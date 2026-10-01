"""
Tests of the client for Ollama's native API, with a fake local server
that imitates /api/chat and keeps what it received.
"""

import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from anchor.planner import LLMPlanner, LLMProfile
from anchor.planner.ollama_client import OllamaClient, OllamaError
from anchor.planner.progress import Progress
from eval.plan_run import warm_up

PLAN = {"steps": [{"action": "click", "description": "botão Salvar", "value": None}]}


class FakeOllama:
    def __init__(self, status=200, content=json.dumps(PLAN)):
        self.status, self.content, self.received = status, content, []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                request = json.loads(self.rfile.read(length))
                fake.received.append((self.path, request))
                if request.get("stream") and fake.status == 200:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/x-ndjson")
                    self.end_headers()
                    chunks = [{"message": {"thinking": "vou "}}, {"message": {"thinking": "clicar"}}]
                    chunks += [{"message": {"content": c}} for c in (fake.content[:10], fake.content[10:])]
                    chunks.append({"done": True, "prompt_eval_count": 50, "eval_count": 12})
                    for chunk in chunks:
                        self.wfile.write((json.dumps(chunk) + "\n").encode())
                        self.wfile.flush()
                    return
                body = json.dumps({"message": {"content": fake.content}, "prompt_eval_count": 50,
                                   "eval_count": 12, "load_duration": 2_500_000_000}).encode()
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body if fake.status == 200 else b'{"error":"model not found"}')

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def ollama():
    fake = FakeOllama()
    yield fake
    fake.close()


def test_plan_through_the_native_api_with_reasoning_off(ollama):
    client = OllamaClient(ollama.url, think=False, options={"num_ctx": 4096})
    plan = LLMPlanner(client, "qwen3.5:4b").plan("salve", "http://x", ["Botão \"Salvar\""])

    assert plan.steps[0].description == "botão Salvar"
    assert plan.tokens_in == 50 and plan.tokens_out == 12
    path, body = ollama.received[0]
    assert path == "/api/chat"
    assert body["model"] == "qwen3.5:4b" and body["stream"] is False
    assert body["think"] is False
    assert body["options"] == {"num_ctx": 4096, "temperature": 0.0, "seed": 7}
    assert body["format"]["required"] == ["goals", "steps"]  # the plan schema goes in "format"


def test_address_with_v1_also_works(ollama):
    OllamaClient(ollama.url + "/v1").chat.completions.create(model="m", messages=[])
    assert ollama.received[0][0] == "/api/chat"


def test_ollama_profile_builds_the_native_client(ollama):
    profile = LLMProfile(name="p", model="qwen3.5:4b", base_url=ollama.url, api="ollama",
                         think=False, options={"num_ctx": 2048})
    planner = profile.planner()
    assert isinstance(planner.client, OllamaClient)
    planner.plan("salve", "http://x")
    assert ollama.received[0][1]["options"]["num_ctx"] == 2048


def test_warm_up_loads_the_model(ollama):
    planner = LLMPlanner(OllamaClient(ollama.url), "qwen3.5:4b")
    assert warm_up(planner) >= 0
    assert ollama.received[0][1]["messages"][0]["content"].startswith("Reply")


def test_missing_model_explains_how_to_check():
    fake = FakeOllama(status=404)
    try:
        with pytest.raises(OllamaError, match="ollama list"):
            OllamaClient(fake.url).chat.completions.create(model="nao-existe", messages=[])
    finally:
        fake.close()


def test_ollama_not_running_explains_the_problem():
    with pytest.raises(OllamaError, match="Ollama app running"):
        OllamaClient("http://127.0.0.1:9", timeout_s=2).chat.completions.create(model="m", messages=[])


def test_streaming_reports_progress_and_builds_the_answer(ollama):
    events = []
    client = OllamaClient(ollama.url, think=True, on_progress=lambda phase, n: events.append((phase, n)))
    plan = LLMPlanner(client, "qwen3.5:4b").plan("salve", "http://x")

    assert ollama.received[0][1]["stream"] is True
    assert plan.steps[0].description == "botão Salvar"   # the chunks were joined
    assert plan.tokens_in == 50 and plan.tokens_out == 12
    assert [p for p, _ in events] == ["thinking", "thinking", "writing", "writing"]
    assert [n for _, n in events] == [1, 2, 3, 4]


def test_without_progress_does_not_stream(ollama):
    OllamaClient(ollama.url).chat.completions.create(model="m", messages=[])
    assert ollama.received[0][1]["stream"] is False


def test_indicator_shows_phase_tokens_and_time():
    out = io.StringIO()
    progress = Progress("  ", stream=out, interval_s=0.05)
    with progress:
        time.sleep(0.12)                      # the clock updates on its own while waiting
        progress.update("thinking", 3)
        progress.update("writing", 40)
    text = out.getvalue()
    assert "waiting for the model... 0 s" in text
    assert "model thinking... 3 tokens" in text
    assert "writing the plan... 40 tokens" in text
    assert text.endswith("\r")                # the line is cleared at the end

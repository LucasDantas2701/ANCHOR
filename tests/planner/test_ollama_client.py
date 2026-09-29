"""
Testes do cliente da API nativa do Ollama, com um servidor falso local
que imita o /api/chat e guarda o que recebeu.
"""

import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.planner import LLMPlanner, LLMProfile
from app.planner.ollama_client import OllamaClient, OllamaError
from app.planner.progress import Progress
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


def test_plano_pela_api_nativa_com_raciocinio_desligado(ollama):
    client = OllamaClient(ollama.url, think=False, options={"num_ctx": 4096})
    plan = LLMPlanner(client, "qwen3.5:4b").plan("salve", "http://x", ["Botão \"Salvar\""])

    assert plan.steps[0].description == "botão Salvar"
    assert plan.tokens_in == 50 and plan.tokens_out == 12
    path, body = ollama.received[0]
    assert path == "/api/chat"
    assert body["model"] == "qwen3.5:4b" and body["stream"] is False
    assert body["think"] is False
    assert body["options"] == {"num_ctx": 4096, "temperature": 0.0, "seed": 7}
    assert body["format"]["required"] == ["goals", "steps"]  # o esquema do plano vai em "format"


def test_endereco_com_v1_tambem_funciona(ollama):
    OllamaClient(ollama.url + "/v1").chat.completions.create(model="m", messages=[])
    assert ollama.received[0][0] == "/api/chat"


def test_perfil_ollama_monta_o_cliente_nativo(ollama):
    profile = LLMProfile(name="p", model="qwen3.5:4b", base_url=ollama.url, api="ollama",
                         think=False, options={"num_ctx": 2048})
    planner = profile.planner()
    assert isinstance(planner.client, OllamaClient)
    planner.plan("salve", "http://x")
    assert ollama.received[0][1]["options"]["num_ctx"] == 2048


def test_aquecimento_carrega_o_modelo(ollama):
    planner = LLMPlanner(OllamaClient(ollama.url), "qwen3.5:4b")
    assert warm_up(planner) >= 0
    assert ollama.received[0][1]["messages"][0]["content"].startswith("Responda")


def test_modelo_inexistente_explica_como_conferir():
    fake = FakeOllama(status=404)
    try:
        with pytest.raises(OllamaError, match="ollama list"):
            OllamaClient(fake.url).chat.completions.create(model="nao-existe", messages=[])
    finally:
        fake.close()


def test_ollama_fechado_explica_o_problema():
    with pytest.raises(OllamaError, match="aplicativo do Ollama está aberto"):
        OllamaClient("http://127.0.0.1:9", timeout_s=2).chat.completions.create(model="m", messages=[])


def test_streaming_avisa_o_progresso_e_monta_a_resposta(ollama):
    events = []
    client = OllamaClient(ollama.url, think=True, on_progress=lambda phase, n: events.append((phase, n)))
    plan = LLMPlanner(client, "qwen3.5:4b").plan("salve", "http://x")

    assert ollama.received[0][1]["stream"] is True
    assert plan.steps[0].description == "botão Salvar"   # os pedaços foram juntados
    assert plan.tokens_in == 50 and plan.tokens_out == 12
    assert [p for p, _ in events] == ["thinking", "thinking", "writing", "writing"]
    assert [n for _, n in events] == [1, 2, 3, 4]


def test_sem_progresso_nao_usa_streaming(ollama):
    OllamaClient(ollama.url).chat.completions.create(model="m", messages=[])
    assert ollama.received[0][1]["stream"] is False


def test_indicador_mostra_fase_tokens_e_tempo():
    out = io.StringIO()
    progress = Progress("  ", stream=out, interval_s=0.05)
    with progress:
        time.sleep(0.12)                      # o relógio atualiza sozinho enquanto espera
        progress.update("thinking", 3)
        progress.update("writing", 40)
    text = out.getvalue()
    assert "aguardando o modelo... 0 s" in text
    assert "modelo pensando... 3 tokens" in text
    assert "escrevendo o plano... 40 tokens" in text
    assert text.endswith("\r")                # a linha é limpa no fim

"""The vision probe: its screenshots and how it reads the answers (no model is called)."""

from types import SimpleNamespace

from eval.vision_probe import _questions, ask


def test_the_probe_has_questions_with_known_answers(page):
    shots = _questions(page)
    assert len(shots) == 6 and sum(expected for _, _, expected in shots) == 3
    assert all(image.startswith(b"\x89PNG") for _, image, _ in shots)


class FakeClient:
    def __init__(self, text):
        self.sent = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.text = text

    def create(self, **kwargs):
        self.sent = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.text))],
                               usage=SimpleNamespace(prompt_tokens=900, completion_tokens=2))


def test_the_image_goes_in_the_message_and_the_answer_is_read():
    client = FakeClient("Sim.")
    answer, seconds, t_in, t_out, raw = ask(client, "m", "Está marcada?", b"\x89PNGdata")
    assert answer is True and t_in == 900
    import base64
    assert client.sent["messages"][0]["images"] == [base64.b64encode(b"\x89PNGdata").decode()]
    assert ask(FakeClient("não"), "m", "x", b"x")[0] is False
    assert ask(FakeClient("talvez"), "m", "x", b"x")[0] is None

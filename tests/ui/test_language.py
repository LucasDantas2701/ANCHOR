"""The interface's language (Settings): what runs say follows it; what the AI reads does not."""
from fastapi.testclient import TestClient

from anchor.i18n import get_language, t
from anchor.ui.server import create_app

from .test_runs import HEADERS, PORT


def test_choosing_the_language_changes_what_runs_say(tmp_path):
    app = create_app(tmp_path / "a", token="the-code", port=PORT, runner=lambda job: {}, headless=True)
    c = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    assert get_language() == "en"
    assert c.put("/api/language", json={"language": "pt"}, headers=HEADERS).json() == {"language": "pt"}
    assert get_language() == "pt" and t("kind.button") == "Botão"
    assert c.put("/api/language", json={"language": "fr"}, headers=HEADERS).status_code == 400
    assert c.put("/api/language", json={"language": "en"}, headers=HEADERS).json() == {"language": "en"}

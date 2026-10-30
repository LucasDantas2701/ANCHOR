"""Saved logins: the password in the credential store only, never answered; a login belongs to an exact site."""
import pytest

from anchor.vault import LoginVault, VaultError, site_of

SECRET = "s3nh@-que-ninguém-vê"


class FakeKeyring:
    """Stands in for Windows' Credential Manager in the tests."""
    def __init__(self):
        self.store = {}

    def set_password(self, service, user, password):
        self.store[(service, user)] = password

    def get_password(self, service, user):
        return self.store.get((service, user))

    def delete_password(self, service, user):
        del self.store[(service, user)]


@pytest.fixture
def vault(tmp_path):
    return LoginVault(tmp_path / "logins.json", keyring=FakeKeyring())


def test_a_site_is_its_exact_address_and_plain_http_only_on_this_computer():
    assert site_of("accounts.example.com/login?x=1") == "https://accounts.example.com"
    assert site_of("https://Accounts.Example.com:8443/a") == "https://accounts.example.com:8443"
    assert site_of("http://localhost:4200/login") == "http://localhost:4200"
    for bad in ("http://intranet.example.com", "ftp://x.com", "javascript:alert(1)", ""):
        with pytest.raises(VaultError):
            site_of(bad)


def test_the_password_goes_to_the_store_and_the_file_has_nothing_secret(vault):
    vault.add("https://accounts.example.com/login", "maria@example.com", SECRET)
    assert SECRET not in vault.path.read_text(encoding="utf-8")
    assert vault.keyring.store == {("ANCHOR login https://accounts.example.com", "maria@example.com"): SECRET}
    login = vault.logins()[0]
    assert vault.password(login) == SECRET and login.scheduled is False


def test_a_login_is_found_only_on_its_exact_site(vault):
    vault.add("accounts.example.com", "maria", SECRET)
    assert len(vault.for_site("https://accounts.example.com/signin?next=/")) == 1
    for other in ("https://mail.example.com/", "https://example.com/", "https://accounts.example.com:8443/",
                  "http://accounts.example.com/", "https://accounts.example.com.evil.io/", "not a url"):
        assert vault.for_site(other) == []


def test_replace_schedule_and_delete(vault):
    vault.add("accounts.example.com", "maria", SECRET)
    with pytest.raises(VaultError):
        vault.add("accounts.example.com", "maria", "outra")                # already saved: replace instead
    vault.replace_password("https://accounts.example.com", "maria", "nova")
    assert vault.password(vault.logins()[0]) == "nova"
    vault.set_scheduled("https://accounts.example.com", "maria", True)
    assert vault.logins()[0].scheduled is True
    vault.delete("https://accounts.example.com", "maria")
    assert vault.logins() == [] and vault.keyring.store == {}


def test_the_interface_never_answers_with_a_password(tmp_path):
    from fastapi.testclient import TestClient

    from anchor.ui.server import create_app
    from tests.ui.test_runs import HEADERS, PORT
    vault = LoginVault(tmp_path / "logins.json", keyring=FakeKeyring())
    app = create_app(tmp_path / "automations", token="the-code", port=PORT, runner=lambda job: {"state": "checked", "message": ""},
                     headless=True, vault=vault)
    c = TestClient(app, base_url=f"http://127.0.0.1:{PORT}")
    answers = [c.post("/api/logins", json={"site": "accounts.example.com", "username": "maria", "password": SECRET}, headers=HEADERS),
               c.post("/api/logins", json={"site": "accounts.example.com", "username": "maria", "password": SECRET}, headers=HEADERS),
               c.post("/api/logins", json={"site": "http://insecure.example.com", "username": "x", "password": SECRET}, headers=HEADERS),
               c.get("/api/logins", headers=HEADERS),
               c.put("/api/logins/password", json={"site": "https://accounts.example.com", "username": "maria", "password": SECRET + "2"}, headers=HEADERS),
               c.put("/api/logins/scheduled", json={"site": "https://accounts.example.com", "username": "maria", "scheduled": True}, headers=HEADERS)]
    assert [a.status_code for a in answers] == [200, 400, 400, 200, 200, 200]
    assert all(SECRET not in a.text for a in answers)                     # not in a list, not in an error
    listed = answers[3].json()[0]
    assert set(listed) == {"site", "username", "created", "last_used", "scheduled"} and listed["site"] == "https://accounts.example.com"
    assert c.delete("/api/logins", params={"site": "https://accounts.example.com", "username": "maria"}, headers=HEADERS).status_code == 200
    assert c.get("/api/logins", headers=HEADERS).json() == [] and vault.keyring.store == {}

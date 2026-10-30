"""Logging in with a saved login, in a real browser, on login pages served by this computer."""
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from anchor.vault import LoginVault
from anchor.vault.fill import VaultLoginWaiter

from .test_vault import FakeKeyring

SECRET = "certa-123"

LOGIN = """<!doctype html><title>Entrar</title>
<form id="f"><label>E-mail <input name="email" type="email"></label>
<label>Senha <input name="senha" type="password"></label><button>Entrar</button></form><p id="msg"></p>
<script>document.getElementById('f').onsubmit = (ev) => { ev.preventDefault();
  const f = ev.target; if (f.email.value === 'maria@example.com' && f.senha.value === '%s') location.href = 'home.html';
  else { document.getElementById('msg').textContent = 'Senha incorreta'; f.senha.value = ''; } };</script>""" % SECRET
TWO_STEP = """<!doctype html><title>Entrar</title>
<form id="a"><label>E-mail <input name="identifier" type="email"></label><button>Próximo</button></form>
<form id="b" hidden><label>Senha <input name="senha" type="password"></label><button>Entrar</button></form>
<script>document.getElementById('a').onsubmit = (ev) => { ev.preventDefault(); document.getElementById('a').hidden = true;
  document.getElementById('b').hidden = false; };
document.getElementById('b').onsubmit = (ev) => { ev.preventDefault();
  if (ev.target.senha.value === '%s') location.href = 'home.html'; };</script>""" % SECRET
HOME = "<!doctype html><title>Início</title><h1>Bem-vinda</h1>"


def serve(folder):
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Quiet, directory=str(folder)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def site(tmp_path):
    (tmp_path / "login.html").write_text(LOGIN, encoding="utf-8")
    (tmp_path / "two.html").write_text(TWO_STEP, encoding="utf-8")
    (tmp_path / "home.html").write_text(HOME, encoding="utf-8")
    server, root = serve(tmp_path)
    yield tmp_path, root
    server.shutdown()


class Person:
    """The fallback: the person asked to log in (here, nobody answers)."""
    def __init__(self):
        self.asked = 0

    def wait(self, url, signup=False):
        self.asked += 1
        return False


def waiter(tmp_path, page, unattended=False):
    said = []
    vault = LoginVault(tmp_path / "logins.json", keyring=FakeKeyring())
    person = Person()
    return vault, person, said, VaultLoginWaiter(vault, lambda: page, fallback=person, report=said.append, unattended=unattended)


def test_a_saved_login_logs_in_on_its_exact_site_and_the_password_is_never_said(page, site):
    folder, root = site
    vault, person, said, w = waiter(folder, page)
    vault.add(root, "maria@example.com", SECRET)
    page.goto(root + "/login.html")
    assert w.wait(page.url) is True and page.url.endswith("/home.html") and person.asked == 0
    assert vault.logins()[0].last_used and not any(SECRET in s for s in said)


def test_two_steps_the_user_name_then_the_password(page, site):
    folder, root = site
    vault, person, said, w = waiter(folder, page)
    vault.add(root, "maria@example.com", SECRET)
    page.goto(root + "/two.html")
    assert w.wait(page.url) is True and page.url.endswith("/home.html")


def test_a_wrong_password_hands_over_to_the_person(page, site):
    folder, root = site
    vault, person, said, w = waiter(folder, page)
    vault.add(root, "maria@example.com", "errada")
    page.goto(root + "/login.html")
    assert w.wait(page.url) is False and person.asked == 1 and "did not get in" in said[-1]


def test_no_saved_login_another_site_or_two_logins_hand_over_without_typing(page, site):
    folder, root = site
    vault, person, said, w = waiter(folder, page)
    page.goto(root + "/login.html")
    assert w.wait(page.url) is False and person.asked == 1                      # nothing saved
    vault.add("https://accounts.example.com", "maria@example.com", SECRET)
    assert w.wait(page.url) is False and person.asked == 2                      # saved for another site
    vault.add(root, "maria@example.com", SECRET)
    vault.add(root, "joao@example.com", SECRET)
    assert w.wait(page.url) is False and person.asked == 3 and "2 saved logins" in said[-1]
    assert page.locator("input[type=password]").input_value() == ""            # nothing typed


def test_a_password_form_inside_a_frame_of_another_site_is_not_filled(page, site, tmp_path_factory):
    folder, root = site
    other = tmp_path_factory.mktemp("other")
    (other / "login.html").write_text(LOGIN, encoding="utf-8")
    server, other_root = serve(other)
    try:
        (folder / "framed.html").write_text(f'<!doctype html><h1>Portal</h1><iframe src="{other_root}/login.html" width=600 height=300></iframe>',
                                            encoding="utf-8")
        vault, person, said, w = waiter(folder, page)
        vault.add(root, "maria@example.com", SECRET)                           # saved for the page, not for the frame
        page.goto(root + "/framed.html")
        page.wait_for_timeout(500)
        assert w.wait(page.url) is False and person.asked == 1
        assert page.frames[1].locator("input[type=password]").input_value() == ""
    finally:
        server.shutdown()


def test_with_no_one_present_only_a_login_allowed_for_scheduled_runs(page, site):
    folder, root = site
    vault, person, said, w = waiter(folder, page, unattended=True)
    vault.add(root, "maria@example.com", SECRET)
    page.goto(root + "/login.html")
    assert w.wait(page.url) is False                                           # not allowed: nobody to ask either
    vault.set_scheduled(root, "maria@example.com", True)
    assert w.wait(page.url) is True and page.url.endswith("/home.html")


def test_the_page_reader_shows_the_ai_only_stars_for_a_filled_password(page, site):
    from anchor.engine.element_resolver import ElementResolver
    folder, root = site
    page.goto(root + "/login.html")
    page.locator("input[type=password]").fill(SECRET)
    seen = str(ElementResolver(page).index())
    assert SECRET not in seen

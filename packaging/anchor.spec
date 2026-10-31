# PyInstaller recipe for ANCHOR.exe: the desktop program with Python, its libraries, the built
# interface, the model profiles, the script ANCHOR puts in pages, and the icon. The browser (Chromium)
# is not included: the program downloads it on its first opening.
#
#   cd web && npm ci && npm run build && cd ..
#   pip install -r requirements-desktop.txt
#   pyinstaller packaging/anchor.spec --noconfirm
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
for needed in (ROOT / "anchor" / "ui" / "static" / "index.html", ROOT / "anchor" / "desktop" / "anchor.ico"):
    if not needed.is_file():
        raise SystemExit(f"missing {needed}: build the interface first (cd web && npm run build)")

datas = [
    (str(ROOT / "anchor" / "ui" / "static"), "anchor/ui/static"),
    (str(ROOT / "llm_profiles.json"), "."),
    (str(ROOT / "anchor" / "engine" / "element_resolver" / "index_script.js"), "anchor/engine/element_resolver"),
    (str(ROOT / "anchor" / "desktop" / "anchor.ico"), "anchor/desktop"),
]
hidden = (collect_submodules("anchor") + collect_submodules("uvicorn") + collect_submodules("keyring.backends")
          + ["pystray._win32", "webview.platforms.edgechromium", "webview.platforms.winforms"])

a = Analysis([str(ROOT / "packaging" / "launch.py")], pathex=[str(ROOT)], datas=datas, hiddenimports=hidden,
             # chardet: requests uses charset-normalizer (ANCHOR's dependency); a compiled chardet found on the
             # building machine crashes once frozen, so it is never carried along.
             excludes=["eval", "tests", "nltk", "tkinter", "matplotlib", "IPython", "chardet"])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ANCHOR", console=False,
          icon=str(ROOT / "anchor" / "desktop" / "anchor.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="ANCHOR")

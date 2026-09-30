from pathlib import Path

INDEX_SCRIPT_PATH = (
    Path(__file__).resolve().parent / "index_script.js"
)


def load_index_script() -> str:
    return INDEX_SCRIPT_PATH.read_text(
        encoding="utf-8"
    )
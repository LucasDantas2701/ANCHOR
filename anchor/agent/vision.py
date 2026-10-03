"""
Effect check by screenshot (layer 4): the last resort when the other checks are in doubt.

Measured with eval/vision_probe.py: the Qwen 3.5 models (4B and 9B) got all the yes/no
questions about a 640-pixel screenshot right, in about 5 s (4B) and 9 s (9B). Too slow for
every step, so the agent asks only when the other checks doubt a step:

    a field, list or box whose state does not match  → does the screenshot show it?
    a click with no visible effect in the page code   → did the page change between the shots?
    an expected text that did not appear in the code  → does the screenshot show it?

The screenshot can only CONFIRM a step the other checks doubted; it never turns a step that
worked into a failure, and an unclear answer counts as "not confirmed".
"""

from __future__ import annotations

import base64
import time
from typing import Optional

from anchor.planner.language import DEFAULT_PROMPT_LANGUAGE, mt

# Scales a PNG down to the given width inside the browser (no extra dependency, no change
# to the page or the window).
_SHRINK_JS = r"""async ([b64, width]) => {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const bitmap = await createImageBitmap(new Blob([bytes], {type: "image/png"}));
    if (bitmap.width <= width) return b64;
    const height = Math.round(bitmap.height * width / bitmap.width);
    const canvas = new OffscreenCanvas(width, height);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, width, height);
    const blob = await canvas.convertToBlob({type: "image/png"});
    const buffer = new Uint8Array(await blob.arrayBuffer());
    let text = ""; for (let i = 0; i < buffer.length; i += 8192) text += String.fromCharCode(...buffer.subarray(i, i + 8192));
    return btoa(text);
}"""


class VisionChecker:
    def __init__(self, client, model: str, width: int = 640, language: str = DEFAULT_PROMPT_LANGUAGE):
        self.client, self.model, self.width, self.language = client, model, width, language
        self.checks = 0            # questions asked
        self.seconds = 0.0         # time spent on them

    # ------------------------------------------------------------ screenshots
    def capture(self, page) -> Optional[str]:
        """A screenshot of the visible page, scaled to self.width, as base64 (None if it fails)."""
        try:
            raw = base64.b64encode(page.screenshot()).decode("ascii")
        except Exception:
            return None
        try:
            return page.evaluate(_SHRINK_JS, [raw, self.width])
        except Exception:
            return raw

    # ------------------------------------------------------------ questions
    def ask(self, question: str, images: list[str]) -> Optional[bool]:
        """True or False for a yes/no question about the images; None if unclear or on error."""
        if not images or any(i is None for i in images):
            return None
        start = time.perf_counter()
        self.checks += 1
        try:
            response = self.client.chat.completions.create(
                model=self.model, temperature=0,
                messages=[{"role": "user", "content": question + " " + mt("vision.answer", self.language),
                           "images": images}],
            )
            word = (response.choices[0].message.content or "").strip().lower().strip(" .!\n")
        except Exception:
            return None
        finally:
            self.seconds += time.perf_counter() - start
        if word.startswith(("sim", "yes")):
            return True
        if word.startswith(("não", "nao", "no")):
            return False
        return None

    def shows_state(self, page, action: str, description: str, value: Optional[str]) -> Optional[bool]:
        key = {"fill": "vision.field", "select": "vision.list", "check": "vision.checked",
               "uncheck": "vision.unchecked"}.get(action)
        if key is None:
            return None
        return self.ask(mt(key, self.language, element=description, value=value or ""), [self.capture(page)])

    def shows_text(self, page, text: str) -> Optional[bool]:
        return self.ask(mt("vision.text", self.language, text=text), [self.capture(page)])

    def changed(self, before: Optional[str], page, description: str) -> Optional[bool]:
        return self.ask(mt("vision.changed", self.language, step=description), [before, self.capture(page)])

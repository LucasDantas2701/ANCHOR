"""The click capture that does not hold the run: started, read, and cancelled."""
from anchor.engine.disambiguation.page_tools import cancel_capture, read_capture, start_capture


def test_a_capture_started_without_waiting_ends_with_the_click(page):
    page.set_content('<p>Order 42</p><button id="b" style="margin:40px">▶</button>')
    start_capture(page)
    assert read_capture(page) == (False, None)
    box = page.locator("#b").bounding_box()
    page.mouse.click(box["x"] + 5, box["y"] + 5)
    done, match = read_capture(page)
    assert done and match is not None and match.tag == "button"
    assert page.locator("#er-point-banner").count() == 0


def test_a_capture_can_be_cancelled(page):
    page.set_content('<button id="b">Go</button>')
    start_capture(page)
    assert page.locator("#er-point-banner").count() == 1
    cancel_capture(page)
    assert read_capture(page) == (True, None) and page.locator("#er-point-banner").count() == 0

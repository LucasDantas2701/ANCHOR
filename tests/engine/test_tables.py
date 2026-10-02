"""Table cells: the column header says what a cell is; extraction never targets a checkbox."""

from anchor.engine.action_executor import ActionExecutor
from anchor.engine.element_resolver import ElementResolver

TABLE = """<html><body><table>
  <thead><tr><th><input type="checkbox" aria-label="Select all"></th><th>Name</th><th>E-mail</th><th>Status</th></tr></thead>
  <tbody>
    <tr><td><input type="checkbox" aria-label="Select Brian Lee"></td><td>Brian Lee</td><td>brian@company.com</td><td>Inactive</td></tr>
    <tr><td><input type="checkbox" aria-label="Select Carol Miller"></td><td>Carol Miller</td><td>carol@company.com</td><td>Active</td></tr>
  </tbody></table></body></html>"""


def test_cell_records_its_column_header(page):
    page.set_content(TABLE)
    resolver = ElementResolver(page)
    resolver.index("content")
    email = next(r for r in resolver.records if r["text"] == "brian@company.com")
    assert email["column"] == "E-mail" and "E-mail" in email["hint"]


def test_interactive_cells_do_not_get_the_header(page):
    page.set_content(TABLE)
    resolver = ElementResolver(page)
    resolver.index("content")
    box = next(r for r in resolver.records if r["label"] == "Select Brian Lee")
    assert box["column"] == ""


def test_extracting_an_email_reads_the_email_cell(page):
    page.set_content(TABLE)
    result = ActionExecutor(page).extract_text("Brian Lee's e-mail")
    assert result.status == "success" and result.value == "brian@company.com"


def test_extraction_never_targets_a_checkbox(page):
    page.set_content(TABLE)
    matches = ElementResolver(page).query("Select Carol Miller", k=10, action="extract")
    assert all(m.role != "checkbox" for m in matches)


def test_verbs_inside_parentheses_are_context_not_the_action(page):
    """The model copies the item's context from the page summary, with the neighbours' names."""
    page.set_content("""<html><body>
      <div class="o"><strong>Order #1023</strong> · Delivered <button>View details</button> <button disabled>Cancel order</button></div>
      <div class="o"><strong>Order #1024</strong> · Being packed <button>View details</button> <button>Cancel order</button></div>
    </body></html>""")
    top = ElementResolver(page).query("Cancel order (Order #1024 · Being packed View details)", k=2, action="click")
    assert top[0].text == "Cancel order" and top[0].score > top[1].score * 1.5

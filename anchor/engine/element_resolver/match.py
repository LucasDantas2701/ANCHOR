from dataclasses import dataclass, field

from playwright.sync_api import Locator, Page


@dataclass
class Match:
    id: str
    tag: str
    role: str
    label: str
    text: str
    content: str
    context: str
    rect: dict
    score: float
    page: Page = field(repr=False)

    # Newer fields from index_script.js (optional, so tests with mocks keep working).
    type: str = ""
    value: str = ""
    hint: str = ""
    href: str = ""
    test_id: str = ""
    state: dict = field(default_factory=dict)
    options: list = field(default_factory=list)
    in_viewport: bool = True
    obscured: bool = False
    layer: bool = False          # inside an open pop-up, dialog or menu

    @property
    def locator(self) -> Locator:
        return self.page.locator(
            f'[data-er-id="{self.id}"]'
        )

    def click(self, **kwargs) -> None:
        self.locator.click(**kwargs)

    def fill(self, value: str, **kwargs) -> None:
        self.locator.fill(value, **kwargs)

    def __repr__(self) -> str:
        return (
            f"Match("
            f"score={self.score:.2f}, "
            f"role='{self.role}', "
            f"text='{self.text}', "
            f"hint='{self.hint}', "
            f"context='{self.context}'"
            f")"
        )
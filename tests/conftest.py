"""Shared test setup."""
import pytest

from anchor.i18n import set_language


@pytest.fixture(autouse=True)
def _language_back_to_default():
    """The interface's server sets the message language for the whole process (English); after each
    test it goes back to the default, so no test changes the language another one sees, in any order."""
    yield
    set_language(None)

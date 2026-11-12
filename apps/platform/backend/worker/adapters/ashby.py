from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from .base import Adapter


class Ashby(Adapter):
    """Single page at /application, rendered by React after load. There is
    no <form> element: fields live in the application form container."""
    name = "ashby"
    hosts = ("ashbyhq.com",)
    # Not [class*=ashby-application-form]: the autofill pane matches that
    # too and comes first in the document.
    root = ".ashby-application-form-container"
    confirm_selector = ".ashby-application-form-success-container, [class*='success-container']"

    def prepare(self, page: Page) -> None:
        try:
            page.wait_for_selector(self.root, timeout=15000)
        except PlaywrightError:
            pass

    def form_present(self, page: Page) -> bool:
        try:
            return page.locator(self.root).first.locator(
                "input:not([type=hidden]), textarea").count() > 0
        except PlaywrightError:
            return False

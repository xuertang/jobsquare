from __future__ import annotations

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from .base import Adapter


class SmartRecruiters(Adapter):
    """Multi-step. The one-click flow is built from web components with open
    shadow roots, and screening questions arrive on later steps: the runner
    re-scans after each step the user advances and fills what is new."""
    name = "smartrecruiters"
    hosts = ("smartrecruiters.com",)
    root = "main, form, body"
    multi_step = True

    def prepare(self, page: Page) -> None:
        try:
            page.wait_for_selector("input, oc-personal-information, spl-input",
                                   timeout=15000)
        except PlaywrightError:
            pass

    def form_present(self, page: Page) -> bool:
        try:
            return page.locator("input:not([type=hidden]), textarea").count() > 0
        except PlaywrightError:
            return False

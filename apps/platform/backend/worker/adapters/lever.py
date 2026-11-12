from __future__ import annotations

import re

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from .. import form
from .base import Adapter


class Lever(Adapter):
    """Single page at /apply, server rendered, native controls throughout."""
    name = "lever"
    hosts = ("lever.co",)
    root = "#application-form, form[action*='/apply']"
    confirm_url = re.compile(r"/thanks\b")

    def after_fill(self, page: Page, decision: dict) -> None:
        # The location box only counts once a suggestion is picked from its
        # dropdown: typing alone leaves the hidden selectedLocation empty and
        # the box is cleared on blur. The search listens for key events, so
        # the value is typed rather than set.
        if decision["key"] != "text:location":
            return
        box = form.field(page, decision["key"])
        results = page.locator(".dropdown-results > *")
        for attempt in dict.fromkeys((str(decision["value"]),
                                      str(decision["value"]).split(",")[0].strip())):
            try:
                box.fill("")
                box.type(attempt, delay=25)
                results.first.wait_for(state="visible", timeout=4000)
                form.safe_click(results.first, timeout=2000)
                return
            except PlaywrightError:
                continue

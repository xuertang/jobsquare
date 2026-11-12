"""ATS adapters. Each one knows where its form lives, how to tell that an
application went through, and what a dead or blocked page looks like. The
field logic itself is shared (worker/form.py and page.js)."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

CONFIRMED = re.compile(
    r"(thank you|thanks) for (applying|your application|your interest in)|"
    r"application (has been |was )?(successfully )?(submitted|received|sent)|"
    r"we('ve| have) received your application|your application is (in|on its way)", re.I)
CLOSED = re.compile(
    r"(job|position|posting|role|page) (is |has been )?(no longer|not) (available|open|accepting)|"
    r"no longer accepting applications|job (not found|has been filled|is closed)|"
    r"this (job|position) has (expired|been closed|been filled)|page not found|\b404\b", re.I)
CAPTCHA_FRAMES = ("recaptcha", "hcaptcha", "challenges.cloudflare.com", "turnstile")


class Adapter:
    name = "generic"
    hosts: tuple[str, ...] = ()
    root = "form"                   # CSS selector for the application form
    confirm_url: re.Pattern | None = None
    confirm_selector: str | None = None
    multi_step = False

    def matches(self, url: str) -> bool:
        host = urlparse(url).hostname or ""
        return any(host == h or host.endswith("." + h) for h in self.hosts)

    def prepare(self, page: Page) -> None:
        """Bring the form into view. Adapters override when the form sits
        behind a tab or anchor; nothing here may submit anything."""

    def form_present(self, page: Page) -> bool:
        try:
            return page.locator(self.root).first.locator(
                "input:not([type=hidden]), textarea, select").count() > 0
        except PlaywrightError:
            return False

    def confirmed(self, page: Page, baseline: bool) -> bool:
        """True once the page shows the application went through. `baseline`
        is whether the confirmation wording was already on the page before
        the fill, in which case wording alone proves nothing."""
        try:
            if self.confirm_url and self.confirm_url.search(page.url):
                return True
            if self.confirm_selector and page.locator(self.confirm_selector).count():
                return True
            if baseline or self.form_present(page):
                return False
            return bool(CONFIRMED.search(body_text(page)))
        except PlaywrightError:
            return False

    def confirmation_wording(self, page: Page) -> bool:
        return bool(CONFIRMED.search(body_text(page)))

    def closed_reason(self, page: Page) -> str:
        if self.form_present(page):
            return ""
        return "The posting looks closed or the page was not found." \
            if CLOSED.search(body_text(page)[:4000]) else ""

    def after_fill(self, page: Page, decision: dict) -> None:
        """Hook for site quirks that follow a successful fill."""

    def has_captcha(self, page: Page) -> bool:
        try:
            return any(any(m in (f.url or "") for m in CAPTCHA_FRAMES) for f in page.frames)
        except PlaywrightError:
            return False

    def login_wall(self, page: Page) -> bool:
        try:
            return (page.locator("input[type=password]").count() > 0
                    and not self.form_present(page))
        except PlaywrightError:
            return False


def body_text(page: Page) -> str:
    try:
        return page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    except PlaywrightError:
        return ""

"""The apply worker: opens an approved application in a visible browser,
fills what it can, and stops. It never clicks submit. While the form is
paused it watches for the user's edits and for the confirmation page, then
records what was actually submitted."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from playwright.sync_api import BrowserContext, Page, sync_playwright
from playwright.sync_api import Error as PlaywrightError

from . import form
from .adapters import adapter_for
from .adapters.base import Adapter
from .client import Api

log = logging.getLogger("copilot.worker")

FORM_WAIT = 120          # seconds to wait for a form (time to clear a challenge page)
HEARTBEAT = 10
IDLE_POLL = 3.0
ACTIVE_POLL = 1.0


@dataclass
class Session:
    task: dict
    page: Page
    adapter: Adapter
    resume_path: Path | None
    opened: float = field(default_factory=time.monotonic)
    state: str = "loading"                       # loading | paused
    seen: set[str] = field(default_factory=set)
    last_values: dict[str, str] = field(default_factory=dict)
    baseline: bool = False
    last_beat: float = 0.0

    @property
    def app_id(self) -> int:
        return self.task["application_id"]

    @property
    def label(self) -> str:
        p = self.task["posting"]
        return f"{p['company']}: {p['title']}"


class Worker:
    def __init__(self, api_url: str, data_dir: Path, *, headless: bool = False,
                 max_tabs: int = 3, channel: str | None = None,
                 token: str | None = None) -> None:
        self.api = Api(api_url, token)
        self.data_dir = data_dir
        self.headless = headless
        self.max_tabs = max_tabs
        self.channel = channel
        self.sessions: list[Session] = []
        self.context: BrowserContext | None = None
        self._pw = None

    # --------------------------------------------------------- browser ---
    def _browser(self) -> BrowserContext:
        """Visible Chromium with a persistent profile, started on demand."""
        if self.context is not None:
            return self.context
        if self._pw is None:
            self._pw = sync_playwright().start()
        profile = self.data_dir / "browser-profile"
        profile.mkdir(parents=True, exist_ok=True)
        self.context = self._pw.chromium.launch_persistent_context(
            str(profile), headless=self.headless, channel=self.channel,
            viewport=None if not self.headless else {"width": 1280, "height": 900},
            args=[] if self.headless else ["--start-maximized"])
        self.context.add_init_script(form.PAGE_JS)
        self.context.on("close", lambda *_: setattr(self, "context", None))
        return self.context

    def _close_browser(self) -> None:
        if self.context is not None:
            try:
                self.context.close()
            except PlaywrightError:
                pass
            self.context = None

    def stop(self) -> None:
        for s in list(self.sessions):
            self._release(s, "The apply worker was stopped before this was submitted.")
        self._close_browser()
        if self._pw is not None:
            self._pw.stop()
            self._pw = None

    # ------------------------------------------------------------ loop ---
    def run(self, once: bool = False) -> None:
        log.info("apply worker ready (up to %d tab(s)); waiting for approved fills",
                 self.max_tabs)
        handled = 0
        while True:
            try:
                if len(self.sessions) < self.max_tabs and not (once and handled):
                    task = self.api.claim()
                    if task:
                        handled += 1
                        self._open(task)
                for s in list(self.sessions):
                    self._tick(s)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 503):
                    log.error("the API refused the worker (%s). Check COPILOT_WORKER_TOKEN "
                              "against the server's .env; retrying in 30s",
                              e.response.status_code)
                    time.sleep(30)
                else:
                    log.warning("API error (%s); retrying", e)
                    time.sleep(5)
            except httpx.HTTPError as e:
                log.warning("API unreachable (%s); retrying", e)
                time.sleep(5)
            if not self.sessions:
                self._close_browser()
                if once and handled:
                    return
            time.sleep(ACTIVE_POLL if self.sessions else IDLE_POLL)

    # --------------------------------------------------------- session ---
    def _open(self, task: dict) -> None:
        posting = task["posting"]
        adapter = adapter_for(posting["ats_type"])
        if adapter is None:
            self.api.released(task["application_id"], task["id"],
                              f"No apply adapter for {posting['ats_type']}.", needs_manual=True)
            return
        resume_path = None
        if task.get("resume"):
            try:
                resume_path = self.api.download_resume(task["resume"],
                                                       self.data_dir / "worker-tmp")
            except httpx.HTTPError as e:
                log.warning("could not fetch the resume file: %s", e)
        page = self._browser().new_page()
        session = Session(task=task, page=page, adapter=adapter, resume_path=resume_path)
        self.sessions.append(session)
        log.info("opening %s", session.label)
        try:
            response = page.goto(posting["apply_url"], wait_until="domcontentloaded",
                                 timeout=45000)
            if response is not None and response.status >= 400:
                self._release(session, f"The application page returned HTTP "
                                       f"{response.status}.", needs_manual=True)
                return
            adapter.prepare(page)
        except PlaywrightError as e:
            self._release(session, f"Could not load the application page: "
                                   f"{str(e).splitlines()[0][:160]}", needs_manual=True)

    def _tick(self, s: Session) -> None:
        if s not in self.sessions:
            return
        if s.page.is_closed():
            self._release(s, "The browser tab was closed before the application was "
                             "submitted. Launch the fill again, or mark it submitted "
                             "if you did apply.")
            return
        now = time.monotonic()
        if now - s.last_beat > HEARTBEAT:
            s.last_beat = now
            if self.api.heartbeat(s.task["id"]) == "cancelled":
                log.info("cancelled from the dashboard: %s", s.label)
                self._drop(s)
                return
        try:
            if s.state == "loading":
                self._tick_loading(s)
            else:
                self._tick_paused(s)
        except PlaywrightError as e:
            # Mid-navigation reads fail; the next tick sees the settled page.
            log.debug("tick skipped for %s: %s", s.label, str(e).splitlines()[0])

    def _tick_loading(self, s: Session) -> None:
        if s.adapter.form_present(s.page):
            s.baseline = s.adapter.confirmation_wording(s.page)
            self._fill_new(s)
            s.state = "paused"
            log.info("filled and paused for review: %s", s.label)
            return
        reason = s.adapter.closed_reason(s.page)
        if reason:
            self._release(s, reason, needs_manual=True)
        elif s.adapter.login_wall(s.page):
            self._release(s, "The site asks you to sign in before applying.",
                          needs_manual=True)
        elif time.monotonic() - s.opened > FORM_WAIT:
            self._release(s, "No application form appeared. The page may be blocked "
                             "by a CAPTCHA or bot check.", needs_manual=True)

    def _tick_paused(self, s: Session) -> None:
        if s.adapter.confirmed(s.page, s.baseline):
            self._submitted(s)
            return
        current = form.values(s.page, s.adapter.root)
        if any(k not in s.seen for k in current):
            self._fill_new(s)            # a new step or a conditional question
            current = form.values(s.page, s.adapter.root)
        if current != s.last_values:
            s.last_values = current
            self.api.snapshot(s.app_id, current)

    def _fill_new(self, s: Session) -> None:
        fields = [f for f in form.extract(s.page, s.adapter.root) if f["key"] not in s.seen]
        if not fields:
            return
        for f in fields:
            if f["type"] == "combobox" and not f["options"]:
                f["options"] = form.read_options(s.page, f["key"])
        decisions = self.api.plan(s.app_id, fields)
        prefilled = {f["key"] for f in fields if f.get("value") and f["type"] != "file"}
        results: dict[str, dict] = {}
        form.set_filling(s.page, True)
        try:
            for d in decisions:
                if d["action"] != "fill":
                    continue
                if d["key"] in prefilled:
                    results[d["key"]] = {"ok": True, "error": ""}   # keep what is there
                    continue
                results[d["key"]] = form.fill(s.page, d, s.resume_path)
                if results[d["key"]]["ok"]:
                    s.adapter.after_fill(s.page, d)
        finally:
            form.set_filling(s.page, False)
        s.seen.update(f["key"] for f in fields)
        report = {"captcha": s.adapter.has_captcha(s.page), "url": s.page.url,
                  "blocked_submits": form.blocked_submits(s.page),
                  "multi_step": s.adapter.multi_step}
        self.api.filled(s.app_id, decisions, results, report)
        s.last_values = form.values(s.page, s.adapter.root)
        self.api.snapshot(s.app_id, s.last_values)

    def _submitted(self, s: Session) -> None:
        final = form.final_values(s.page) or s.last_values
        shot = None
        try:
            s.page.wait_for_timeout(800)          # let the confirmation render
            shot = s.page.screenshot(full_page=True)
        except PlaywrightError:
            pass
        out = self.api.submitted(s.app_id, final, shot)
        log.info("submitted by you and recorded: %s (%d answer(s) saved to the bank)",
                 s.label, out.get("bank_saved", 0))
        self._drop(s, close_after=2500)

    def _release(self, s: Session, reason: str, needs_manual: bool = False) -> None:
        log.info("%s: %s", "manual queue" if needs_manual else "released", reason)
        try:
            self.api.released(s.app_id, s.task["id"], reason, needs_manual)
        except httpx.HTTPError as e:
            log.warning("could not report release: %s", e)
        self._drop(s)

    def _drop(self, s: Session, close_after: int = 0) -> None:
        if s in self.sessions:
            self.sessions.remove(s)
        try:
            if not s.page.is_closed():
                if close_after:
                    s.page.wait_for_timeout(close_after)
                s.page.close()
        except PlaywrightError:
            pass

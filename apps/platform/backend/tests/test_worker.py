"""The worker loop end to end: fill, pause, pick up the user's edits, notice
the confirmation page, record what was really submitted. The API is replaced
by an in-memory fake that uses the real planner; the form is a local page."""
import copy
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from copilot import apply, seed  # noqa: E402
from worker.runner import Worker  # noqa: E402

pytestmark = pytest.mark.browser
FLOW = Path(__file__).parent / "fixtures" / "flow"


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(FLOW)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


class FakeApi:
    """Records every call the worker makes."""

    def __init__(self, profile, resume_file):
        self.profile, self.resume_file = profile, resume_file
        self.filled_calls, self.snapshots, self.submitted_calls, self.released_calls = [], [], [], []
        self.task_state = "running"

    def claim(self):
        return None

    def heartbeat(self, task_id):
        return self.task_state

    def plan(self, application_id, fields):
        return apply.plan(fields, profile=self.profile, bank=[], settings=dict(seed.DEFAULT_APP),
                          posting={"company": "Acme", "title": "Senior Software Engineer"},
                          resume={"id": 1, "label": "General", "path": "x.pdf"}, use_llm=False)

    def filled(self, application_id, decisions, results, report):
        self.filled_calls.append((decisions, results, report))
        return report

    def snapshot(self, application_id, values):
        self.snapshots.append(dict(values))

    def submitted(self, application_id, values, screenshot):
        self.submitted_calls.append((dict(values), screenshot))
        return {"bank_saved": 1}

    def released(self, application_id, task_id, reason, needs_manual=False):
        self.released_calls.append((reason, needs_manual))

    def download_resume(self, resume, into):
        return self.resume_file


@pytest.fixture
def worker(tmp_path, profile):
    resume = tmp_path / "alex-rivera.pdf"
    resume.write_bytes(b"%PDF-1.4")
    try:
        w = Worker("http://unused", tmp_path / "data", headless=True)
        w.api = FakeApi(copy.deepcopy(profile), resume)
        w._browser()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Chromium is not installed: {e}")
    yield w
    w.sessions.clear()
    w._close_browser()
    if w._pw:
        w._pw.stop()


def task(site, page="apply.html"):
    return {"id": 7, "application_id": 3, "resume": {"id": 1, "filename": "alex-rivera.pdf"},
            "posting": {"id": 1, "title": "Senior Software Engineer", "company": "Acme",
                        "ats_type": "greenhouse", "apply_url": f"{site}/{page}"}}


def tick_until(worker, done, tries=40):
    for _ in range(tries):
        for s in list(worker.sessions):
            worker._tick(s)
        if done():
            return
        if worker.sessions:
            worker.sessions[0].page.wait_for_timeout(100)
    raise AssertionError("worker did not reach the expected state")


def test_fill_pause_edit_submit(worker, site):
    api = worker.api
    worker._open(task(site))
    session = worker.sessions[0]
    tick_until(worker, lambda: session.state == "paused")
    page = session.page

    # Filled from the profile, then stopped. Still on the form: nothing submitted.
    assert page.url.endswith("/apply.html")
    assert page.input_value("#first_name") == "Alex"
    assert page.input_value("#email") == "alex@example.com"
    assert page.input_value("#auth") == "Yes"
    assert page.evaluate("() => document.getElementById('resume').files[0].name") == "alex-rivera.pdf"
    assert page.input_value("#why") == "", "no saved answer and no LLM: left empty"
    assert page.input_value("#gender") == "", "demographic question left for the user"
    assert not page.is_checked("#consent"), "consent is never ticked"
    decisions, results, report = api.filled_calls[0]
    assert report["blocked_submits"] == 0 and report["captcha"] is False
    assert all(r["ok"] for r in results.values())
    assert api.submitted_calls == []

    # The user reviews in the browser: answers the open question, corrects a
    # field, ticks consent, and submits.
    page.fill("#why", "I want to work on ledgers.")
    page.fill("#first_name", "Alexander")
    page.check("#consent")
    tick_until(worker, lambda: api.snapshots and api.snapshots[-1].get("textarea:why"))
    assert api.snapshots[-1]["text:first_name"] == "Alexander"
    page.fill("#why", "I want to work on ledgers and payments.")   # a last-second edit
    page.click("#go")
    page.wait_for_url("**/confirmation.html")
    tick_until(worker, lambda: api.submitted_calls)

    values, screenshot = api.submitted_calls[0]
    assert values["textarea:why"] == "I want to work on ledgers and payments.", \
        "the answers recorded are the ones on the form when submit was pressed"
    assert values["text:first_name"] == "Alexander"
    assert values["checkbox:consent"] == "yes"
    assert screenshot[:8] == b"\x89PNG\r\n\x1a\n", "confirmation screenshot captured"
    assert worker.sessions == [] and api.released_calls == []


def test_closing_the_tab_releases_the_application(worker, site):
    worker._open(task(site))
    session = worker.sessions[0]
    tick_until(worker, lambda: session.state == "paused")
    session.page.close()
    tick_until(worker, lambda: worker.api.released_calls)
    reason, needs_manual = worker.api.released_calls[0]
    assert "closed before the application was submitted" in reason and not needs_manual
    assert worker.api.submitted_calls == [] and worker.sessions == []


def test_dead_posting_goes_to_the_manual_queue(worker, site):
    worker._open(task(site, "closed.html"))
    tick_until(worker, lambda: worker.api.released_calls)
    reason, needs_manual = worker.api.released_calls[0]
    assert needs_manual and "closed" in reason
    assert worker.api.filled_calls == []


def test_http_error_goes_to_the_manual_queue(worker, site):
    worker._open(task(site, "missing.html"))
    assert worker.api.released_calls == [("The application page returned HTTP 404.", True)]
    assert worker.sessions == []


def test_cancel_from_the_dashboard_stops_the_session(worker, site):
    worker._open(task(site))
    session = worker.sessions[0]
    tick_until(worker, lambda: session.state == "paused")
    worker.api.task_state = "cancelled"
    session.last_beat = 0
    worker._tick(session)
    assert worker.sessions == [] and session.page.is_closed()
    assert worker.api.submitted_calls == []


def test_unsupported_ats_is_never_opened(worker, site):
    t = task(site)
    t["posting"]["ats_type"] = "workday"
    worker._open(t)
    assert worker.sessions == []
    assert worker.api.released_calls == [("No apply adapter for workday.", True)]

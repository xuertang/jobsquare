"""Whole system over real HTTP: the FastAPI app served by uvicorn, the real
worker client, a real (headless) browser, and a local application form.

approve -> launch -> worker fills and pauses -> user edits and submits ->
application recorded with final answers, screenshot, and a fed answer bank."""
import socket
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

pytest.importorskip("playwright.sync_api")
import uvicorn  # noqa: E402

from copilot import config, db  # noqa: E402
from copilot.main import create_app  # noqa: E402
from tests.conftest import add_posting  # noqa: E402
from tests.test_worker import Quiet, tick_until  # noqa: E402
from worker.runner import Worker  # noqa: E402

pytestmark = pytest.mark.browser
FLOW = Path(__file__).parent / "fixtures" / "flow"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def stack(db_path, tmp_path):
    site = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(FLOW)))
    threading.Thread(target=site.serve_forever, daemon=True).start()
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(db_path, scheduler=False),
                                           host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    api_url = f"http://127.0.0.1:{port}"
    try:
        worker = Worker(api_url, tmp_path / "worker-data", headless=True)
        worker._browser()
    except Exception as e:  # noqa: BLE001
        server.should_exit = True
        site.shutdown()
        pytest.skip(f"Chromium is not installed: {e}")
    yield httpx.Client(base_url=f"{api_url}/api", timeout=30), worker, \
        f"http://127.0.0.1:{site.server_address[1]}"
    worker.sessions.clear()
    worker._close_browser()
    if worker._pw:
        worker._pw.stop()
    server.should_exit = True
    site.shutdown()


def test_approve_fill_review_submit_over_http(stack, db_path):
    http, worker, site = stack
    with db.session(db_path) as conn:
        pid = add_posting(conn)
        conn.execute("UPDATE postings SET apply_url = ? WHERE id = ?",
                     (f"{site}/apply.html", pid))
    http.put("/settings/profile", json={
        "contact": {"first_name": "Alex", "last_name": "Rivera", "email": "alex@example.com"},
        "work_auth": {"authorized": "yes", "requires_sponsorship": "no"}}).raise_for_status()
    http.post("/settings/resumes", data={"label": "General"},
              files={"file": ("alex-rivera.txt", b"Alex Rivera. Ledgers.", "text/plain")})
    http.post("/settings/answers", json={"question": "Why do you want to work here?",
                                         "answer": "Saved answer about ledgers."})

    match = http.get("/matches").json()["matches"][0]
    app = http.post(f"/matches/{match['id']}/approve").json()
    assert worker.api.claim() is None, "approved is not launched: nothing for the worker yet"
    http.post(f"/applications/{app['id']}/launch").raise_for_status()

    task = worker.api.claim()
    assert task["application_id"] == app["id"]
    assert http.get("/status").json()["worker"]["running"] is True
    worker._open(task)
    session = worker.sessions[0]
    tick_until(worker, lambda: session.state == "paused")
    page = session.page

    detail = http.get(f"/applications/{app['id']}").json()
    assert detail["state"] == "paused"
    answers = {a["question"]: a for a in detail["answers"]}
    assert answers["First Name"]["answer"] == "Alex" and answers["First Name"]["source"] == "profile"
    assert answers["Resume/CV"]["answer"] == "General"
    assert answers["Are you legally authorized to work in the United States?"]["answer"] == "Yes"
    why = answers["Why do you want to work at Acme?"]
    assert why["answer"] == "Saved answer about ledgers." and why["source"] == "bank"
    assert not why["flagged"] and why["confidence"] == 1.0, \
        "the same question once the employer's name is removed: reused with full confidence"
    assert answers["Gender"]["status"] == "unfilled"
    assert answers["I agree to the privacy policy"]["status"] == "unfilled"
    assert page.input_value("#why") == "Saved answer about ledgers."
    assert page.evaluate("() => document.getElementById('resume').files[0].name") == "alex-rivera.txt"
    assert page.url.endswith("/apply.html"), "filled and stopped; not submitted"

    # The user improves the reused answer, ticks consent, and submits.
    page.fill("#why", "I want to build ledgers at Acme.")
    page.check("#consent")
    page.click("#go")
    page.wait_for_url("**/confirmation.html")
    tick_until(worker, lambda: not worker.sessions)

    done = http.get(f"/applications/{app['id']}").json()
    assert done["state"] == "submitted" and done["submitted_at"]
    final = {a["question"]: a for a in done["answers"]}
    assert final["Why do you want to work at Acme?"]["answer"] == "I want to build ledgers at Acme."
    assert final["Why do you want to work at Acme?"]["edited"]
    assert final["I agree to the privacy policy"]["answer"] == "yes"
    shot = http.get(f"/applications/{app['id']}/screenshot")
    assert shot.status_code == 200 and shot.content[:4] == b"\x89PNG"
    assert (config.DATA_DIR / done["screenshot_path"]).is_file()
    bank = http.get("/settings/answers").json()
    assert any(e["answer"] == "I want to build ledgers at Acme." for e in bank), \
        "the edited answer is saved back to the bank"
    assert http.get("/applications?scope=queue").json() == []
    assert worker.api.claim() is None

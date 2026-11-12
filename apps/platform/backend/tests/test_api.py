"""End-to-end through the HTTP API, including the worker protocol."""
import io
import json

from copilot import config, db, repo
from tests.conftest import add_posting
from tests.test_referrals import EXPORT


def seed_posting(db_path, **kw):
    with db.session(db_path) as conn:
        return add_posting(conn, **kw)


def test_status_and_empty_views(client):
    status = client.get("/api/status").json()
    assert status["llm"] == {"available": False, "model": "claude-opus-5-5"}
    assert status["scheduler"]["enabled"] is False
    assert client.get("/api/matches").json()["matches"] == []
    assert client.get("/api/applications").json() == []
    assert client.get("/api/outreach").json()["companies"] == []


def test_match_actions(client, db_path):
    pid = seed_posting(db_path)
    match = client.get("/api/matches").json()["matches"][0]
    assert match["posting_id"] == pid and match["score"] is None and match["contacts"] == 0

    assert client.post(f"/api/matches/{match['id']}/snooze", json={"days": 3}).json()["state"] == "snoozed"
    assert client.get("/api/matches").json()["matches"] == []
    assert len(client.get("/api/matches?state=snoozed").json()["matches"]) == 1
    client.post(f"/api/matches/{match['id']}/restore")
    client.post(f"/api/matches/{match['id']}/dismiss")
    assert client.get("/api/matches").json()["counts"]["dismissed"] == 1
    client.post(f"/api/matches/{match['id']}/restore")
    assert client.post(f"/api/matches/{match['id']}/rescore").status_code == 409  # no LLM


def test_assisted_apply_flow_through_the_worker_protocol(client, db_path):
    seed_posting(db_path)
    client.put("/api/settings/profile", json={
        "contact": {"first_name": "Alex", "last_name": "Rivera", "email": "alex@example.com"},
        "work_auth": {"authorized": "yes", "requires_sponsorship": "no"}})
    resume = client.post("/api/settings/resumes", data={"label": "General"},
                         files={"file": ("cv.txt", b"Alex Rivera. Built ledgers.", "text/plain")}).json()
    assert resume["has_file"] and resume["is_default"] and "ledgers" in resume["text"]

    match = client.get("/api/matches").json()["matches"][0]
    app = client.post(f"/api/matches/{match['id']}/approve").json()
    assert app["state"] == "waiting" and app["resume_variant"] == "General"

    # Nothing is handed to the worker until the user launches the fill.
    assert client.post("/api/worker/claim").json() == {"task": None}
    assert client.post(f"/api/applications/{app['id']}/launch").json()["fill_task"]["state"] == "queued"
    task = client.post("/api/worker/claim").json()["task"]
    assert task["application_id"] == app["id"]
    assert task["posting"]["apply_url"].startswith("https://job-boards.greenhouse.io/acme/")
    assert task["resume"] == {"id": resume["id"], "filename": "cv.txt"}
    assert client.get(f"/api/applications/{app['id']}").json()["state"] == "filling"
    assert client.get(f"/api/worker/resumes/{resume['id']}/file").content == b"Alex Rivera. Built ledgers."

    fields = [
        {"key": "f0", "label": "First Name", "type": "text"},
        {"key": "f1", "label": "Resume/CV", "type": "file"},
        {"key": "f2", "label": "Why do you want to work at Acme?", "type": "textarea"},
        {"key": "f3", "label": "I agree to the Privacy Policy", "type": "checkbox"},
    ]
    decisions = client.post(f"/api/worker/applications/{app['id']}/plan",
                            json={"fields": fields}).json()["decisions"]
    assert [(d["action"], d["value"]) for d in decisions] == [
        ("fill", "Alex"), ("fill", "General"), ("skip", ""), ("skip", "")]
    report = client.post(f"/api/worker/applications/{app['id']}/filled", json={
        "decisions": decisions, "results": {"f0": {"ok": True}, "f1": {"ok": True}},
        "report": {"captcha": False}}).json()
    assert report["unfilled"] == 2
    queue = client.get("/api/applications").json()
    assert queue[0]["state"] == "paused" and queue[0]["unfilled_count"] == 2

    assert client.post(f"/api/worker/tasks/{task['id']}/heartbeat").json() == {"state": "running"}
    client.post(f"/api/worker/applications/{app['id']}/snapshot",
                json={"f2": "I like ledgers."})
    done = client.post(f"/api/worker/applications/{app['id']}/submitted",
                       data={"values": json.dumps({"f2": "I like ledgers and payments."})},
                       files={"screenshot": ("c.png", b"\x89PNG fake", "image/png")}).json()
    assert done == {"bank_saved": 1}

    assert client.get("/api/applications").json() == []
    submitted = client.get("/api/applications?scope=submitted").json()[0]
    assert submitted["state"] == "submitted" and submitted["status"] == "applied"
    assert client.get(f"/api/applications/{app['id']}/screenshot").content == b"\x89PNG fake"
    detail = client.get(f"/api/applications/{app['id']}").json()
    answer = next(a for a in detail["answers"] if a["field_key"] == "f2")
    assert answer["answer"] == "I like ledgers and payments." and answer["edited"]
    assert client.get("/api/settings/answers").json()[0]["answer"] == "I like ledgers and payments."
    assert client.post("/api/worker/claim").json() == {"task": None}

    # Tracking: status and notes.
    patched = client.patch(f"/api/applications/{app['id']}",
                           json={"status": "screen", "notes": "Recruiter call Tuesday"}).json()
    assert patched["status"] == "screen" and patched["notes"] == "Recruiter call Tuesday"
    assert client.delete(f"/api/applications/{app['id']}").status_code == 409


def test_worker_release_and_withdraw(client, db_path):
    seed_posting(db_path)
    match = client.get("/api/matches").json()["matches"][0]
    app = client.post(f"/api/matches/{match['id']}/approve").json()
    client.post(f"/api/applications/{app['id']}/launch")
    task = client.post("/api/worker/claim").json()["task"]
    out = client.post(f"/api/worker/applications/{app['id']}/released", json={
        "reason": "CAPTCHA wall before the form", "needs_manual": True,
        "task_id": task["id"]}).json()
    assert out == {"state": "needs_manual"}
    detail = client.get(f"/api/applications/{app['id']}").json()
    assert detail["manual_reason"] == "CAPTCHA wall before the form"
    # Manual queue: paste a question, get an answer row back (unfilled without an LLM).
    row = client.post(f"/api/applications/{app['id']}/answers",
                      json={"question": "Why Acme?"}).json()
    assert row["status"] == "unfilled"
    edited = client.patch(f"/api/applications/{app['id']}/answers/{row['id']}",
                          json={"answer": "Ledgers."}).json()
    assert edited["status"] == "filled" and edited["source"] == "manual"
    assert client.delete(f"/api/applications/{app['id']}").json() == {"ok": True}
    assert client.get("/api/matches").json()["matches"][0]["state"] == "new"


def test_outreach_flow(client, db_path):
    pid = seed_posting(db_path)
    out = client.post("/api/contacts/import",
                      files={"file": ("Connections.csv", EXPORT.encode(), "text/csv")}).json()
    assert out == {"rows": 3, "created": 3, "updated": 0}
    assert client.post("/api/contacts/import",
                       files={"file": ("x.csv", b"a,b\n1,2\n", "text/csv")}).status_code == 400
    assert client.get("/api/matches").json()["matches"][0]["contacts"] == 2

    detail = client.get(f"/api/postings/{pid}").json()
    assert [c["name"] for c in detail["contacts"]] == ["Dana Okafor", "Sam Lee"]
    assert detail["search_links"][-1]["label"] == "My connections at Acme"
    dana = detail["contacts"][0]

    # Second-degree target pasted in by hand.
    target = client.post("/api/contacts", json={
        "name": "Jo Hiring", "company": "Acme", "title": "Engineering Manager",
        "profile_url": "https://www.linkedin.com/in/jo/", "relationship_type": "hiring_team"}).json()
    assert target["source"] == "manual" and target["profile_url"].endswith("/in/jo")

    draft = client.post("/api/messages/draft",
                        json={"contact_id": dana["id"], "posting_id": pid}).json()
    assert draft["source"] == "template" and draft["body"].startswith("Hi Dana,")
    edited = client.patch(f"/api/messages/{draft['id']}", json={"body": "Hi Dana, quick ask."}).json()
    assert edited["body"] == "Hi Dana, quick ask." and edited["problems"] == []
    sent = client.post(f"/api/messages/{draft['id']}/sent").json()
    assert sent["sent_at"]
    assert client.patch(f"/api/messages/{draft['id']}", json={"body": "x"}).status_code == 409

    reply = client.post(f"/api/contacts/{dana['id']}/reply", json={
        "posting_id": pid, "body": "Happy to refer you.", "outcome": "referred"}).json()
    assert reply["direction"] == "in" and reply["outcome"] == "referred"

    board = client.get("/api/outreach").json()
    group = board["companies"][0]
    assert group["company"] == "Acme" and group["postings"][0]["id"] == pid
    statuses = {c["name"]: c["status"] for c in group["contacts"]}
    assert statuses == {"Dana Okafor": "referred", "Sam Lee": "none", "Jo Hiring": "none"}
    assert [m["direction"] for m in board["log"]] == ["in", "out"]
    assert board["followups"] == []


def test_settings_roundtrip(client, db_path):
    crit = client.get("/api/settings/criteria").json()
    assert "(Multiple Positions)" in crit["search"]["title_exclude"]
    assert crit["app"]["daily_apply_cap"] == 0
    saved = client.put("/api/settings/criteria", json={
        "search": {"levels": ["senior"]}, "app": {"followup_days": "5"}}).json()
    assert saved["search"]["levels"] == ["senior"] and saved["app"]["followup_days"] == 5
    assert client.put("/api/settings/criteria", json={"search": {"levels": ["wizard"]}}).status_code == 400
    assert client.put("/api/settings/criteria", json={"app": {"fetch_hour": 30}}).status_code == 400
    with db.session(db_path) as conn:     # saving criteria queues a re-filter
        assert repo.active_task(conn, "refilter")["kind"] == "refilter"

    assert client.put("/api/settings/profile", json={"nope": {}}).status_code == 400
    assert client.put("/api/settings/profile", json={"contact": []}).status_code == 400

    bank = client.post("/api/settings/answers", json={
        "question": "Why do you want to work here?", "answer": "Ledgers."}).json()
    assert "embedding" not in bank
    client.patch(f"/api/settings/answers/{bank['id']}",
                 json={"question": "Why here?", "answer": "Payments."})
    assert client.get("/api/settings/answers").json()[0]["answer"] == "Payments."

    added = client.post("/api/settings/companies", json={
        "name": "Globex", "ats_type": "lever", "board_token": "globex"})
    assert added.status_code == 200
    assert client.post("/api/settings/companies", json={
        "name": "Globex", "ats_type": "lever", "board_token": "globex"}).status_code == 409
    assert client.post("/api/settings/companies", json={
        "name": "LinkedIn", "ats_type": "linkedin", "board_token": "1337"}).status_code == 400
    assert client.post("/api/settings/companies", json={
        "name": "WD", "ats_type": "workday", "board_token": "https://x"}).status_code == 400
    cid = added.json()["id"]
    assert client.patch(f"/api/settings/companies/{cid}", json={"active": False}).json()["active"] is False

    export = client.get("/api/settings/export").json()
    assert {c["name"] for c in export["companies"]} == {"Acme", "Globex"}
    assert export["answer_bank"] == [{"question": "Why here?", "answer": "Payments."}]
    client.delete(f"/api/settings/companies/{cid}")
    client.delete(f"/api/settings/answers/{bank['id']}")
    assert client.post("/api/settings/import", json=export).json() == {
        "criteria": 2, "profile": 9, "answer_bank": 1, "companies": 1, "contacts": 0}


def test_resume_upload_rejects_unknown_types_and_deletes_files(client):
    bad = client.post("/api/settings/resumes", data={"label": "x"},
                      files={"file": ("cv.exe", b"MZ", "application/octet-stream")})
    assert bad.status_code == 400
    ok = client.post("/api/settings/resumes", data={"label": "Payments", "keywords": "payments"},
                     files={"file": ("../../cv final.md", b"# Alex", "text/markdown")}).json()
    stored = list(config.RESUME_DIR.iterdir())
    assert len(stored) == 1 and stored[0].parent == config.RESUME_DIR
    assert "path" not in ok
    client.delete(f"/api/settings/resumes/{ok['id']}")
    assert list(config.RESUME_DIR.iterdir()) == []


def test_manual_task_trigger(client, db_path):
    out = client.post("/api/run/fetch").json()
    assert out["created"] and out["task"]["state"] == "queued"
    assert client.post("/api/run/fetch").json()["created"] is False
    assert client.post("/api/run/nonsense").status_code == 400
    assert client.get("/api/tasks").json()[0]["kind"] == "fetch"

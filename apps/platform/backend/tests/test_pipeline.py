from types import SimpleNamespace

import pytest

from copilot import config, db, digest, llm, normalize, pipeline, repo, scraper, tasks
from copilot.scoring import Score
from tests.conftest import add_posting

Job = scraper.modules().models.Job


def job(ext, title="Software Engineer", location="San Francisco, CA", source="greenhouse",
        **raw):
    return Job(source=source, company="acme", external_id=str(ext), title=title,
               url=f"https://example.com/{ext}", location=location, raw=raw)


def company(conn):
    return repo.get_company(conn, 1)


# ------------------------------------------------------------- normalize ---
def test_normalize_greenhouse_uses_hosted_board_for_apply():
    row = normalize.normalize(job(77, requisition_id="REQ-12"))
    assert row["apply_url"] == (
        "https://job-boards.greenhouse.io/embed/job_app?for=acme&token=77")
    assert row["requisition_id"] == "REQ-12"
    assert row["ats_type"] == "greenhouse" and row["remote"] == 0


def test_requisition_placeholder_is_dropped():
    assert normalize.normalize(job(1, requisition_id="See Opening ID"))["requisition_id"] == ""


def test_normalize_lever_and_ashby_carry_description_and_apply_url():
    lever = Job(source="lever", company="acme", external_id="a", title="SWE",
                url="https://jobs.lever.co/acme/a", location="Remote",
                raw={"descriptionPlain": "Build things.", "workplaceType": "remote",
                     "lists": [{"text": "You have", "content": "<li>Python</li>"}]})
    row = normalize.normalize(lever)
    assert row["apply_url"] == "https://jobs.lever.co/acme/a/apply"
    assert "Build things." in row["description"] and "- Python" in row["description"]
    assert row["remote"] == 1

    ashby = Job(source="ashby", company="acme", external_id="b", title="SWE",
                url="https://jobs.ashbyhq.com/acme/b", location="San Francisco",
                raw={"descriptionPlain": "About the team", "isRemote": True,
                     "workplaceType": "Hybrid",
                     "secondaryLocations": [{"location": "New York"}]})
    row = normalize.normalize(ashby)
    assert row["apply_url"] == "https://jobs.ashbyhq.com/acme/b/application"
    assert row["location"] == "San Francisco; New York"
    assert row["remote"] == 0, "workplaceType wins over the unreliable isRemote flag"


def test_html_to_text():
    text = normalize.html_to_text("<p>Hello&nbsp;<b>world</b></p><ul><li>one</li><li>two</li></ul>"
                                  "<script>x()</script>")
    assert text == "Hello world\n\n- one\n- two"


def test_out_of_scope_sources_are_never_seeded():
    assert scraper.company_from_source({"ats": "linkedin", "company": "1337"}) is None
    assert scraper.company_from_source({"ats": "google", "query": "swe"}) is None
    wd = scraper.company_from_source({"ats": "workday", "company": "nvidia",
                                      "host": "nvidia.wd5.myworkdayjobs.com",
                                      "tenant": "nvidia", "site": "Ext"})
    assert wd["board_token"] == "https://nvidia.wd5.myworkdayjobs.com/en-US/Ext"
    assert scraper.source_for({"ats_type": "workday", "name": "Nvidia", **wd})["tenant"] == "nvidia"


# ------------------------------------------------------------ store_fetch ---
def test_store_fetch_dedups_and_closes(conn):
    out = pipeline.store_fetch(conn, company(conn), [job(1), job(2), job(2)], "")
    assert out == {"status": "ok", "new": 2, "closed": 0}
    out = pipeline.store_fetch(conn, company(conn), [job(2), job(3)], "")
    assert out == {"status": "ok", "new": 1, "closed": 1}
    rows = {r["external_id"]: r["closed"] for r in conn.execute("SELECT * FROM postings")}
    assert rows == {"1": 1, "2": 0, "3": 0}
    # A posting that comes back is reopened.
    pipeline.store_fetch(conn, company(conn), [job(1), job(2), job(3)], "")
    assert conn.execute("SELECT closed FROM postings WHERE external_id='1'").fetchone()[0] == 0


def test_empty_board_is_flagged_not_closed(conn):
    """A quiet zero looks exactly like a migrated or throttled board."""
    pipeline.store_fetch(conn, company(conn), [job(i) for i in range(5)], "")
    out = pipeline.store_fetch(conn, company(conn), [], "")
    assert out["status"] == "empty"
    assert conn.execute("SELECT COUNT(*) FROM postings WHERE closed = 0").fetchone()[0] == 5
    c = company(conn)
    assert c["last_status"] == "empty" and c["failures"] == 1 and "moved" in c["last_error"]


def test_shrunken_board_defers_closures_until_confirmed(conn):
    pipeline.store_fetch(conn, company(conn), [job(i) for i in range(20)], "")
    out = pipeline.store_fetch(conn, company(conn), [job(i) for i in range(3)], "")
    assert out["status"] == "suspect" and out["closed"] == 0
    out = pipeline.store_fetch(conn, company(conn), [job(i) for i in range(3)], "")
    assert out == {"status": "ok", "new": 0, "closed": 17}


def test_failed_fetch_is_recorded(conn):
    pipeline.store_fetch(conn, company(conn), [], "HTTPStatusError: 404")
    c = company(conn)
    assert c["last_status"] == "failed" and "404" in c["last_error"]


def test_refilter_creates_and_hides_matches(conn):
    pipeline.store_fetch(conn, company(conn), [
        job(1, "Senior Software Engineer"), job(2, "Account Executive"),
        job(3, "Software Engineer", "Berlin")], "")
    stats = pipeline.refilter(conn)
    assert stats["passed"] == 1 and stats["new_matches"] == 1
    assert stats["rejected_title"] == 1 and stats["rejected_location"] == 1
    assert [m["title"] for m in repo.list_matches(conn)] == ["Senior Software Engineer"]
    # Tighten the criteria: the match is hidden, not deleted, so a cached
    # score survives if the criteria are loosened again.
    repo.set_config(conn, "criteria", "search", {"levels": ["mid"]})
    pipeline.refilter(conn)
    assert repo.list_matches(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 1


# ---------------------------------------------------------------- scoring ---
def test_scoring_is_skipped_without_credentials(db_path, conn):
    add_posting(conn)
    conn.commit()
    out = pipeline.run_score(db_path)
    assert out["scored"] == 0 and "unscored" in out["skipped"]


def test_score_is_cached_per_posting(db_path, fake_llm):
    with db.session(db_path) as conn:
        add_posting(conn, external_id="1")
        add_posting(conn, external_id="2", title="Backend Engineer")
    fake = fake_llm(parsed=Score(score=140, rationale="Strong — fit\nGap: Go\nextra"))
    assert pipeline.run_score(db_path) == {"scored": 2, "failed": 0, "remaining": 0}
    with db.session(db_path) as conn:
        m = repo.list_matches(conn)[0]
    assert m["score"] == 100, "scores are clamped to 0-100"
    assert m["rationale"] == "Strong, fit\nGap: Go", "two lines, no em dashes"
    assert m["score_model"] == config.MODEL
    assert len(fake.calls) == 2
    assert pipeline.run_score(db_path)["scored"] == 0
    assert len(fake.calls) == 2, "a scored posting is never sent again"


def test_score_cap_limits_a_run(db_path, fake_llm):
    with db.session(db_path) as conn:
        for i in range(5):
            add_posting(conn, external_id=str(i))
    fake_llm(parsed=Score(score=70, rationale="a\nb"))
    out = pipeline.run_score(db_path, limit=2)
    assert out["scored"] == 2 and out["remaining"] == 3


def test_refusal_is_recorded_and_does_not_stop_the_run(db_path, fake_llm):
    with db.session(db_path) as conn:
        add_posting(conn)
    fake_llm(parsed=None, stop_reason="refusal")
    out = pipeline.run_score(db_path)
    assert out["scored"] == 0 and out["failed"] == 1
    with db.session(db_path) as conn:
        assert "declined" in repo.list_matches(conn)[0]["score_error"]


# ----------------------------------------------------------------- digest ---
def test_digest_links_into_the_dashboard(db_path, monkeypatch):
    with db.session(db_path) as conn:
        hi = add_posting(conn, external_id="1")
        lo = add_posting(conn, external_id="2", title="Backend Engineer")
        repo.set_score(conn, repo.match_for_posting(conn, hi)["id"], 91, "a\nb", "m")
        repo.set_score(conn, repo.match_for_posting(conn, lo)["id"], 40, "a\nb", "m")
    sent = []
    monkeypatch.setattr(scraper.modules().notify, "dispatch",
                        lambda new, changed: sent.append((new, changed)))
    assert digest.run_digest(db_path) == {"sent": 1}
    (new, changed), = sent
    assert changed == [] and new[0].title.startswith("[91] ")
    assert new[0].url == f"{config.DASHBOARD_URL}/postings/{hi}"
    assert digest.run_digest(db_path) == {"sent": 0}, "a match is only announced once"


# ------------------------------------------------------------------ tasks ---
def test_task_queue_dedupes_runs_and_recovers(db_path, monkeypatch):
    monkeypatch.setitem(tasks.HANDLERS, "fetch", lambda p, payload: {"ran": payload})
    with db.session(db_path) as conn:
        first, created = repo.enqueue(conn, "fetch", {"company_ids": [1]}, dedupe_key="fetch")
        again, created_again = repo.enqueue(conn, "fetch", dedupe_key="fetch")
        assert created and not created_again and first == again
    assert tasks.run_pending(db_path) == 1
    with db.session(db_path) as conn:
        t = repo.get_task(conn, first)
        assert t["state"] == "done" and t["result"] == {"ran": {"company_ids": [1]}}
        # A task left 'running' by a crash goes back on the queue at startup.
        tid, _ = repo.enqueue(conn, "fetch")
        repo.claim_task(conn, ["fetch"])
        assert repo.recover_tasks(conn, tasks.IN_PROCESS) == 1
        assert repo.get_task(conn, tid)["state"] == "queued"


def test_failing_task_is_recorded_not_raised(db_path, monkeypatch):
    def boom(p, payload):
        raise RuntimeError("board exploded")
    monkeypatch.setitem(tasks.HANDLERS, "fetch", boom)
    with db.session(db_path) as conn:
        tid, _ = repo.enqueue(conn, "fetch")
    tasks.run_pending(db_path)
    with db.session(db_path) as conn:
        t = repo.get_task(conn, tid)
    assert t["state"] == "failed" and "board exploded" in t["error"]


# -------------------------------------------------------------------- llm ---
def test_llm_request_shape(fake_llm):
    fake = fake_llm(parsed=Score(score=1, rationale="x"))
    system = llm.system_blocks("instructions", "<resume>stable</resume>")
    llm.structured(system, "posting", Score, effort="low")
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["output_config"] == {"effort": "low"}
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_format"] is Score
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "temperature" not in call
    # The per-posting part is the user turn, after the cached prefix.
    assert call["messages"] == [{"role": "user", "content": "posting"}]


def test_llm_refusal_and_unavailable(fake_llm, monkeypatch):
    fake_llm(parsed=None, stop_reason="refusal")
    with pytest.raises(llm.LLMRefused):
        llm.structured([], "x", Score)
    monkeypatch.setenv("COPILOT_LLM", "off")
    with pytest.raises(llm.LLMUnavailable):
        llm.client()


def test_redact_and_plain():
    text = llm.redact("Alex Rivera | alex.r+jobs@example.com | +1 (415) 555-0199 | 7 years")
    assert "example.com" not in text and "555" not in text and "7 years" in text
    assert llm.plain("Great team — strong fit – really") == "Great team, strong fit, really"


# ------------------------------------------------------------ display names ---
def test_slug_names_are_replaced_once_and_hand_edits_survive(db_path, monkeypatch):
    """'janestreet' becomes 'Jane Street' on the first fetch. A name set in
    Settings carries no auto flag, so it is never overwritten."""
    with db.session(db_path) as conn:
        fields = scraper.company_from_source({"ats": "greenhouse", "company": "janestreet"})
        assert fields["name"] == "Janestreet" and fields["board_config"]["_auto_name"]
        auto, _ = repo.upsert_company(conn, **fields)
        manual, _ = repo.upsert_company(conn, name="My Name", ats_type="lever", board_token="acme2")
        companies = repo.list_companies(conn)
    asked = []

    async def fake_names(todo):
        asked.extend(c["board_token"] for c in todo)
        return {auto: "Jane Street"}
    monkeypatch.setattr(pipeline, "_resolve_names", fake_names)
    assert pipeline.resolve_names(db_path, companies) == 1
    assert asked == ["janestreet"], "only auto-named boards are looked up"
    with db.session(db_path) as conn:
        c = repo.get_company(conn, auto)
        assert c["name"] == "Jane Street" and "_auto_name" not in c["board_config"]
        assert repo.get_company(conn, manual)["name"] == "My Name"
        assert "_auto_name" not in scraper.source_for(c)
        assert pipeline.resolve_names(db_path, repo.list_companies(conn)) == 0

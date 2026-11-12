"""Shared fixtures. Every test gets its own database and data directory, the
scheduler stays off, and no test reaches the network or the Claude API."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from copilot import config, db, llm, repo, seed  # noqa: E402


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "DB_PATH", data / "copilot.db")
    monkeypatch.setattr(config, "RESUME_DIR", data / "resumes")
    monkeypatch.setattr(config, "SCREENSHOT_DIR", data / "screenshots")
    monkeypatch.setenv("COPILOT_LLM", "off")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    llm.set_client(None)
    config.ensure_dirs()
    yield
    llm.set_client(None)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "data" / "copilot.db"
    db.init(path)
    with db.session(path) as conn:
        # Seed config only; tests add the companies they need.
        repo.upsert_company(conn, name="Acme", ats_type="greenhouse", board_token="acme")
        seed.seed_defaults(conn)
        # Deterministic criteria: do not inherit the user's sources.yaml filters.
        repo.set_config(conn, "criteria", "search", dict(seed.DEFAULT_SEARCH))
    return path


@pytest.fixture
def conn(db_path):
    with db.session(db_path) as c:
        yield c


@pytest.fixture
def client(db_path):
    from fastapi.testclient import TestClient

    from copilot.main import create_app
    with TestClient(create_app(db_path, scheduler=False)) as c:
        yield c


@pytest.fixture
def profile():
    p = copy.deepcopy(seed.DEFAULT_PROFILE)
    p["contact"].update(first_name="Alex", last_name="Rivera", email="alex@example.com",
                        phone="+1 415 555 0199", city="Los Angeles", state="California",
                        zip="90012", country="United States")
    p["links"].update(linkedin="https://linkedin.com/in/alexrivera",
                      github="https://github.com/alexrivera")
    p["work_auth"].update(authorized="yes", requires_sponsorship="no")
    p["extras"].update(current_company="Initech", current_title="Senior Software Engineer",
                       years_experience="7", how_heard="LinkedIn")
    p["work_history"] = [{"company": "Initech", "title": "Senior Software Engineer",
                          "start": "2021-03", "end": "Present", "description": "Payments."},
                         {"company": "Globex", "title": "Software Engineer",
                          "start": "2017-06", "end": "2021-02", "description": "Search."}]
    p["education"] = [{"school": "UCLA", "degree": "Bachelor of Science",
                       "field": "Computer Science", "start": "2013", "end": "2017"}]
    return p


def add_posting(conn, *, title="Senior Software Engineer, Backend", company_id=1,
                external_id="1001", location="San Francisco, CA", ats_type="greenhouse",
                requisition_id="", remote=0, description="Build payment systems.",
                match=True) -> int:
    ids = repo.upsert_postings(conn, company_id, [{
        "external_id": external_id, "requisition_id": requisition_id, "title": title,
        "location": location, "remote": remote, "department": "Engineering",
        "employment_type": "", "salary_range": "", "url": f"https://example.com/{external_id}",
        "apply_url": f"https://job-boards.greenhouse.io/acme/jobs/{external_id}",
        "ats_type": ats_type, "posted_at": db.now(), "description": description}])
    if match:
        repo.sync_match(conn, ids[0], True)
    return ids[0]


class FakeMessages:
    """Stands in for client.beta.messages. Records every call."""

    def __init__(self, parsed=None, text="", stop_reason="end_turn"):
        self.parsed, self.text_out, self.stop_reason = parsed, text, stop_reason
        self.calls: list[dict] = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        parsed = self.parsed(kwargs) if callable(self.parsed) else self.parsed
        return SimpleNamespace(stop_reason=self.stop_reason, parsed_output=parsed)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        body = self.text_out(kwargs) if callable(self.text_out) else self.text_out
        return SimpleNamespace(stop_reason=self.stop_reason,
                               content=[SimpleNamespace(type="text", text=body)])


@pytest.fixture
def fake_llm(monkeypatch):
    """Turn the LLM 'on' with a fake client; returns the fake messages API."""
    def install(**kwargs) -> FakeMessages:
        fake = FakeMessages(**kwargs)
        monkeypatch.setenv("COPILOT_LLM", "on")
        llm.set_client(SimpleNamespace(beta=SimpleNamespace(messages=fake)))
        return fake
    return install

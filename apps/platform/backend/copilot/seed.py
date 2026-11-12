"""First-run defaults: criteria, app settings, an empty profile, and the
company list from the scraper's sources.yaml."""
from __future__ import annotations

import yaml

from . import config, repo, scraper

CA_PLACES = [
    "California", "Bay Area", "San Francisco", "South San Francisco", "Los Angeles",
    "San Jose", "San Diego", "Sunnyvale", "Mountain View", "Palo Alto", "Menlo Park",
    "Santa Clara", "Cupertino", "Redwood City", "San Mateo", "Foster City", "Oakland",
    "Berkeley", "Fremont", "Irvine", "Santa Monica", "Culver City", "El Segundo",
    "Pasadena", "Burlingame", "Los Gatos", "San Bruno", "Santa Barbara", "Sacramento",
]

DEFAULT_SEARCH = {
    "title_include": ["software engineer", "backend", "back end", "full stack",
                      "distributed systems"],
    # "(Multiple Positions)" marks a PERM labor-certification filing, not an opening.
    "title_exclude": ["android", "ios", "embedded", "quantum", "(Multiple Positions)"],
    "levels": ["entry", "mid", "senior", "lead"],
    "locations": CA_PLACES,
    "remote_ok": True,
    "remote_regions": ["United States", "USA", "US", "U.S.", "North America", "Americas"],
    "excluded_companies": [],
    "max_age_days": 14,
    "preferences": ("Open to roles based in California, or US-remote roles that accept "
                    "California residents. Weigh the level and the stack against my "
                    "resume. A posting that reads like a visa labor-certification "
                    "filing rather than an open role should score low."),
}

DEFAULT_APP = {
    "fetch_hour": 7,                 # local time, daily
    "fetch_minute": 30,
    "max_scores_per_run": 100,       # cost guard for the scoring step
    "description_chars": 6000,       # how much of a description the model sees
    "digest_min_score": 70,
    "followup_days": 7,
    "max_followups": 1,
    "char_cap_message": 800,         # first-degree message
    "char_cap_connection_note": 300, # second-degree connection request note
    "daily_apply_cap": 0,            # 0 = no cap
    "bank_match": 0.78,              # similarity needed to reuse a saved answer
    "bank_confident": 0.90,          # below this a reused answer is flagged
}

DEFAULT_PROFILE = {
    "contact": {"first_name": "", "last_name": "", "preferred_name": "", "email": "",
                "phone": "", "address_line1": "", "city": "", "state": "", "zip": "",
                "country": "United States"},
    "links": {"linkedin": "", "github": "", "website": "", "portfolio": ""},
    "work_history": [],   # {company, title, location, start, end, description}
    "education": [],      # {school, degree, field, start, end}
    "work_auth": {"authorized": "", "requires_sponsorship": ""},
    "salary": {"expectation": ""},
    # Blank means "leave this question for me". Nothing is ever inferred here.
    "demographics": {"gender": "", "race_ethnicity": "", "hispanic_latino": "",
                     "veteran_status": "", "disability_status": "", "pronouns": ""},
    "extras": {"current_company": "", "current_title": "", "years_experience": "",
               "notice_period": "", "earliest_start": "", "how_heard": "",
               "willing_to_relocate": ""},
    "writing": {"style": "", "summary": ""},
}


def seed_defaults(conn) -> None:
    if repo.get_config(conn, "criteria", "search") is None:
        search = dict(DEFAULT_SEARCH)
        search.update(_scraper_filters())
        repo.set_config(conn, "criteria", "search", search)
    app = repo.get_config(conn, "criteria", "app") or {}
    merged = {**DEFAULT_APP, **app}
    if merged != app:
        repo.set_config(conn, "criteria", "app", merged)
    for key, value in DEFAULT_PROFILE.items():
        if repo.get_config(conn, "profile", key) is None:
            repo.set_config(conn, "profile", key, value)
    if conn.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
        sync_companies(conn)


def app_settings(conn) -> dict:
    return {**DEFAULT_APP, **(repo.get_config(conn, "criteria", "app") or {})}


def search_criteria(conn) -> dict:
    return {**DEFAULT_SEARCH, **(repo.get_config(conn, "criteria", "search") or {})}


def load_profile(conn) -> dict:
    stored = repo.all_config(conn, "profile")
    out = {}
    for key, default in DEFAULT_PROFILE.items():
        value = stored.get(key, default)
        out[key] = {**default, **value} if isinstance(default, dict) else value
    return out


def _sources() -> dict:
    path = config.SCRAPER_DIR / "sources.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _scraper_filters() -> dict:
    """Carry over the keyword lists already tuned in the scraper config. Level
    words move to the level rule; geography comes from DEFAULT_SEARCH."""
    f = (_sources().get("filters") or {})
    out: dict = {}
    level_words = {"intern", "manager", "principal", "staff", "director", "senior", "junior"}
    if f.get("include_keywords"):
        out["title_include"] = list(f["include_keywords"])
    if f.get("exclude_keywords"):
        keep = [w for w in f["exclude_keywords"] if w.lower() not in level_words]
        out["title_exclude"] = list(dict.fromkeys(keep + ["(Multiple Positions)"]))
    return out


def sync_companies(conn) -> dict:
    """Add companies from sources.yaml that are not in the table yet. Never
    removes or edits an existing row, so dashboard edits survive a re-sync."""
    added, skipped = 0, 0
    for src in _sources().get("sources") or []:
        fields = scraper.company_from_source(src)
        if fields is None:
            skipped += 1
            continue
        _, created = repo.upsert_company(conn, **fields)
        added += int(created)
    return {"added": added, "out_of_scope": skipped}


def import_job_ops_profile(conn, data: dict) -> list[str]:
    """Map apps/job-ops apply-profile.json onto the profile store. Explicit,
    user-triggered; returns the sections that were updated."""
    def pick(mapping: dict) -> dict:
        return {k: str(data[src]).strip() for k, src in mapping.items()
                if data.get(src) not in (None, "")}

    updates = {
        "contact": pick({"first_name": "firstName", "last_name": "lastName",
                         "preferred_name": "preferredName", "email": "email",
                         "phone": "phone", "address_line1": "addressLine1",
                         "city": "city", "state": "state", "zip": "zip",
                         "country": "country"}),
        "links": pick({"linkedin": "linkedin", "github": "github", "website": "website"}),
        "work_auth": pick({"authorized": "workAuthorized",
                           "requires_sponsorship": "requireSponsorship"}),
        "salary": pick({"expectation": "desiredSalary"}),
        "demographics": pick({"gender": "gender", "race_ethnicity": "raceEthnicity",
                              "hispanic_latino": "hispanicLatino", "pronouns": "pronouns",
                              "veteran_status": "veteranStatus",
                              "disability_status": "disabilityStatus"}),
        "extras": pick({"current_company": "currentCompany", "current_title": "currentTitle",
                        "years_experience": "yearsExperience", "notice_period": "noticePeriod",
                        "earliest_start": "earliestStartDate", "how_heard": "howHeard",
                        "willing_to_relocate": "willingToRelocate"}),
        "writing": pick({"summary": "summary"}),
    }
    changed = []
    for key, values in updates.items():
        if values:
            current = repo.get_config(conn, "profile", key) or {}
            repo.set_config(conn, "profile", key, {**DEFAULT_PROFILE[key], **current, **values})
            changed.append(key)
    work = [{"company": e.get("company", ""), "title": e.get("title", ""),
             "location": e.get("location", ""), "start": e.get("startDate", ""),
             "end": e.get("endDate", ""), "description": e.get("description", "")}
            for e in data.get("experience") or []]
    if work:
        repo.set_config(conn, "profile", "work_history", work)
        changed.append("work_history")
    edu = [{"school": e.get("school", ""), "degree": e.get("degree", ""),
            "field": e.get("field", ""), "start": e.get("startDate", ""),
            "end": e.get("endDate", "")} for e in data.get("education") or []]
    if edu:
        repo.set_config(conn, "profile", "education", edu)
        changed.append("education")
    return changed

from datetime import datetime, timedelta, timezone

import pytest

from copilot import filters, seed

CRITERIA = dict(seed.DEFAULT_SEARCH)


def posting(title="Software Engineer", location="San Francisco, CA", remote=False, **kw):
    return {"title": title, "location": location, "remote": remote, "company": "Acme", **kw}


@pytest.mark.parametrize("title,level", [
    ("Software Engineer", "mid"),
    ("Software Engineer II", "mid"),
    ("Senior Software Engineer", "senior"),
    ("Sr. Backend Engineer", "senior"),
    ("Staff Software Engineer", "staff"),
    ("Principal Engineer", "principal"),
    ("Engineering Manager, Payments", "management"),
    ("Software Engineer Intern", "intern"),
    ("Software Engineer, New Grad", "entry"),
    ("Tech Lead, Platform", "lead"),
    ("Internal Tools Engineer", "mid"),          # 'intern' must not match 'internal'
])
def test_level_of(title, level):
    assert filters.level_of(title) == level


@pytest.mark.parametrize("location,remote,ok", [
    ("San Francisco, CA", False, True),
    ("New York, NY; Los Angeles, CA", False, True),
    ("New York, NY", False, False),
    ("Austin, TX", False, False),               # 'US' must not match inside 'Austin'
    ("Remote", True, True),
    ("Remote (US)", True, True),
    ("US-Remote", True, True),
    ("Remote - Canada", True, False),
    ("Remote, India", True, False),
    ("Remote (EMEA)", True, False),
    ("United States", False, True),             # a bare region reads as remote-eligible
    ("London, United Kingdom", False, False),
    ("", False, True),                          # unknown location is kept, not guessed
])
def test_location(location, remote, ok):
    assert filters.location_ok(location, remote, CRITERIA) is ok


def test_remote_can_be_switched_off():
    crit = {**CRITERIA, "remote_ok": False}
    assert not filters.location_ok("Remote (US)", True, crit)
    assert filters.location_ok("San Jose, CA", False, crit)


def test_check_reports_the_failed_rule():
    assert filters.check(posting(), CRITERIA) == (True, "")
    assert filters.check(posting(title="Account Executive"), CRITERIA) == (False, "title")
    assert filters.check(posting(title="Staff Software Engineer"), CRITERIA) == (False, "level")
    assert filters.check(posting(location="Berlin"), CRITERIA) == (False, "location")
    assert filters.check(posting(title="iOS Software Engineer"), CRITERIA) == (False, "title")


def test_perm_filings_are_excluded():
    """'(Multiple Positions)' marks a labor-certification filing, not an opening."""
    p = posting(title="Software Engineer (Multiple Positions)")
    assert filters.check(p, CRITERIA) == (False, "title")


def test_excluded_company_matches_on_normalized_name():
    crit = {**CRITERIA, "excluded_companies": ["Acme, Inc."]}
    assert filters.check(posting(), crit) == (False, "company")


def test_age_cutoff_keeps_undated_postings():
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    assert filters.check(posting(posted_at=old), CRITERIA) == (False, "age")
    assert filters.check(posting(posted_at=""), CRITERIA)[0]
    assert filters.check(posting(posted_at="Posted 30+ Days Ago"), CRITERIA)[0]

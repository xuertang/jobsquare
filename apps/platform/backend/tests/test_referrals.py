from datetime import datetime, timedelta, timezone

from copilot import referrals, repo, seed
from tests.conftest import add_posting

EXPORT = """Notes:
"When exporting your connection data, you may notice that some of the email addresses are missing."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
Dana,Okafor,https://www.linkedin.com/in/dana-okafor,dana@private.example,"Acme, Inc.",Staff Software Engineer,04 Mar 2019
Sam,Lee,https://www.linkedin.com/in/samlee,,Acme,Technical Recruiter,12 Jan 2026
Priya,Natarajan,https://www.linkedin.com/in/priyan,,Globex,Product Manager,21 Jul 2022
,,,,,,
"""


def save_profile(conn, profile):
    for key, value in profile.items():
        repo.set_config(conn, "profile", key, value)


def test_parse_export_skips_preamble_and_drops_emails():
    rows = referrals.parse_connections_csv(EXPORT.encode("utf-8-sig"))
    assert [r["name"] for r in rows] == ["Dana Okafor", "Sam Lee", "Priya Natarajan"]
    assert rows[0] == {"name": "Dana Okafor", "company": "Acme, Inc.",
                       "title": "Staff Software Engineer",
                       "profile_url": "https://www.linkedin.com/in/dana-okafor",
                       "connected_on": "2019-03-04", "source": "export"}
    assert all("email" not in k for r in rows for k in r)


def test_reimport_updates_in_place_and_keeps_hand_edits(conn):
    assert referrals.import_contacts(conn, EXPORT) == {"rows": 3, "created": 3, "updated": 0}
    dana = repo.search_contacts(conn, "Dana")[0]
    repo.update_contact(conn, dana["id"], {"relationship_type": "former_colleague",
                                           "shared_context": "We built billing at Globex"})
    moved = EXPORT.replace("Staff Software Engineer", "Principal Engineer")
    assert referrals.import_contacts(conn, moved) == {"rows": 3, "created": 0, "updated": 3}
    dana = repo.get_contact(conn, dana["id"])
    assert dana["title"] == "Principal Engineer"
    assert dana["relationship_type"] == "former_colleague"
    assert dana["shared_context"] == "We built billing at Globex"


def test_contacts_match_a_posting_company_and_rank_by_strength(conn, profile):
    save_profile(conn, profile)
    referrals.import_contacts(conn, EXPORT)
    pid = add_posting(conn)
    posting, company = repo.get_posting(conn, pid), repo.get_company(conn, 1)
    ranked = referrals.contacts_for_company(conn, company, posting)
    # "Acme, Inc." and "Acme" both normalize to the company; Globex does not.
    assert [c["name"] for c in ranked] == ["Dana Okafor", "Sam Lee"]
    assert "same function as the role" in ranked[0]["reasons"]
    assert "recruiting or hiring side" in ranked[1]["reasons"]
    assert ranked[0]["hint"] == "Connected while you were at Globex"
    # Marking the relationship moves a contact up.
    repo.update_contact(conn, ranked[1]["id"], {"relationship_type": "former_colleague"})
    assert referrals.contacts_for_company(conn, company, posting)[0]["name"] == "Sam Lee"


def test_alias_extends_company_matching(conn):
    repo.upsert_contact(conn, {"name": "Lou Park", "company": "Acme Robotics"})
    company = repo.get_company(conn, 1)
    assert referrals.contacts_for_company(conn, company) == []
    repo.update_company(conn, 1, {"aliases": "Acme Robotics"})
    assert len(referrals.contacts_for_company(conn, repo.get_company(conn, 1))) == 1


def test_search_links_are_plain_urls_for_the_user(conn, profile):
    pid = add_posting(conn)
    links = referrals.search_links(repo.get_posting(conn, pid), profile)
    labels = [l["label"] for l in links]
    assert labels == ["UCLA alumni at Acme", "Ex-Initech at Acme", "Ex-Globex at Acme",
                      "Hiring team at Acme", "My connections at Acme"]
    assert all(l["url"].startswith("https://www.linkedin.com/search/results/people/?keywords=")
               for l in links)
    assert "network=%5B%22S%22%5D" in links[0]["url"]      # second degree
    assert "%22Acme%22%20%22UCLA%22" in links[0]["url"]


def test_template_draft_per_contact_type(conn, profile):
    pid = add_posting(conn)
    posting = repo.get_posting(conn, pid)
    base = {"name": "Dana Okafor", "title": "Engineer", "company": "Acme",
            "shared_context": ""}
    colleague = referrals.template({**base, "relationship_type": "former_colleague",
                                    "shared_context": "We shipped the ledger rewrite"},
                                   posting, profile, "initial")
    assert colleague.startswith("Hi Dana,") and "ledger rewrite" in colleague
    assert "referring me" in colleague and colleague.endswith("Thanks,\nAlex")
    hiring = referrals.template({**base, "relationship_type": "hiring_team"}, posting,
                                profile, "initial")
    assert "referr" not in hiring, "a cold note to the hiring team does not ask for a referral"
    assert "—" not in colleague + hiring


def test_draft_uses_template_without_llm_and_is_reused(conn, profile):
    save_profile(conn, profile)
    cid, _ = repo.upsert_contact(conn, {"name": "Sam Lee", "company": "Acme"})
    pid = add_posting(conn)
    first = referrals.draft_message(conn, cid, pid)
    assert first["source"] == "template" and first["sent_at"] is None
    assert first["char_cap"] == 800 and first["problems"] == []
    assert referrals.draft_message(conn, cid, pid)["id"] == first["id"]


def test_llm_draft_is_checked_against_the_cap_and_retried(conn, profile, fake_llm):
    save_profile(conn, profile)
    cid, _ = repo.upsert_contact(conn, {"name": "Sam Lee", "company": "Acme",
                                        "relationship_type": "hiring_team"})
    pid = add_posting(conn)
    replies = iter(["x" * 400, "Hi Sam — quick question about the role.\n\nAlex"])
    fake = fake_llm(text=lambda kwargs: next(replies))
    msg = referrals.draft_message(conn, cid, pid)
    assert msg["source"] == "llm" and msg["char_cap"] == 300
    assert msg["body"] == "Hi Sam, quick question about the role.\n\nAlex"
    assert len(fake.calls) == 2
    retry = fake.calls[1]["messages"]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert "under 300" in retry[-1]["content"]
    # The contact's email or the candidate's contact details never go out.
    sent = str(fake.calls[0])
    assert "alex@example.com" not in sent and "555" not in sent


def test_over_cap_draft_is_flagged_not_truncated(conn, profile, fake_llm):
    save_profile(conn, profile)
    cid, _ = repo.upsert_contact(conn, {"name": "Sam Lee", "company": "Acme"})
    fake_llm(text="y" * 900)
    msg = referrals.draft_message(conn, cid, None)
    assert len(msg["body"]) == 900
    assert msg["problems"] == ["900 characters, over the 800 limit"]


def _sent_days_ago(conn, contact_id, posting_id, days, kind="initial"):
    mid = repo.add_message(conn, contact_id=contact_id, posting_id=posting_id,
                           body="Hi, about the role", kind=kind)
    when = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    repo.update_message(conn, mid, {"sent_at": when})
    return mid


def test_followups_due_after_the_wait_with_a_drafted_nudge(conn, profile):
    save_profile(conn, profile)
    pid = add_posting(conn)
    quiet, _ = repo.upsert_contact(conn, {"name": "Quiet Quinn", "company": "Acme"})
    recent, _ = repo.upsert_contact(conn, {"name": "Recent Rae", "company": "Acme"})
    replied, _ = repo.upsert_contact(conn, {"name": "Replied Ravi", "company": "Acme"})
    _sent_days_ago(conn, quiet, pid, 9)
    _sent_days_ago(conn, recent, pid, 2)
    _sent_days_ago(conn, replied, pid, 9)
    repo.add_message(conn, contact_id=replied, posting_id=pid, body="Sure, send it over",
                     direction="in", kind="reply", sent=True)
    due = referrals.followups(conn)
    assert [c["name"] for c in due] == ["Quiet Quinn"]
    assert due[0]["days_waiting"] == 9
    assert due[0]["draft"]["kind"] == "followup"
    assert "following up" in due[0]["draft"]["body"]
    # Sending the nudge uses up the one follow-up allowed by default.
    repo.update_message(conn, due[0]["draft"]["id"],
                        {"sent_at": (datetime.now(timezone.utc) - timedelta(days=8))
                         .isoformat(timespec="seconds")})
    assert referrals.followups(conn) == []


def test_logged_outcome_ends_followups(conn, profile):
    save_profile(conn, profile)
    cid, _ = repo.upsert_contact(conn, {"name": "Quiet Quinn", "company": "Acme"})
    _sent_days_ago(conn, cid, None, 20)
    assert len(referrals.followups(conn)) == 1
    repo.add_message(conn, contact_id=cid, posting_id=None, body="", direction="in",
                     kind="reply", outcome="no_response", sent=True)
    assert referrals.followups(conn) == []
    msgs = repo.messages_for_contacts(conn, [cid])
    assert referrals.contact_status(msgs) == "no_response"

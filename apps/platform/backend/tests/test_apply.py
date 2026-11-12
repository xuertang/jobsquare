import pytest

from copilot import answers, apply, db, repo, seed
from tests.conftest import add_posting

SETTINGS = dict(seed.DEFAULT_APP)
POSTING = {"company": "Acme", "title": "Senior Software Engineer", "department": "Payments"}
RESUME = {"id": 1, "label": "General", "path": "resumes/1-cv.pdf", "is_default": True}


def field(label, type="text", options=None, key=None, **kw):
    return {"key": key or f"f:{label[:24]}", "label": label, "type": type,
            "options": options or [], **kw}


def plan(fields, profile, bank=(), **kw):
    kw.setdefault("resume", RESUME)
    out = apply.plan(fields, profile=profile, bank=list(bank), settings=SETTINGS,
                     posting=POSTING, **kw)
    return {d["question"]: d for d in out}


# ---------------------------------------------------------- classification ---
@pytest.mark.parametrize("label,type,expected", [
    ("First Name", "text", ("standard", "first_name")),
    ("Legal name", "text", ("standard", "full_name")),
    ("Email", "email", ("standard", "email")),
    ("Resume/CV", "file", ("standard", "resume")),
    ("LinkedIn Profile", "text", ("standard", "linkedin")),
    ("Current location", "text", ("standard", "location")),
    ("Will you now or in the future require sponsorship for employment visa status?",
     "select", ("standard", "requires_sponsorship")),
    ("Are you legally authorized to work in the United States?", "select",
     ("standard", "authorized")),
    ("Gender", "select", ("demographic", "gender")),
    ("Are you Hispanic/Latino?", "select", ("demographic", "hispanic_latino")),
    ("Veteran Status", "select", ("demographic", "veteran_status")),
    ("Sexual orientation", "select", ("demographic", "")),
    ("I agree to the Privacy Policy", "checkbox", ("consent", "")),
    ("Join our talent community", "checkbox", ("consent", "")),
    ("Social Security Number", "text", ("restricted", "")),
    ("Date of birth", "date", ("restricted", "")),
    ("Why do you want to work here?", "textarea", ("custom", "")),
    ("Describe a time you used your full name recognition system at a prior company in "
     "production and what you learned from it", "textarea", ("custom", "")),
])
def test_classify(label, type, expected):
    assert apply.classify({"label": label, "type": type}) == expected


def test_attribute_hints_cover_terse_labels():
    assert apply.classify({"label": "Name", "type": "text",
                           "name": "_systemfield_name"}) == ("standard", "full_name")
    assert apply.classify({"label": "", "type": "text", "name": "urls[LinkedIn]"}) == \
        ("standard", "linkedin")
    assert apply.classify({"label": "", "type": "text", "name": "org"}) == \
        ("standard", "current_company")


# ---------------------------------------------------------------- options ---
@pytest.mark.parametrize("value,options,expected", [
    ("Male", ["Female", "Male", "Non-binary"], "Male"),      # not 'Female' by substring
    ("Male", ["Man", "Woman"], "Man"),
    ("United States", ["Canada", "United States of America", "Mexico"],
     "United States of America"),
    ("Bachelor of Science", ["High School", "Bachelor's Degree", "Master's Degree"],
     "Bachelor's Degree"),
    ("Prefer not to say", ["Yes", "No", "I don't wish to answer"], "I don't wish to answer"),
    ("LinkedIn", ["Company website", "LinkedIn", "Referral"], "LinkedIn"),
    ("California", ["CA", "NY"], None),                      # no guess on abbreviations
    ("Engineer", ["Software Engineer", "Data Engineer"], None),   # ambiguous
])
def test_choose_option(value, options, expected):
    assert apply.choose_option(value, options) == expected


def test_yes_no_needs_plain_options():
    assert apply.choose_yes_no("yes", ["Yes, I am authorized", "No"]) == "Yes, I am authorized"
    assert apply.choose_yes_no("no", ["Yes", "No, I will not need sponsorship"]) \
        == "No, I will not need sponsorship"
    assert apply.choose_yes_no("yes", ["US Citizen", "Green Card", "H-1B"]) is None


# ---------------------------------------------------------------- planner ---
def test_standard_fields_come_from_the_profile(profile):
    out = plan([
        field("First Name"), field("Last Name"), field("Email", "email"),
        field("Phone", "tel"), field("Resume/CV", "file"), field("LinkedIn Profile"),
        field("Current location"), field("Current company"),
        field("Are you legally authorized to work in the United States?", "select",
              ["Yes", "No"]),
        field("Will you now or in the future require sponsorship?", "radio", ["Yes", "No"]),
        field("Country", "select", ["Canada", "United States of America"]),
        field("How did you hear about us?", "select", ["LinkedIn", "Referral", "Other"]),
    ], profile)
    values = {q: d["value"] for q, d in out.items()}
    assert values == {
        "First Name": "Alex", "Last Name": "Rivera", "Email": "alex@example.com",
        "Phone": "+1 415 555 0199", "Resume/CV": "General",
        "LinkedIn Profile": "https://linkedin.com/in/alexrivera",
        "Current location": "Los Angeles, California", "Current company": "Initech",
        "Are you legally authorized to work in the United States?": "Yes",
        "Will you now or in the future require sponsorship?": "No",
        "Country": "United States of America", "How did you hear about us?": "LinkedIn"}
    assert all(d["action"] == "fill" and d["source"] == "profile" and not d["flagged"]
               for d in out.values())
    assert out["Resume/CV"]["resume_id"] == 1


def test_guardrails_leave_fields_for_the_user(profile):
    out = plan([
        field("Gender", "select", ["Man", "Woman", "Decline to self-identify"]),
        field("Veteran Status", "select", ["Yes", "No"]),
        field("I agree to the Privacy Policy", "checkbox"),
        field("Text me about future roles", "checkbox"),
        field("Social Security Number"),
        field("Which office do you prefer?", "select", ["SF", "NYC"]),
        field("Are you authorized to work in Canada?", "select", ["Yes", "No"]),
        field("What is your work authorization status?", "select",
              ["US Citizen", "Green Card", "H-1B"]),
        field("Desired salary", "select", ["$100k-$150k", "$150k-$200k"]),
        field("Cover Letter", "file"),
    ], profile)
    assert all(d["action"] == "skip" for d in out.values())
    assert "left for you" in out["Gender"]["note"]
    assert "never guessed" in out["Which office do you prefer?"]["note"]
    assert "never filled" in out["Social Security Number"]["note"]
    assert "country other than" in out["Are you authorized to work in Canada?"]["note"]


def test_demographics_fill_only_from_explicit_defaults(profile):
    profile["demographics"].update(gender="Male", veteran_status="Prefer not to say")
    out = plan([
        field("Gender", "select", ["Man", "Woman", "Decline to self-identify"]),
        field("Veteran Status", "select", ["I am a veteran", "I am not a veteran",
                                           "I don't wish to answer"]),
        field("Disability Status", "select", ["Yes", "No"]),
    ], profile)
    assert out["Gender"]["value"] == "Man"
    assert out["Veteran Status"]["value"] == "I don't wish to answer"
    assert out["Disability Status"]["action"] == "skip"


def test_missing_profile_value_is_reported_not_invented(profile):
    profile["links"]["github"] = ""
    out = plan([field("GitHub URL"), field("Resume", "file")], profile, resume=None)
    assert out["GitHub URL"]["action"] == "skip" and "github" in out["GitHub URL"]["note"]
    assert out["Resume"]["note"] == "No resume file uploaded in Settings."


def bank_entry(question, answer, id=1, company=""):
    """As answers.save stores it: the employer's name is stripped before
    embedding, so the entry is reusable at the next company."""
    return {"id": id, "question": question, "answer": answer,
            "embedding": answers.embedder.embed(answers.canonical(question, company))}


def test_answer_bank_reuse_and_low_confidence_flag(profile):
    bank = [bank_entry("Why do you want to work at Stripe?", "I like payments.", 1, "Stripe"),
            bank_entry("Describe a challenging technical project you led.",
                       "I rebuilt the ledger.", 2),
            bank_entry("Are you open to hybrid work?", "Yes", 3)]
    out = plan([
        field("Why do you want to work at Acme?", "textarea"),
        field("Describe a challenging technical project you have led", "textarea"),
        field("Are you open to hybrid work?", "select", ["Yes", "No"]),
        field("What is your favorite database and why?", "textarea"),
    ], profile, bank)
    exact = out["Why do you want to work at Acme?"]
    assert (exact["value"], exact["source"], exact["flagged"]) == ("I like payments.", "bank", False)
    assert exact["confidence"] == 1.0 and exact["bank_id"] == 1
    close = out["Describe a challenging technical project you have led"]
    assert close["value"] == "I rebuilt the ledger." and close["source"] == "bank"
    assert out["Are you open to hybrid work?"]["value"] == "Yes"
    assert out["What is your favorite database and why?"]["action"] == "skip"


def test_bank_answer_that_fits_no_option_is_not_forced(profile):
    bank = [bank_entry("Which office do you prefer?", "Seattle")]
    out = plan([field("Which office do you prefer?", "select", ["SF", "NYC"])], profile, bank)
    assert out["Which office do you prefer?"]["action"] == "skip"


def test_llm_drafts_free_text_only_and_flags_it(profile, fake_llm):
    def reply(kwargs):
        return apply.DraftedAnswers(answers=[
            apply.DraftedAnswer(index=0, answer="Payments at scale — my lane.",
                                needs_input=False),
            apply.DraftedAnswer(index=1, answer="", needs_input=True)])
    fake = fake_llm(parsed=reply)
    out = plan([
        field("What excites you about this role?", "textarea"),
        field("What was your GPA?", "text"),
        field("Which team interests you?", "select", ["Infra", "Product"]),
        field("First Name"),
    ], profile, resume_text="Alex Rivera alex@example.com built ledgers")
    drafted = out["What excites you about this role?"]
    assert drafted["value"] == "Payments at scale, my lane."
    assert drafted["source"] == "llm" and drafted["flagged"]
    assert out["What was your GPA?"]["action"] == "skip", "needs a fact only the user has"
    assert out["Which team interests you?"]["action"] == "skip", "choices are never LLM-picked"
    assert len(fake.calls) == 1, "one batched call for all free-text questions"
    sent = str(fake.calls[0])
    assert "What excites you" in sent and "Which team interests you" not in sent
    assert "alex@example.com" not in sent, "contact details are redacted before sending"
    assert fake.calls[0]["output_config"] == {"effort": "medium"}


def test_resume_variant_selection():
    resumes = [{"id": 1, "label": "General", "path": "a.pdf", "keywords": "", "is_default": True},
               {"id": 2, "label": "Payments", "path": "b.pdf", "keywords": "payments, fintech",
                "is_default": False},
               {"id": 3, "label": "No file", "path": "", "keywords": "payments, senior",
                "is_default": False}]
    assert apply.select_resume(POSTING, resumes)["id"] == 2
    assert apply.select_resume({"title": "ML Engineer"}, resumes)["id"] == 1
    assert apply.select_resume(POSTING, []) is None


# ------------------------------------------------------------- lifecycle ---
def match_id(conn, posting_id):
    return repo.match_for_posting(conn, posting_id)["id"]


def test_approve_creates_application_and_blocks_duplicates(conn):
    first = add_posting(conn, external_id="1", requisition_id="REQ-9")
    repost = add_posting(conn, external_id="2", requisition_id="REQ-9")
    app = apply.approve(conn, match_id(conn, first))
    assert app["state"] == "waiting"
    assert repo.get_match(conn, match_id(conn, first))["state"] == "approved"
    with pytest.raises(apply.ApplyError, match="same requisition"):
        apply.approve(conn, match_id(conn, repost))
    # Approving twice returns the same application.
    assert apply.approve(conn, match_id(conn, first))["id"] == app["id"]


def test_placeholder_requisition_ids_do_not_block(conn):
    ids = [add_posting(conn, external_id=str(i), requisition_id="OPEN-1") for i in range(6)]
    apply.approve(conn, match_id(conn, ids[0]))
    assert apply.approve(conn, match_id(conn, ids[1]))["state"] == "waiting"


def test_workday_goes_to_the_manual_queue_with_answers(conn, profile):
    for key, value in profile.items():
        repo.set_config(conn, "profile", key, value)
    pid = add_posting(conn, ats_type="workday")
    app = apply.approve(conn, match_id(conn, pid))
    assert app["state"] == "needs_manual" and "Workday" in app["manual_reason"]
    pasted = {a["question"]: a["answer"] for a in repo.list_answers(conn, app["id"])}
    assert pasted["Email"] == "alex@example.com"
    assert pasted["Authorized to work in the US"] == "yes"
    with pytest.raises(apply.ApplyError, match="by hand"):
        apply.launch(conn, app["id"])


def test_daily_cap_blocks_new_fills(conn):
    a = apply.approve(conn, match_id(conn, add_posting(conn, external_id="1")))
    b = apply.approve(conn, match_id(conn, add_posting(conn, external_id="2")))
    repo.set_config(conn, "criteria", "app", {**seed.DEFAULT_APP, "daily_apply_cap": 1})
    apply.finalize(conn, a["id"])
    with pytest.raises(apply.ApplyError, match="Daily cap reached"):
        apply.launch(conn, b["id"])
    repo.set_config(conn, "criteria", "app", {**seed.DEFAULT_APP, "daily_apply_cap": 0})
    assert apply.launch(conn, b["id"])["task_id"]


def test_fill_review_and_submission_feed_the_bank(conn, profile):
    app = apply.approve(conn, match_id(conn, add_posting(conn)))
    decisions = apply.plan([
        field("First Name", key="f0"),
        field("Why do you want to work at Acme?", "textarea", key="f1"),
        field("Which office do you prefer?", "select", ["SF", "NYC"], key="f2"),
        field("Gender", "select", ["Man", "Woman"], key="f3"),
        field("LinkedIn Profile", key="f4"),
    ], profile=profile, bank=[], settings=SETTINGS, posting=POSTING, resume=None)
    report = apply.record_fill(conn, app["id"], decisions,
                               {"f0": {"ok": True}, "f4": {"ok": False, "error": "detached"}},
                               {"captcha": True})
    assert report == {"captcha": True, "unfilled": 4, "fields": 5}
    assert repo.get_application(conn, app["id"])["state"] == "paused"
    rows = {a["field_key"]: a for a in repo.list_answers(conn, app["id"])}
    assert rows["f0"]["status"] == "filled" and rows["f0"]["source"] == "profile"
    assert rows["f4"]["status"] == "failed" and rows["f4"]["note"] == "detached"
    assert rows["f2"]["status"] == "unfilled"

    # The user answers two questions in the browser and fixes the first name.
    changed = apply.record_snapshot(conn, app["id"], {
        "f0": "Alexander", "f1": "I want to build payment rails.", "f2": "SF", "f3": ""})
    assert changed == 3
    rows = {a["field_key"]: a for a in repo.list_answers(conn, app["id"])}
    assert rows["f0"]["edited"] and rows["f0"]["source"] == "profile"
    assert rows["f1"]["source"] == "manual" and rows["f1"]["status"] == "filled"

    out = apply.finalize(conn, app["id"], screenshot_path="screenshots/x.png")
    assert out["application"]["state"] == "submitted" and out["bank_saved"] == 2
    bank = {e["question"]: e["answer"] for e in repo.list_bank(conn)}
    assert bank == {"Why do you want to work at Acme?": "I want to build payment rails.",
                    "Which office do you prefer?": "SF"}
    # Next application: the same questions are now answered from the bank,
    # and the standard field edit did not leak into it.
    again = apply.plan([field("Why do you want to work at Initrode?", "textarea"),
                        field("Which office do you prefer?", "select", ["NYC", "SF"])],
                       profile=profile, bank=repo.list_bank(conn), settings=SETTINGS,
                       posting={"company": "Initrode", "title": "SWE"}, resume=None)
    assert [(d["value"], d["source"]) for d in again] == [
        ("I want to build payment rails.", "bank"), ("SF", "bank")]


def test_embedder_keeps_unrelated_questions_apart():
    def sim(a, b):
        return answers.cosine(answers.embedder.embed(answers.canonical(a)),
                              answers.embedder.embed(answers.canonical(b)))
    assert sim("What are your salary expectations?", "What is your expected salary?") > 0.78
    assert sim("Why do you want to work here?", "Which languages do you know best?") < 0.3
    assert sim("Are you authorized to work in the US?", "Will you require sponsorship?") < 0.3
    assert answers.canonical("Why Stripe?", "Stripe") == answers.canonical("Why Acme?", "Acme")

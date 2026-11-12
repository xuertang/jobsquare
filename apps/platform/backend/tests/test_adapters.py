"""One fixture test per ATS adapter, against saved form snapshots, plus the
guarantees that hold for every adapter: unmapped fields are reported rather
than guessed, consent is never ticked, and nothing is ever submitted."""
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

from copilot import apply, seed  # noqa: E402
from worker import form  # noqa: E402
from worker.adapters import ADAPTERS, adapter_for  # noqa: E402

pytestmark = pytest.mark.browser
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def browser():
    try:
        pw = playwright.sync_playwright().start()
        b = pw.chromium.launch(headless=True)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Chromium is not installed (python -m playwright install chromium): {e}")
    yield b
    b.close()
    pw.stop()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 1000})
    ctx.add_init_script(form.PAGE_JS)
    p = ctx.new_page()
    p.set_default_timeout(4000)
    yield p
    ctx.close()


@pytest.fixture
def resume(tmp_path):
    path = tmp_path / "alex-rivera.pdf"
    path.write_bytes(b"%PDF-1.4 test resume")
    return path


RESUME = {"id": 1, "label": "General", "path": "resumes/1.pdf", "is_default": True}
POSTING = {"company": "Acme", "title": "Senior Software Engineer"}


def load(page, name):
    page.goto((FIXTURES / f"{name}.html").as_uri())
    # Count anything that would submit, however it is triggered.
    page.evaluate("""() => {
        window.__submits = 0; window.__submitClicks = 0;
        document.addEventListener('submit', (e) => { window.__submits++; e.preventDefault(); }, true);
        document.addEventListener('click', (e) => {
            const b = e.target.closest && e.target.closest('button, input[type=submit]');
            if (b && /submit|apply/i.test(b.textContent || b.value || '')) window.__submitClicks++;
        }, true);
    }""")


def run_fill(page, ats, profile, resume, bank=()):
    """Extract, plan and fill, the way the worker does. Custom dropdowns are
    planned but not driven: a static snapshot has no script to open them."""
    adapter = adapter_for(ats)
    assert adapter.form_present(page), "adapter should recognise its form"
    fields = form.extract(page, adapter.root)
    decisions = apply.plan(fields, profile=profile, bank=list(bank),
                           settings=dict(seed.DEFAULT_APP), posting=POSTING, resume=RESUME,
                           use_llm=False)
    results = {}
    form.set_filling(page, True)
    for d in decisions:
        if d["action"] == "fill" and d["field_type"] != "combobox":
            results[d["key"]] = form.fill(page, d, resume)
    form.set_filling(page, False)
    by_key = {d["key"]: d for d in decisions}
    return fields, by_key, results, form.values(page, adapter.root)


def assert_never_submitted(page):
    assert page.evaluate("() => [window.__submits, window.__submitClicks]") == [0, 0]
    assert form.blocked_submits(page) == 0


def labels(fields):
    return {f["key"]: (f["type"], f["label"]) for f in fields}


# -------------------------------------------------------------- greenhouse ---
def test_greenhouse_snapshot(page, profile, resume):
    load(page, "greenhouse")
    profile["demographics"]["gender"] = "Male"
    fields, plan, results, values = run_fill(page, "greenhouse", profile, resume)
    found = labels(fields)
    assert found["text:first_name"] == ("text", "First Name")
    assert found["text:last_name"] == ("text", "Last Name")
    assert found["text:email"] == ("text", "Email")
    assert found["tel:phone"] == ("tel", "Phone")
    assert found["file:resume"] == ("file", "Resume/CV"), "not the 'Attach' button text"
    assert found["file:cover_letter"][0] == "file"
    assert found["combobox:candidate-location"] == ("combobox", "Location (City)")
    assert found["combobox:gender"] == ("combobox", "Gender")
    countries = next(f for f in fields if f["type"] == "checkboxes")
    assert len(countries["options"]) == 30 and "Canada" in countries["options"]

    assert values["text:first_name"] == "Alex" and values["text:last_name"] == "Rivera"
    assert values["text:email"] == "alex@example.com"
    assert values["file:resume"] == "alex-rivera.pdf"
    assert values["file:cover_letter"] == "", "optional attachments are left alone"
    assert all(r["ok"] for r in results.values()), results

    # Reported, not guessed.
    assert plan["combobox:gender"]["category"] == "demographic"
    assert plan[countries["key"]]["action"] == "skip"
    assert "never guessed" in plan[countries["key"]]["note"]
    assert values[countries["key"]] == ""
    whatsapp = next(d for d in plan.values() if "WhatsApp" in d["question"])
    assert whatsapp["category"] == "consent" and whatsapp["action"] == "skip"
    assert_never_submitted(page)


# ------------------------------------------------------------------- lever ---
def test_lever_snapshot(page, profile, resume):
    load(page, "lever")
    fields, plan, results, values = run_fill(page, "lever", profile, resume)
    found = labels(fields)
    assert found["text:name"] == ("text", "Full name"), "required marker and helper text stripped"
    assert found["email:email"] == ("email", "Email")
    assert found["text:location"] == ("text", "Current location")
    assert found["text:org"] == ("text", "Current company")
    assert found["file:resume"] == ("file", "Resume/CV")
    assert found["text:urls[LinkedIn]"] == ("text", "LinkedIn URL")
    pronouns = next(f for f in fields if f["key"] == "checkboxes:pronouns")
    assert len(pronouns["options"]) == 10 and "They/them" in pronouns["options"]

    assert values["text:name"] == "Alex Rivera"
    assert values["email:email"] == "alex@example.com"
    assert values["text:org"] == "Initech"
    assert values["text:urls[LinkedIn]"] == "https://linkedin.com/in/alexrivera"
    assert values["file:resume"] == "alex-rivera.pdf"
    country = next(f for f in fields if f["type"] == "select" and len(f["options"]) > 200)
    assert values[country["key"]] == "United States", "location dropdown listing countries"
    assert all(r["ok"] for r in results.values()), results

    assert plan["checkboxes:pronouns"]["action"] == "skip"          # demographic
    assert values["checkboxes:pronouns"] == ""
    consent = next(d for d in plan.values() if "consent to contact me" in d["question"])
    assert consent["category"] == "consent" and values[consent["key"]] == ""
    employed = next(d for d in plan.values() if "previously employed" in d["question"])
    assert employed["action"] == "skip" and employed["options"][0] == "No"
    assert_never_submitted(page)


# ------------------------------------------------------------------- ashby ---
def test_ashby_snapshot(page, profile, resume):
    load(page, "ashby")
    # The snapshot has no React: emulate the yes/no buttons keeping their state.
    page.evaluate("""() => document.querySelectorAll('.ashby-application-form-input-yesno button')
        .forEach((b) => b.addEventListener('click', () => {
            b.parentElement.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        }))""")
    fields, plan, results, values = run_fill(page, "ashby", profile, resume)
    found = labels(fields)
    assert found["text:_systemfield_name"] == ("text", "Legal Name")
    assert found["email:_systemfield_email"] == ("email", "Email")
    assert found["file:_systemfield_resume"] == ("file", "Resume")
    assert sum(1 for f in fields if f["type"] == "file") == 1, "autofill uploader is ignored"

    pairs = [f for f in fields if f.get("widget") == "buttons"]
    assert [f["options"] for f in pairs] == [["Yes", "No"], ["Yes", "No"]]
    questions = [f["label"] for f in fields]
    assert len(questions) == len(set(questions)), \
        "the hidden checkbox behind each yes/no pair must not appear as a second field"

    assert values["text:_systemfield_name"] == "Alex Rivera"
    assert values["email:_systemfield_email"] == "alex@example.com"
    assert values["file:_systemfield_resume"] == "alex-rivera.pdf"
    auth = next(f for f in pairs if "authorized" in f["label"])
    sponsor = next(f for f in pairs if "sponsorship" in f["label"])
    assert values[auth["key"]] == "Yes" and values[sponsor["key"]] == "No"
    assert all(r["ok"] for r in results.values()), results

    confirm = next(d for d in plan.values() if d["question"].startswith("I confirm"))
    assert confirm["category"] == "consent" and values[confirm["key"]] == ""
    assert_never_submitted(page)


# --------------------------------------------------------- smartrecruiters ---
def test_smartrecruiters_shadow_dom_and_second_step(page, profile, resume):
    load(page, "smartrecruiters")
    fields, plan, results, values = run_fill(page, "smartrecruiters", profile, resume)
    by_label = {f["label"]: f for f in fields}
    assert set(by_label) == {"First name", "Last name", "Email", "Phone number", "LinkedIn",
                             "Resume", "I have read and accept the privacy notice"}
    assert by_label["Last name"]["type"] == "text", "label read from the host element"
    assert values[by_label["First name"]["key"]] == "Alex"
    assert values[by_label["Last name"]["key"]] == "Rivera"
    assert values[by_label["Email"]["key"]] == "alex@example.com"
    assert values[by_label["Resume"]["key"]] == "alex-rivera.pdf"
    assert values[by_label["I have read and accept the privacy notice"]["key"]] == ""

    # The user presses Next; the adapter is multi-step, so the worker re-scans.
    assert adapter_for("smartrecruiters").multi_step
    page.click("#next")
    seen = {f["key"] for f in fields}
    step2 = [f for f in form.extract(page, "main, form, body") if f["key"] not in seen]
    assert [f["label"] for f in step2] == [
        "Why do you want to join us?",
        "Are you legally authorized to work in the United States?", "Gender"]
    decisions = apply.plan(step2, profile=profile, bank=[], settings=dict(seed.DEFAULT_APP),
                           posting=POSTING, resume=None, use_llm=False)
    for d in decisions:
        if d["action"] == "fill":
            assert form.fill(page, d, None)["ok"]
    after = form.values(page, "main, form, body")
    assert after["radio:auth"] == "Yes"
    assert after["radio:gender"] == "", "no demographic default saved, so left for the user"
    assert after[by_label["First name"]["key"]] == "Alex", "step one is untouched"
    assert page.evaluate("() => window.__submits") == 0


# ---------------------------------------------------------------- dropdowns ---
def test_custom_dropdowns(page):
    load(page, "combobox")
    fields = form.extract(page, "#application-form")
    assert [(f["key"], f["label"]) for f in fields] == [
        ("combobox:degree", "Degree"), ("combobox:loc", "Location (City)")]
    options = form.read_options(page, "combobox:degree")
    assert options == ["Associate's Degree", "Bachelor's Degree", "Master's Degree",
                       "Doctor of Philosophy (Ph.D.)"], "the hidden country list is not this menu"
    assert form.read_options(page, "combobox:loc") == [], "a remote search has nothing to list"

    picked = apply.choose_option("Bachelor of Science", options)
    assert picked == "Bachelor's Degree"
    out = form.fill(page, {"key": "combobox:degree", "field_type": "combobox",
                           "value": picked, "options": options}, None)
    assert out == {"ok": True, "error": ""}
    out = form.fill(page, {"key": "combobox:loc", "field_type": "combobox",
                           "value": "Los Angeles, California", "options": []}, None)
    assert out["ok"]
    assert form.values(page, "#application-form") == {
        "combobox:degree": "Bachelor's Degree",
        "combobox:loc": "Los Angeles, California, United States"}

    missing = form.fill(page, {"key": "combobox:degree", "field_type": "combobox",
                               "value": "Juris Doctor", "options": options}, None)
    assert not missing["ok"] and "no matching option" in missing["error"]
    assert form.values(page, "#application-form")["combobox:degree"] == "Bachelor's Degree"
    # Options are clicked. Enter is never pressed: in a form it submits.
    assert page.evaluate("() => [window.__enter, window.__submits]") == [0, 0]


# ------------------------------------------------------------ never submit ---
@pytest.mark.parametrize("fixture,selector", [
    ("greenhouse", "button[type=submit]"),
    ("lever", "#btn-submit"),                       # type=button, labelled 'Submit application'
    ("ashby", ".ashby-application-form-submit-button"),
    ("smartrecruiters", "#submit"),
])
def test_submit_controls_are_refused(page, fixture, selector):
    load(page, fixture)
    with pytest.raises(form.SubmitGuard):
        form.safe_click(page.locator(selector).first)
    assert page.evaluate("() => [window.__submits, window.__submitClicks]") == [0, 0]


def test_submit_is_blocked_while_filling_and_allowed_after(page):
    """Belt and braces: even if something triggered a submit mid-fill, the
    page-level guard swallows it. Once filling ends the user can submit."""
    page.goto((FIXTURES / "flow" / "apply.html").as_uri())
    page.fill("#first_name", "Alex")
    page.fill("#last_name", "Rivera")
    page.fill("#email", "alex@example.com")          # the form is now valid
    form.set_filling(page, True)
    page.evaluate("() => document.getElementById('application-form').requestSubmit()")
    assert form.blocked_submits(page) == 1
    assert page.url.endswith("apply.html")
    form.set_filling(page, False)
    page.click("#go")                                # the user, not the worker
    page.wait_for_url("**/confirmation.html")


def test_every_in_scope_ats_has_an_adapter_except_workday():
    assert sorted(ADAPTERS) == ["ashby", "greenhouse", "lever", "smartrecruiters"]
    assert adapter_for("workday") is None, "Workday is a manual queue, never automated"
    assert adapter_for("greenhouse").matches("https://job-boards.greenhouse.io/embed/job_app")
    assert not adapter_for("greenhouse").matches("https://evilgreenhouse.io.example.com/")

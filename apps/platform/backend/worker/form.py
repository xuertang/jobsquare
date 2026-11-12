"""Reading and writing form fields through Playwright.

Reading is delegated to page.js. Writing lives here, and every click goes
through `safe_click`, which refuses anything that could submit the form."""
from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

PAGE_JS = Path(__file__).with_name("page.js").read_text()
OPTION = '[role="option"], [class*="select__option"]'
SUBMIT_TEXT = re.compile(r"\b(submit|apply|send application|finish|complete application)\b", re.I)


class SubmitGuard(Exception):
    """Raised instead of clicking a control that could submit the form."""


def inject(page: Page) -> None:
    """Make sure page.js is present (init scripts miss set_content pages)."""
    page.evaluate(f"() => {{ if (!window.__copilot) {{ {PAGE_JS} }} }}")


def extract(page: Page, root: str) -> list[dict]:
    inject(page)
    return page.evaluate("(sel) => window.__copilot.extract(sel)", root)


def values(page: Page, root: str) -> dict[str, str]:
    inject(page)
    return page.evaluate("(sel) => window.__copilot.values(sel)", root)


def final_values(page: Page) -> dict[str, str] | None:
    try:
        inject(page)
        return page.evaluate("() => window.__copilot.final()")
    except PlaywrightError:
        return None


def set_filling(page: Page, on: bool) -> None:
    page.evaluate("(on) => { window.__copilotFilling = on; }", on)


def blocked_submits(page: Page) -> int:
    return page.evaluate("() => window.__copilotBlockedSubmits || 0")


def safe_click(loc: Locator, **kwargs) -> None:
    """Click an option, label or input. Never a submit control."""
    info = loc.evaluate(
        "el => ({tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase(),"
        " text: (el.textContent || el.value || '').trim().slice(0, 80),"
        " inOption: !!el.closest('[role=\"option\"], [role=\"listbox\"], label, [data-copilot-opt]')})")
    is_button = info["tag"] == "button" or (info["tag"] == "input" and info["type"] in ("submit", "button", "image"))
    if info["type"] == "submit" or (is_button and not info["inOption"]
                                    and SUBMIT_TEXT.search(info["text"])):
        raise SubmitGuard(f"refused to click a submit control: {info['text']!r}")
    loc.click(**kwargs)


def field(page: Page, key: str) -> Locator:
    return page.locator(f'[data-copilot-key="{_css(key)}"]').first


def _css(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def read_options(page: Page, key: str) -> list[str]:
    """Open a custom dropdown, read what it offers, close it again. Dropdowns
    that only search as you type come back empty."""
    loc = field(page, key)
    try:
        _open(page, loc)
        options = _options(page, loc)
        options.first.wait_for(state="visible", timeout=900)
        texts = options.all_inner_texts()
    except PlaywrightError:
        texts = []
    try:
        page.keyboard.press("Escape")
        loc.evaluate("el => el.blur && el.blur()")
    except PlaywrightError:
        pass
    seen: list[str] = []
    for t in texts[:300]:
        t = " ".join(t.split())
        if t and t not in seen and not re.match(r"(?i)^(no options|loading|type to search)", t):
            seen.append(t)
    return seen


def _open(page: Page, loc: Locator) -> None:
    """Open a dropdown. A react-select input sits under its placeholder, so a
    mouse click is intercepted; focus plus ArrowDown opens the menu instead.
    ArrowDown never submits a form."""
    if loc.evaluate("el => el.tagName") == "INPUT":
        loc.focus(timeout=2000)
        page.keyboard.press("ArrowDown")
    else:
        loc.click(timeout=2000)


def _options(page: Page, loc: Locator) -> Locator:
    """The options of the dropdown that is open for this control. Scoped by
    aria-controls when the widget sets it: pages keep other option lists in
    the DOM (a hidden phone-country list, for one), and those must not match."""
    listbox = loc.get_attribute("aria-controls") or loc.get_attribute("aria-owns")
    if listbox:
        return page.locator(f'[id="{_css(listbox)}"]').locator(OPTION)
    return page.locator(f":is({OPTION}):visible")


def fill(page: Page, decision: dict, resume_path: Path | None) -> dict:
    """Apply one planned value. Returns {'ok': bool, 'error': str}."""
    key, ftype, value = decision["key"], decision["field_type"], decision["value"]
    loc = field(page, key)
    try:
        if ftype == "file":
            if not resume_path:
                return {"ok": False, "error": "resume file is not available to the worker"}
            loc.set_input_files(str(resume_path))
        elif ftype in ("text", "textarea", "email", "tel", "url", "number"):
            loc.fill(str(value), timeout=4000)
        elif ftype == "select":
            loc.select_option(label=str(value), timeout=4000)
        elif ftype == "radio":
            _pick(page, key, str(value))
        elif ftype == "checkbox":
            _check(loc)
        elif ftype == "checkboxes":
            for v in value if isinstance(value, list) else [x.strip() for x in str(value).split(";")]:
                if v:
                    _pick(page, key, v)
        elif ftype == "combobox":
            _combobox(page, loc, str(value), bool(decision.get("options")))
        else:
            return {"ok": False, "error": f"unsupported field type {ftype}"}
        return {"ok": True, "error": ""}
    except SubmitGuard as e:
        return {"ok": False, "error": str(e)}
    except PlaywrightError as e:
        return {"ok": False, "error": str(e).splitlines()[0][:200]}


def _option(page: Page, key: str, value: str) -> Locator:
    return page.locator(
        f'[data-copilot-group="{_css(key)}"][data-copilot-opt="{_css(value)}"]').first


def _pick(page: Page, key: str, value: str) -> None:
    opt = _option(page, key, value)
    if opt.evaluate("el => el.tagName") == "BUTTON":
        safe_click(opt, timeout=3000)       # yes/no button pair
    else:
        _check(opt)


def _check(loc: Locator) -> None:
    """Tick a radio or checkbox. Styled controls hide the native input, so
    fall back to its label, then to a direct DOM click."""
    if loc.is_checked():
        return
    try:
        loc.check(timeout=1500)
        return
    except PlaywrightError:
        pass
    label = loc.locator("xpath=ancestor::label[1]")
    if label.count() == 0 and loc.get_attribute("id"):
        label = loc.page.locator(f'label[for="{_css(loc.get_attribute("id"))}"]')
    if label.count():
        try:
            safe_click(label.first, timeout=1500)
        except PlaywrightError:
            pass
    if not loc.is_checked():
        loc.evaluate("el => el.click()")
    if not loc.is_checked():
        raise PlaywrightError("could not tick this option")


def _combobox(page: Page, loc: Locator, value: str, known_options: bool) -> None:
    """Custom dropdown: open, type to filter, click the matching option.
    Options are clicked, never confirmed with Enter (Enter can submit)."""
    attempts = [value] if known_options else [value, value.split(",")[0].strip()]
    for attempt in dict.fromkeys(a for a in attempts if a):
        _open(page, loc)
        if loc.evaluate("el => el.tagName") == "INPUT":
            loc.fill("")
            loc.type(attempt[:60], delay=15)
        options = _options(page, loc)
        try:
            options.first.wait_for(state="visible", timeout=3500)
        except PlaywrightError:
            page.keyboard.press("Escape")
            continue
        texts = [" ".join(t.split()) for t in options.all_inner_texts()]
        want = value.lower()
        index = next((i for i, t in enumerate(texts) if t.lower() == want), None)
        if index is None and not known_options:
            index = next((i for i, t in enumerate(texts) if t.lower().startswith(attempt.lower())),
                         0 if texts else None)
        if index is None:
            page.keyboard.press("Escape")
            continue
        safe_click(options.nth(index), timeout=3000)
        return
    raise PlaywrightError(f"no matching option for {value!r}")

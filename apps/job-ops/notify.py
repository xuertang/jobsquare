"""Notifiers. Console always runs; others activate when their env var is set."""
from __future__ import annotations

import json
import os
import smtplib
from email.mime.text import MIMEText

import httpx

from models import Job


def _line(job: Job) -> str:
    loc = f"  [{job.location}]" if job.location else ""
    pay = f"  ({job.salary_range})" if job.salary_range else ""
    return f"  • {job.title}{loc}{pay}  — {job.company}\n    {job.url}"


def notify_console(new: list[Job], changed: list[Job]) -> None:
    if new:
        print(f"\n=== {len(new)} NEW listing(s) ===")
        for j in new:
            print(_line(j))
    if changed:
        print(f"\n=== {len(changed)} UPDATED listing(s) ===")
        for j in changed:
            print(_line(j))
    if not new and not changed:
        print("No fresh listings.")


def notify_slack(new: list[Job], changed: list[Job]) -> None:
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url or not (new or changed):
        return
    blocks = []
    if new:
        blocks.append(f"*{len(new)} new job(s)*")
        blocks += [f"• <{j.url}|{j.title}> — {j.company} {j.location}"
                   f"{f' · {j.salary_range}' if j.salary_range else ''}".rstrip()
                   for j in new]
    if changed:
        blocks.append(f"_{len(changed)} updated_")
    text = "\n".join(blocks)
    httpx.post(url, json={"text": text}, timeout=15)


def notify_webhook(new: list[Job], changed: list[Job]) -> None:
    url = os.getenv("WEBHOOK_URL")
    if not url or not (new or changed):
        return
    payload = {"new": [j.to_row() for j in new],
               "changed": [j.to_row() for j in changed]}
    httpx.post(url, content=json.dumps(payload, default=str),
               headers={"Content-Type": "application/json"}, timeout=15)


def notify_email(new: list[Job], changed: list[Job]) -> None:
    host = os.getenv("SMTP_HOST")
    to = os.getenv("EMAIL_TO")
    if not host or not to or not (new or changed):
        return
    body = "\n".join(_line(j) for j in (new + changed))
    msg = MIMEText(f"{len(new)} new / {len(changed)} updated\n\n{body}")
    msg["Subject"] = f"[jobscraper] {len(new)} new listing(s)"
    msg["From"] = os.getenv("EMAIL_FROM") or to
    msg["To"] = to
    with smtplib.SMTP(host, int(os.getenv("SMTP_PORT") or "587")) as s:
        s.starttls()
        if os.getenv("SMTP_USER"):
            s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        s.send_message(msg)


def _sms_body(new: list[Job], changed: list[Job], limit: int = 8) -> str:
    # ASCII-only and compact: non-GSM chars (•, …) force costly UCS-2 segments.
    head = f"[jobsquare] {len(new)} new, {len(changed)} updated"
    lines = [f"- {j.title} ({j.company})" for j in new[:limit]]
    if len(new) > limit:
        lines.append(f"+{len(new) - limit} more")
    return "\n".join([head, *lines])


def notify_sms(new: list[Job], changed: list[Job]) -> None:
    """Twilio SMS. Activates only when all four TWILIO_* env vars are set."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    sender = os.getenv("TWILIO_FROM")
    to = os.getenv("TWILIO_TO")
    if not (sid and token and sender and to) or not (new or changed):
        return
    resp = httpx.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        auth=(sid, token),
        data={"From": sender, "To": to, "Body": _sms_body(new, changed)},
        timeout=15,
    )
    resp.raise_for_status()  # surface misconfig (bad creds / unverified number)


NOTIFIERS = [notify_console, notify_slack, notify_webhook, notify_email, notify_sms]


def dispatch(new: list[Job], changed: list[Job]) -> None:
    for fn in NOTIFIERS:
        try:
            fn(new, changed)
        except Exception as e:  # noqa: BLE001
            print(f"  ! notifier {fn.__name__} failed: {e}")
"""1.0.5: integration settings stored in the database (Settings > Email, Payments, SMS).

Each section is a list of fields. Plain fields are stored as text in `app_settings`; secret fields
(passwords, API secrets) are encrypted (app/secret_store.py) and are write-only for the browser:
  * GET returns "" plus "<field>_set": true/false for a secret, never the value or part of it;
  * an empty secret in a save keeps the stored value; "<field>_clear": true removes it;
  * in demo mode (DEMO_MODE=true) secrets are never stored - they are skipped and reported back,
    and the SMTP test send is disabled, so demo visitors can neither read nor plant real credentials.
Server code reads a decrypted secret only where it is needed (e.g. smtp_send below).
"""

from __future__ import annotations

import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import secret_store
from .models import AppSetting, utcnow

EMAIL_RE = re.compile(r"^[^@\s<>\"']{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,255}$")


@dataclass(frozen=True)
class Field:
    name: str
    kind: str = "text"  # text, secret, bool, int, choice, email, url, host
    default: object = ""
    choices: tuple[str, ...] = field(default_factory=tuple)
    max_len: int = 255


GATEWAYS = ("stripe", "paypal", "sslcommerz", "bkash")
GATEWAY_LABELS = {"stripe": "Stripe", "paypal": "PayPal", "sslcommerz": "SSLCommerz", "bkash": "bKash"}

SECTIONS: dict[str, list[Field]] = {
    "smtp": [
        Field("enabled", "bool", False),
        Field("host", "host"),
        Field("port", "int", 587),
        Field("security", "choice", "starttls", ("starttls", "ssl", "none")),
        Field("username", "text"),
        Field("password", "secret"),
        Field("from_email", "email"),
        Field("from_name", "text", "", max_len=120),
    ],
    "payments": [
        Field("stripe_enabled", "bool", False),
        Field("stripe_mode", "choice", "test", ("test", "live")),
        Field("stripe_publishable_key", "text", max_len=300),
        Field("stripe_secret_key", "secret"),
        Field("stripe_webhook_secret", "secret"),
        Field("paypal_enabled", "bool", False),
        Field("paypal_mode", "choice", "sandbox", ("sandbox", "live")),
        Field("paypal_client_id", "text", max_len=300),
        Field("paypal_client_secret", "secret"),
        Field("sslcommerz_enabled", "bool", False),
        Field("sslcommerz_mode", "choice", "sandbox", ("sandbox", "live")),
        Field("sslcommerz_store_id", "text", max_len=120),
        Field("sslcommerz_store_password", "secret"),
        Field("bkash_enabled", "bool", False),
        Field("bkash_mode", "choice", "sandbox", ("sandbox", "live")),
        Field("bkash_app_key", "text", max_len=300),
        Field("bkash_app_secret", "secret"),
        Field("bkash_username", "text", max_len=120),
        Field("bkash_password", "secret"),
    ],
    "sms": [
        Field("enabled", "bool", False),
        Field("provider", "choice", "custom", ("twilio", "bulksmsbd", "custom")),
        Field("api_url", "url", max_len=300),
        Field("api_key", "secret"),
        Field("api_secret", "secret"),
        Field("sender_id", "text", max_len=40),
    ],
}


def _fields(section: str) -> list[Field]:
    if section not in SECTIONS:
        raise HTTPException(404, "Unknown settings section")
    return SECTIONS[section]


def _rows(db: Session, section: str) -> dict[str, AppSetting]:
    rows = db.scalars(select(AppSetting).where(AppSetting.key.like(f"{section}.%"))).all()
    return {r.key.split(".", 1)[1]: r for r in rows}


def _plain(f: Field, raw: str | None):
    if raw is None:
        return f.default
    if f.kind == "bool":
        return raw == "1"
    if f.kind == "int":
        try:
            return int(raw)
        except ValueError:
            return f.default
    return raw


def get_section(db: Session, section: str) -> dict:
    """Values for the settings page. Secrets: "" + "<name>_set" (bool) - never the value."""
    rows = _rows(db, section)
    out: dict = {}
    for f in _fields(section):
        row = rows.get(f.name)
        if f.kind == "secret":
            is_set = bool(row and secret_store.decrypt(row.value) is not None)
            out[f.name] = ""
            out[f"{f.name}_set"] = is_set
            out[f"{f.name}_mask"] = secret_store.mask(is_set)
        else:
            out[f.name] = _plain(f, row.value if row else None)
    return out


def get_value(db: Session, section: str, name: str):
    """Server-side read of one field (secrets decrypted). Never send the result to the browser."""
    f = next((x for x in _fields(section) if x.name == name), None)
    if f is None:
        raise KeyError(name)
    row = db.get(AppSetting, f"{section}.{name}")
    if f.kind == "secret":
        return secret_store.decrypt(row.value) if row else None
    return _plain(f, row.value if row else None)


def _validate(f: Field, value) -> str:
    """Normalised text to store, or HTTPException(400) with a readable message."""
    label = f.name.replace("_", " ")
    if f.kind == "bool":
        if not isinstance(value, bool):
            raise HTTPException(400, f"{label}: expected true or false")
        return "1" if value else "0"
    if f.kind == "int":
        try:
            n = int(value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, f"{label}: enter a whole number") from exc
        if not 1 <= n <= 65535:
            raise HTTPException(400, f"{label}: must be between 1 and 65535")
        return str(n)
    text = "" if value is None else str(value).strip()
    if len(text) > f.max_len or "\n" in text or "\r" in text:
        raise HTTPException(400, f"{label}: max. {f.max_len} characters on one line")
    if f.kind == "choice" and text not in f.choices:
        raise HTTPException(400, f"{label}: choose one of {', '.join(f.choices)}")
    if text and f.kind == "email" and not EMAIL_RE.match(text):
        raise HTTPException(400, f"{label}: enter a valid email address")
    if text and f.kind == "host" and not HOST_RE.match(text):
        raise HTTPException(400, f"{label}: enter a host name such as smtp.example.org")
    if text and f.kind == "url" and not text.startswith("https://"):
        raise HTTPException(400, f"{label}: must start with https://")
    return text


def save_section(db: Session, section: str, data: dict, demo_mode: bool) -> dict:
    """Store the fields present in ``data``. Returns {"saved": [...], "skipped_secrets": [...]}."""
    fields = _fields(section)
    known = {f.name for f in fields} | {f"{f.name}_clear" for f in fields if f.kind == "secret"}
    unknown = sorted(set(data) - known - {f"{f.name}_set" for f in fields} - {f"{f.name}_mask" for f in fields})
    if unknown:
        raise HTTPException(400, f"Unknown field(s): {', '.join(unknown)}")
    saved, skipped = [], []
    staged: list[tuple[str, str | None, bool]] = []
    for f in fields:
        key = f"{section}.{f.name}"
        if f.kind == "secret":
            if data.get(f"{f.name}_clear") is True:
                if demo_mode:
                    skipped.append(f.name)
                    continue
                staged.append((key, None, True))
                continue
            value = data.get(f.name)
            if value in (None, ""):
                continue  # empty = keep what is stored
            if not isinstance(value, str) or len(value) > 500 or "\n" in value:
                raise HTTPException(400, f"{f.name.replace('_', ' ')}: max. 500 characters on one line")
            if demo_mode:
                skipped.append(f.name)  # the public demo never stores secrets
                continue
            staged.append((key, secret_store.encrypt(value), True))
            continue
        if f.name not in data:
            continue
        staged.append((key, _validate(f, data[f.name]), False))
    for key, value, is_secret in staged:  # all fields validated: now write
        row = db.get(AppSetting, key)
        if value is None:
            if row is not None:
                db.delete(row)
            saved.append(key.split(".", 1)[1])
            continue
        if row is None:
            row = AppSetting(key=key)
            db.add(row)
        row.value, row.is_secret, row.updated_at = value, is_secret, utcnow()
        saved.append(key.split(".", 1)[1])
    db.commit()
    return {"saved": saved, "skipped_secrets": skipped}


def enabled_gateways(db: Session) -> list[dict]:
    """Payment gateways switched on in Settings > Payments (shown as payment methods when collecting fees)."""
    cfg = get_section(db, "payments")
    return [
        {"id": g, "label": GATEWAY_LABELS[g], "mode": cfg.get(f"{g}_mode")} for g in GATEWAYS if cfg.get(f"{g}_enabled")
    ]


def smtp_send(db: Session, to: str, subject: str, body: str, timeout: int = 15) -> None:
    """Send one email with the stored SMTP settings (used by the "Send test email" button)."""
    cfg = get_section(db, "smtp")
    if not cfg["host"] or not cfg["from_email"]:
        raise HTTPException(400, "Enter and save the SMTP host and the From address first.")
    if not EMAIL_RE.match(to or ""):
        raise HTTPException(400, "Enter a valid recipient email address.")
    msg = EmailMessage()
    msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>" if cfg["from_name"] else cfg["from_email"]
    msg["To"], msg["Subject"] = to, subject
    msg.set_content(body)
    password = get_value(db, "smtp", "password")
    context = ssl.create_default_context()
    try:
        if cfg["security"] == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=timeout, context=context)
        else:
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=timeout)
        with server:
            if cfg["security"] == "starttls":
                server.starttls(context=context)
            if cfg["username"]:
                server.login(cfg["username"], password or "")
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise HTTPException(502, f"Sending failed: {type(exc).__name__}: {str(exc)[:200]}") from exc

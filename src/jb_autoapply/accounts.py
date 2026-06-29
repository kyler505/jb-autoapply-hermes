"""ATS account credential store.

Stores per-tenant Workday/ATS account credentials so they can be
reused across sessions instead of creating new accounts every time.
"""

from __future__ import annotations

import json
import os
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACCOUNTS_FILE = Path.home() / ".hermes" / "ats_accounts.json"


def _load() -> dict[str, Any]:
    """Load the accounts database."""
    if not ACCOUNTS_FILE.exists():
        return {}
    return json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))


def _save(data: dict[str, Any]) -> None:
    """Save the accounts database with restricted permissions."""
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_FILE.write_text(
        json.dumps(data, indent=2, default=str), encoding="utf-8"
    )
    ACCOUNTS_FILE.chmod(0o600)


def tenant_domain(url: str) -> str | None:
    """Extract the Workday tenant domain from a job URL.

    'https://cox.wd1.myworkdayjobs.com/...' -> 'cox.wd1.myworkdayjobs.com'
    'https://kla.wd1.myworkdayjobs.com/...' -> 'kla.wd1.myworkdayjobs.com'
    'https://jobs.ashbyhq.com/...' -> None (Ashby uses SSO/social login)
    """
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.lower()
    if "myworkdayjobs" in domain:
        return domain
    if "icims" in domain:
        return domain
    # Ashby, Greenhouse, Lever typically use social login — no stored creds
    return None


def resolve_tenant_name(domain: str) -> str:
    """Short human name for the tenant (e.g. 'Cox', 'KLA', 'Sentry')."""
    parts = domain.split(".")
    return parts[0].title() if parts else domain


def get_account(domain: str) -> dict[str, Any] | None:
    """Get a saved account for the given tenant domain, or None."""
    data = _load()
    return data.get(domain)


def list_accounts() -> dict[str, Any]:
    """List all stored accounts (passwords masked)."""
    data = _load()
    result = {}
    for domain, acct in data.items():
        result[domain] = {
            "company": resolve_tenant_name(domain),
            "email": acct.get("email"),
            "password": "****" + acct.get("password", "")[-4:],
            "created": acct.get("created_at", "?"),
        }
    return result


def save_account(
    domain: str,
    email: str,
    password: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save or update an account for the given tenant domain."""
    data = _load()
    data[domain] = {
        "email": email,
        "password": password,
        "domain": domain,
        "company": resolve_tenant_name(domain),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "job_ids": [],
        **(metadata or {}),
    }
    _save(data)
    return data[domain]


def generate_password(length: int = 16) -> str:
    """Generate a Workday-compatible password.

    Requirements: 8+ chars, uppercase, lowercase, digit, special char.
    """
    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    special = "!@#$%^&*"
    # Guarantee at least one of each
    pw = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    # Fill the rest
    all_chars = upper + lower + digits + special
    pw += [secrets.choice(all_chars) for _ in range(length - 4)]
    secrets.SystemRandom().shuffle(pw)
    return "".join(pw)


def has_account(url: str) -> bool:
    """Check if we have credentials stored for this job's ATS tenant."""
    domain = tenant_domain(url)
    if not domain:
        return False
    return get_account(domain) is not None


def get_or_create_account(
    url: str,
    email: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | tuple[dict[str, Any], str]:
    """Get existing account or create a new one with a generated password.

    Returns (account_dict, password) — password is None if reusing existing.
    """
    domain = tenant_domain(url)
    if not domain:
        msg = f"Cannot determine ATS tenant from URL: {url}"
        raise ValueError(msg)

    existing = get_account(domain)
    if existing:
        return existing, existing["password"]

    password = generate_password()
    account = save_account(domain, email, password, metadata=metadata)
    return account, password

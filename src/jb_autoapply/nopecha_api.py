"""CAPTCHA solving via NopeCHA API (free tier: 100 solves/day by IP).

No API key needed — the free tier works by IP address. For higher quotas,
set NOPECHA_KEY environment variable.

Usage:
    token = await solve_recaptcha(page, site_key, page_url)
    await inject_token(page, token)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

_API_BASE = "https://api.nopecha.com"


def get_api_key() -> str | None:
    key = os.environ.get("NOPECHA_KEY")
    return key.strip() if key else None


def is_configured() -> bool:
    """NopeCHA always works — free 100/day by IP."""
    return True


def status() -> dict[str, Any]:
    """Check NopeCHA account status (plan, credits, quota)."""
    try:
        resp = urllib.request.urlopen(f"{_API_BASE}/status", timeout=10)
        return json.loads(resp.read())
    except Exception:
        return {"error": "could not check status"}


def _api_request(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Make a POST request to NopeCHA API and return the response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_API_BASE}/solve",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  ❌ NopeCHA API error ({e.code}): {body[:200]}")
        return None
    except urllib.error.URLError as e:
        print(f"  ❌ NopeCHA connection error: {e.reason}")
        return None


async def solve_recaptcha(page, site_key: str, page_url: str, *, max_wait: int = 120) -> str | None:
    """Solve reCAPTCHA via NopeCHA API.

    Sends the site key and page URL, polls for result, returns the token.

    Args:
        page: Playwright page (unused — here for API compatibility)
        site_key: The reCAPTCHA site key
        page_url: Full URL of the page with the CAPTCHA
        max_wait: Maximum seconds to wait for solve

    Returns:
        g-recaptcha-response token string, or None on failure.
    """
    print(f"  🧠 Solving CAPTCHA via NopeCHA API ...")

    # Build the solve request
    payload: dict[str, Any] = {
        "type": "recaptcha",
        "sitekey": site_key,
        "url": page_url,
        # Optional proxy — omit to use our IP
    }

    result = _api_request(payload)
    if result is None:
        return None

    # NopeCHA returns the token directly, or an error
    if isinstance(result, dict) and "data" in result:
        token = result["data"]
        print(f"  ✓ CAPTCHA solved ({len(token)} chars)")
        return token

    error = result.get("error", "unknown error")
    message = result.get("message", "")
    print(f"  ❌ CAPTCHA solve failed: {error} {message}".strip())
    return None


async def inject_token(page, token: str) -> bool:
    """Inject a solved reCAPTCHA token into the page.

    Places the token into the g-recaptcha-response textarea and
    dispatches events to trigger form validation callbacks.
    """
    try:
        success = await page.evaluate(f"""() => {{
            const ta = document.getElementById('g-recaptcha-response');
            if (ta) {{
                ta.innerHTML = '{token}';
                ta.value = '{token}';
            }}

            // Also try finding by name or class
            const alt = document.querySelector('textarea[name="g-recaptcha-response"]');
            if (alt) {{
                alt.innerHTML = '{token}';
                alt.value = '{token}';
            }}

            // Trigger callbacks
            try {{
                if (typeof grecaptcha !== 'undefined') {{
                    grecaptcha.enterprise?.ready?.();
                }}
            }} catch(e) {{}}

            // Dispatch events
            const el = ta || alt;
            if (el) {{
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}

            return true;
        }}""")
        return True
    except Exception as e:
        print(f"  ⚠ Token injection error: {e}")
        return False


async def find_site_key(page) -> str | None:
    """Extract the reCAPTCHA site key from the current page DOM."""
    try:
        site_key = await page.evaluate("""() => {
            // data-sitekey attribute
            const el = document.querySelector('[data-sitekey]');
            if (el) return el.getAttribute('data-sitekey');

            // recaptcha iframe src
            const frame = document.querySelector('iframe[src*="recaptcha"]');
            if (frame) {
                const m = frame.src.match(/[?&]k=([^&]+)/);
                if (m) return m[1];
            }

            // script src
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                if (s.src && s.src.includes('recaptcha')) {
                    const m = s.src.match(/[?&]k=([^&]+)/);
                    if (m) return m[1];
                }
            }

            return null;
        }""")
        return site_key
    except Exception:
        return None

"""Capsolver API wrapper for automated CAPTCHA solving.

Uses capsolver.com API (~$3/1000 solves) to solve reCAPTCHA v2/v3
challenges. Requires CAPSOLVER_KEY environment variable.

Usage:
    token = await solve_recaptcha(page, site_key, page_url)
    if token:
        await inject_token(page, token)
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

CAPSOLVER_KEY_ENV = "CAPSOLVER_KEY"
_API_BASE = "https://api.capsolver.com"


def get_api_key() -> str | None:
    key = os.environ.get(CAPSOLVER_KEY_ENV)
    return key.strip() if key else None


def is_configured() -> bool:
    return bool(get_api_key())


def _api_request(endpoint: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Make a POST request to Capsolver API and return the response."""
    url = f"{_API_BASE}/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"  ❌ Capsolver API error: {e}")
        return None


def create_task(site_key: str, page_url: str, *, is_invisible: bool = False) -> dict[str, Any] | None:
    """Submit a reCAPTCHA task to Capsolver and get back a task ID.

    Args:
        site_key: The reCAPTCHA site key (data-sitekey)
        page_url: The full page URL where the CAPTCHA appears
        is_invisible: True for invisible reCAPTCHA v2

    Returns:
        Task result dict with 'taskId' on success, or None on failure.
    """
    key = get_api_key()
    if not key:
        print("  ❌ CAPSOLVER_KEY not set")
        return None

    task_type = "ReCaptchaV2EnterpriseTask" if is_invisible else "ReCaptchaV2Task"
    payload = {
        "clientKey": key,
        "task": {
            "type": task_type,
            "websiteURL": page_url,
            "websiteKey": site_key,
        },
    }
    return _api_request("createTask", payload)


def get_task_result(task_id: str, *, max_wait: int = 120) -> dict[str, Any] | None:
    """Poll Capsolver for task result until solved or timeout.

    Args:
        task_id: The task ID from create_task
        max_wait: Maximum seconds to wait

    Returns:
        Result dict with 'solution' containing gRecaptchaResponse, or None.
    """
    key = get_api_key()
    if not key:
        return None

    deadline = time.time() + max_wait
    while time.time() < deadline:
        payload = {"clientKey": key, "taskId": task_id}
        result = _api_request("getTaskResult", payload)
        if result is None:
            return None
        status = result.get("status", "")
        if status == "ready":
            return result
        if status == "failed":
            print(f"  ❌ Capsolver task failed: {result.get('errorDescription', 'unknown')}")
            return None
        # Still processing
        time.sleep(3)

    print(f"  ⚠ Capsolver task timed out after {max_wait}s")
    return None


async def solve_recaptcha(page, site_key: str, page_url: str, *, max_wait: int = 120) -> str | None:
    """Solve reCAPTCHA on the current page.

    Returns the g-recaptcha-response token string, or None on failure.
    """
    print(f"  🧠 Solving CAPTCHA via Capsolver (site key: {site_key[:8]}...)")

    task = create_task(site_key, page_url)
    if not task or "taskId" not in task:
        return None

    task_id = task["taskId"]
    result = get_task_result(task_id, max_wait=max_wait)
    if not result:
        return None

    solution = result.get("solution", {})
    token = solution.get("gRecaptchaResponse") or solution.get("token")
    if not token:
        print(f"  ❌ No token in Capsolver response")
        return None

    print(f"  ✓ CAPTCHA solved ({len(token)} chars)")
    return token


async def inject_token(page, token: str) -> bool:
    """Inject a reCAPTCHA token into the page and trigger the callback.

    Places the token into the textarea and calls the callback if registered.
    """
    try:
        success = await page.evaluate(f"""() => {{
            // Set the token in the response textarea
            const ta = document.getElementById('g-recaptcha-response');
            if (ta) {{
                ta.innerHTML = '{token}';
                ta.value = '{token}';
            }}

            // Try to find and trigger the callback
            try {{
                // Greenhouse uses grecaptcha.enterprise
                if (typeof grecaptcha !== 'undefined') {{
                    grecaptcha.enterprise?.ready?.();
                }}
            }} catch(e) {{}}

            // Dispatch an input event to wake up any listeners
            if (ta) {{
                ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
                ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}

            return true;
        }}""")
        return success
    except Exception as e:
        print(f"  ⚠ Token injection error: {e}")
        return False


async def find_site_key(page) -> str | None:
    """Extract the reCAPTCHA site key from the current page."""
    try:
        site_key = await page.evaluate("""() => {
            // Check for data-sitekey attribute
            const el = document.querySelector('[data-sitekey]');
            if (el) return el.getAttribute('data-sitekey');

            // Check for recaptcha iframe src
            const frame = document.querySelector('iframe[src*="recaptcha"]');
            if (frame) {
                const match = frame.src.match(/[?&]k=([^&]+)/);
                if (match) return match[1];
            }

            // Check for grecaptcha.render calls
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                if (s.src && s.src.includes('recaptcha')) {
                    const match = s.src.match(/[?&]k=([^&]+)/);
                    if (match) return match[1];
                }
            }

            return null;
        }""")
        return site_key
    except Exception:
        return None

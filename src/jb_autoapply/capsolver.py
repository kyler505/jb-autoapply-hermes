"""CAPTCHA solving via Capsolver API (~$3/1000 solves).

Requires CAPSOLVER_KEY environment variable. Sign up at https://capsolver.com
and add funds to get an API key.

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

_API_BASE = "https://api.capsolver.com"


def get_api_key() -> str | None:
    key = os.environ.get("CAPSOLVER_KEY")
    return key.strip() if key else None


def is_configured() -> bool:
    return bool(get_api_key())


def status() -> str:
    key = get_api_key()
    if key:
        return f"✓ key configured"
    return "✗ CAPSOLVER_KEY not set"


def _api_request(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Make a POST request to Capsolver API and return the response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_API_BASE}/createTask",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        print(f"  ❌ Capsolver API error ({e.code}): {body}")
        return None
    except urllib.error.URLError as e:
        print(f"  ❌ Capsolver connection error: {e.reason}")
        return None


def _get_task_result(task_id: str, *, max_wait: int = 120) -> dict[str, Any] | None:
    """Poll Capsolver for task result until solved or timeout."""
    key = get_api_key()
    if not key:
        return None

    deadline = time.time() + max_wait
    while time.time() < deadline:
        payload = {"clientKey": key, "taskId": task_id}
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{_API_BASE}/getTaskResult",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            result = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  ⚠ Capsolver poll error: {e}")
            time.sleep(3)
            continue

        status = result.get("status", "")
        if status == "ready":
            return result
        if status == "failed":
            print(f"  ❌ Capsolver task failed: {result.get('errorDescription', 'unknown')}")
            return None
        time.sleep(3)

    print(f"  ⚠ Capsolver task timed out after {max_wait}s")
    return None


async def solve_recaptcha(page, site_key: str, page_url: str, *, max_wait: int = 120) -> str | None:
    """Solve reCAPTCHA via Capsolver API.

    Returns the g-recaptcha-response token string, or None on failure.
    """
    key = get_api_key()
    if not key:
        print(f"  ❌ CAPSOLVER_KEY not set")
        return None

    print(f"  🧠 Solving CAPTCHA via Capsolver ...")

    # Create task
    payload = {
        "clientKey": key,
        "task": {
            "type": "ReCaptchaV2EnterpriseTask",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "isInvisible": False,
        },
    }

    # Try standard ReCaptchaV2Task if Enterprise fails
    task = _api_request(payload)
    if task is None:
        return None

    task_id = task.get("taskId")
    if not task_id:
        task_error = task.get("errorDescription", str(task)[:100])
        print(f"  ❌ Capsolver task creation failed: {task_error}")
        return None

    print(f"  ⏳ Task created ({task_id[:12]}...), waiting for solve...")
    result = _get_task_result(task_id, max_wait=max_wait)
    if not result:
        return None

    solution = result.get("solution", {})
    token = solution.get("gRecaptchaResponse") or solution.get("token")
    if not token:
        print(f"  ❌ No token in Capsolver response")
        return None

    print(f"  ✓ CAPTCHA solved ({len(token)} chars)")
    return token


async def find_site_key(page) -> str | None:
    """Extract the reCAPTCHA site key from the current page."""
    try:
        site_key = await page.evaluate("""() => {
            const el = document.querySelector('[data-sitekey]');
            if (el) return el.getAttribute('data-sitekey');

            const frame = document.querySelector('iframe[src*="recaptcha"]');
            if (frame) {
                const m = frame.src.match(/[?&]k=([^&]+)/);
                if (m) return m[1];
            }
            return null;
        }""")
        return site_key
    except Exception:
        return None


async def inject_token(page, token: str) -> bool:
    """Inject a solved reCAPTCHA token into the page."""
    try:
        await page.evaluate(f"""() => {{
            const ta = document.getElementById('g-recaptcha-response');
            if (ta) {{ ta.innerHTML = '{token}'; ta.value = '{token}'; }}
            const alt = document.querySelector('textarea[name="g-recaptcha-response"]');
            if (alt) {{ alt.innerHTML = '{token}'; alt.value = '{token}'; }}
            try {{ grecaptcha.enterprise?.ready?.(); }} catch(e) {{}}
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

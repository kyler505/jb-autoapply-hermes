"""Unified apply runner for the auto-apply pipeline.

Reads the queue, classifies jobs by ATS type, dispatches to the correct
handler, and writes results back to Obsidian job notes with full status tracking.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from . import accounts as _accounts
from . import config
from . import nopecha as _nopecha
from . import simplify as _simplify
from .adapters import detect_site
from .selector import build_queue
from .vault import read_note, set_fm_field, write_note


# ---------------------------------------------------------------------------
# Per-ATS daily rate limits (conservative)
# ---------------------------------------------------------------------------
ATS_RATE_LIMITS: dict[str, int] = {
    "ashby": 5,       # 5 roles / 90 days (known limit)
    "greenhouse": 20,
    "workday": 50,
    "lever": 15,
    "smartrecruiters": 15,
    "icims": 10,
    "generic": 30,
}

# Chromium profile directory (ephemeral per run)
PROFILE = "/tmp/autoapply-run"
RESUME_PATH = Path.home() / ".hermes" / ".playwright-mcp" / "resume.pdf"


# ---------------------------------------------------------------------------
# Rate tracker
# ---------------------------------------------------------------------------
class RateTracker:
    """Tracks per-ATS attempt counts to respect rate limits."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._date: str = date.today().isoformat()

    def can_attempt(self, site: str) -> bool:
        limit = ATS_RATE_LIMITS.get(site, 30)
        return self._counts.get(site, 0) < limit

    def record_attempt(self, site: str) -> None:
        self._counts[site] = self._counts.get(site, 0) + 1

    @property
    def summary(self) -> str:
        parts = sorted(self._counts.items())
        return " | ".join(
            f"{k}: {v}/{ATS_RATE_LIMITS.get(k, 30)}" for k, v in parts
        )


# ---------------------------------------------------------------------------
# Vault write-back
# ---------------------------------------------------------------------------
def write_back(job: dict[str, Any], result: dict[str, Any]) -> None:
    """Write apply result back to the job's Obsidian note."""
    path = Path(job["path"])
    _, fm_text, body = read_note(path)

    updates: dict[str, Any] = {
        "apply_method": result.get("method", "auto"),
        "apply_result": result.get("result", "error"),
    }

    if result.get("status"):
        updates["status"] = result["status"]
    if result.get("applied_date"):
        updates["applied_date"] = result["applied_date"]
    if result.get("confirmation"):
        updates["confirmation"] = result["confirmation"]
    if result.get("resume_used"):
        updates["resume_used"] = result["resume_used"]
    if result.get("needs_review") is not None:
        updates["needs_review"] = result["needs_review"]
    if result.get("error"):
        updates["apply_error"] = result["error"][:200]

    for key, val in updates.items():
        fm_text = set_fm_field(fm_text, key, val)

    write_note(path, fm_text, body)


# ---------------------------------------------------------------------------
# Helper: safe click with fallback
# ---------------------------------------------------------------------------
async def _click(page, locator_str: str, *, timeout: int = 3000, force: bool = True) -> bool:
    """Click a locator if visible; return success."""
    try:
        el = page.locator(locator_str)
        if await el.is_visible(timeout=timeout):
            await el.click(force=force, timeout=timeout)
            return True
    except Exception:
        pass
    return False


async def _click_text(page, text: str, *, timeout: int = 2000) -> bool:
    """Click a button by visible text."""
    try:
        btn = page.get_by_role("button", name=text, exact=False)
        if await btn.count() > 0 and await btn.first.is_visible(timeout=timeout):
            await btn.first.click(force=True, timeout=timeout)
            return True
    except Exception:
        pass
    # fallback: has-text selector
    try:
        el = page.locator(f'button:has-text("{text}"), div[role="button"]:has-text("{text}")').first
        if await el.is_visible(timeout=500):
            await el.click(force=True, timeout=timeout)
            return True
    except Exception:
        pass
    return False


async def _remove_overlays(page) -> None:
    """Remove Workday click_filter overlays that block button clicks."""
    try:
        await page.evaluate("""() => {
            document.querySelectorAll('[data-automation-id="click_filter"]')
                .forEach(e => e.remove());
        }""")
    except Exception:
        pass


async def _wait_for_stable(page, timeout: float = 3.0, interval: float = 0.5) -> None:
    """Wait until page body text stops changing (settled)."""
    last = ""
    for _ in range(int(timeout / interval)):
        await page.wait_for_timeout(interval * 1000)
        try:
            cur = await page.inner_text("body")
            if cur == last:
                return
            last = cur
        except Exception:
            return


# ---------------------------------------------------------------------------
# ATS-specific handlers
# ---------------------------------------------------------------------------
async def _handle_workday(page, ctx, job: dict[str, Any], acct: dict[str, Any] | None) -> dict[str, Any]:
    """Workday flow: sign-in, navigate wizard, fill, submit.

    Handles multiple Workday states:
    - Already signed in → direct to wizard
    - Sign-in link visible → click, fill, submit
    - Create Account form → fill, submit
    - Wrong password → detect error text
    - Account already exists → switch to sign-in mode
    """
    url: str = job["url"]
    company: str = job["company"]
    email = "kcao@tamu.edu"
    password = acct["password"] if acct else None
    domain = _accounts.tenant_domain(url)

    async def _page_debug(label: str) -> str:
        """Log a snippet of the current page for debugging."""
        try:
            title = await page.title()
            url_cur = page.url[:80]
            body = (await page.inner_text("body"))[:300]
            # Check for common error indicators
            errors = []
            for phrase in ["wrong email", "incorrect", "invalid", "not found", "does not exist", "locked"]:
                if phrase in body.lower():
                    errors.append(phrase)
            debug = f"[{label}] {title[:50]} | {url_cur}"
            if errors:
                debug += f" | ⚠ ERRORS: {', '.join(errors)}"
            print(f"  {debug}")
            return body
        except Exception as e:
            print(f"  [{label}] error getting debug: {e}")
            return ""

    async def _find_visible_button(page, *names: str) -> str | None:
        """Find the first visible button matching any of the given names."""
        for name in names:
            try:
                btn = page.get_by_role("button", name=name, exact=False)
                if await btn.count() > 0:
                    for i in range(min(await btn.count(), 5)):
                        try:
                            if await btn.nth(i).is_visible(timeout=300):
                                # Scroll into view
                                await btn.nth(i).scroll_into_view_if_needed(timeout=1000)
                                return name
                        except Exception:
                            pass
            except Exception:
                pass
        return None

    async def _click_visible_button(page, *names: str) -> bool:
        """Click the first visible button matching any name."""
        name = await _find_visible_button(page, *names)
        if name:
            print(f"  → Clicking '{name}'")
            try:
                btn = page.get_by_role("button", name=name, exact=False)
                await btn.first.scroll_into_view_if_needed(timeout=2000)
                await btn.first.click(force=True, timeout=5000)
                return True
            except Exception:
                pass
        return False

    apply_url = url.rstrip("/") + "/apply/applyManually"

    # -- PHASE 1: Navigate to apply page --
    print(f"  Navigating to apply page...")
    try:
        await page.goto(apply_url, timeout=20000, wait_until="domcontentloaded")
    except Exception as e:
        print(f"  ⚠ Navigation timeout: {e}")
    await page.wait_for_timeout(2000)
    body_snapshot = await _page_debug("apply-page")

    # Dead posting check
    if "doesn't exist" in body_snapshot.lower() or "not exist" in body_snapshot.lower():
        print(f"  ✗ Job posting not found (dead link)")
        return _error_result("dead_link", "Job posting no longer exists on Workday")

    # -- PHASE 2: Sign in if needed --
    if password:
        sl = page.locator('[data-automation-id="signInLink"]')
        if await sl.is_visible(timeout=2000):
            print(f"  Sign-in link visible, clicking...")
            await sl.click()
            await page.wait_for_timeout(2000)
            await _page_debug("after-signin-click")

            # Fill credentials
            email_field = page.locator('[data-automation-id="email"]')
            if await email_field.is_visible(timeout=3000):
                await email_field.fill(email)
                pw_field = page.locator('[data-automation-id="password"]')
                if await pw_field.is_visible(timeout=1000):
                    await pw_field.fill(password)
                    await page.wait_for_timeout(500)

                    # Strategy 1: Try clicking the overlay directly (it has the JS handler)
                    overlay = page.locator('[data-automation-id="click_filter"][aria-label="Sign In"]')
                    if await overlay.is_visible(timeout=500):
                        print(f"  Clicking Sign In overlay directly...")
                        await overlay.click(force=True, timeout=5000)
                        await page.wait_for_timeout(5000)
                    else:
                        # Fallback: generic click_filter
                        overlay_generic = page.locator('[data-automation-id="click_filter"]')
                        if await overlay_generic.is_visible(timeout=500):
                            await overlay_generic.click(force=True, timeout=5000)
                            await page.wait_for_timeout(5000)
                    
                    # Check if still on sign-in
                    if await email_field.is_visible(timeout=1000):
                        # Strategy 2: Enter key
                        print(f"  Submitting via Enter...")
                        await page.keyboard.press("Enter")
                        await page.wait_for_timeout(3000)

                        # Strategy 3: If still on sign-in, remove overlay and click button
                        if await email_field.is_visible(timeout=1000):
                            print(f"  Still on sign-in, removing overlay...")
                            await _remove_overlays(page)
                            await _click(page, '[data-automation-id="signInSubmitButton"]', timeout=3000)
                            await page.wait_for_timeout(5000)

                    # Check result
                    await _page_debug("after-signin-submit")
                    body = await page.inner_text("body")

                    # Check for error
                    if any(p in body.lower() for p in ["wrong email", "incorrect", "invalid", "not found", "locked"]):
                        print(f"  ❌ Sign-in failed: wrong email or password")
                        return _error_result("password_wrong",
                            f"Wrong email or password for {domain} — run 'jb-autoapply accounts-verify'")

                    # Check for signed-in indicator
                    signed_in = await page.locator(
                        '[data-automation-id="accountMenuButton"], '
                        'button:has-text("My Account"), '
                        '[aria-label*="account" i]'
                    ).is_visible(timeout=3000)
                    if signed_in:
                        print(f"  ✓ Signed in")
                    else:
                        print(f"  ⚠ Sign-in state uncertain — continuing")
        else:
            # Check if already signed in
            signed_in = await page.locator(
                '[data-automation-id="accountMenuButton"]'
            ).is_visible(timeout=1000)
            if signed_in:
                print(f"  Already signed in ✓")
    else:
        print(f"  No stored credentials — will create account if needed")

    # -- PHASE 3: Navigate to job and click Apply --
    print(f"  Navigating to job posting...")
    await page.goto(url, timeout=30000)
    await page.wait_for_timeout(3000)

    # Dead posting check on job page
    try:
        job_body = await page.inner_text("body")
        if "doesn't exist" in job_body.lower() or "not exist" in job_body.lower():
            print(f"  ✗ Job posting not found (dead link)")
            return _error_result("dead_link", "Job posting no longer exists on Workday")
    except Exception:
        pass

    # Accept cookies
    await _click_visible_button(page, "Accept", "Accept Cookies", "Accept All", "I Accept")
    await page.wait_for_timeout(1000)

    await _page_debug("job-page")

    # Click Apply / Adventure button
    await _click(page, '[data-automation-id="adventureButton"]', timeout=3000)
    await page.wait_for_timeout(3000)

    # Click Apply Manually
    if not await _click(page, '[data-automation-id="applyManually"]', timeout=4000):
        # Maybe already at the form or using "Use My Last Application"
        await _page_debug("after-apply")
    await page.wait_for_timeout(3000)

    await _page_debug("after-apply-manually")

    # -- PHASE 4: Handle wizard sign-in / create-account step --
    # After clicking Apply Manually, Workday may show:
    #   - "Create Account" (email field + password + checkbox)
    #   - "Sign In" (email field + password)
    #   - A "Sign In" modal/overlay with a different HTML structure
    async def _handle_wizard_auth(page, pwd: str) -> bool:
        """Try to handle a sign-in/auth wizard step. Returns True if advanced past it."""
        # Find the email field using multiple strategies
        step_email = page.locator('[data-automation-id="email"]')
        if not await step_email.is_visible(timeout=500):
            # Fallback: look for email input by type or label
            step_email = page.locator(
                'input[type="email"], '
                'input[name="email"], '
                'input[data-automation-id*="email"], '
                'input[aria-label*="Email" i]'
            ).first
        if await step_email.is_visible(timeout=2000):
            print(f"  Wizard auth: email field found")

            # Check for error text
            body = await page.inner_text("body")
            if any(p in body.lower() for p in ["wrong email", "incorrect", "locked", "already exists"]):
                for p in ["wrong email", "incorrect", "locked", "already exists"]:
                    if p in body.lower():
                        print(f"  ❌ Account error: {p}")
                        return False

            await step_email.fill(email)
            pw_field = page.locator('[data-automation-id="password"], input[type="password"]').first
            if await pw_field.is_visible(timeout=500):
                await pw_field.fill(pwd)
                # Workday Create Account requires a "Verify New Password" field
                verify_pw = page.locator('[data-automation-id="verifyPassword"]')
                if await verify_pw.is_visible(timeout=300):
                    await verify_pw.fill(pwd)
                    await page.wait_for_timeout(200)

            # Check for Create Account checkbox
            cb = page.locator('[data-automation-id="createAccountCheckbox"]')
            if await cb.is_visible(timeout=300):
                await cb.check()

            await page.wait_for_timeout(300)

            # Try multiple submission strategies
            overlay = page.locator('[data-automation-id="click_filter"]').first
            if await overlay.is_visible(timeout=300):
                print(f"  Clicking overlay...")
                await overlay.click(force=True, timeout=3000)
                await page.wait_for_timeout(3000)
            # If still on auth step, try clicking the specific Create Account overlay
            if await step_email.is_visible(timeout=500):
                create_overlay = page.locator(
                    '[data-automation-id="click_filter"][aria-label="Create Account"]'
                ).first
                if await create_overlay.is_visible(timeout=300):
                    print(f"  Clicking Create Account overlay...")
                    await create_overlay.click(force=True, timeout=5000)
                    await page.wait_for_timeout(3000)

            # Check if still on auth step
            if await step_email.is_visible(timeout=500):
                print(f"  Trying Enter key...")
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(3000)

            if await step_email.is_visible(timeout=500):
                print(f"  Trying submit button directly...")
                await _remove_overlays(page)
                # Click any submit-button-looking element
                submit_btn = page.locator(
                    '[data-automation-id="createAccountSubmitButton"], '
                    'button[type="submit"], '
                    'button:has-text("Create Account")'
                ).first
                if await submit_btn.is_visible(timeout=500):
                    await submit_btn.click(force=True, timeout=5000)
                    await page.wait_for_timeout(3000)
                # If still visible, try JavaScript dispatchEvent (React workaround)
                if await step_email.is_visible(timeout=500):
                    print(f"  Trying JavaScript click dispatch...")
                    await page.evaluate("""() => {
                        const btn = document.querySelector('[data-automation-id="createAccountSubmitButton"]');
                        if (btn) {
                            btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
                            btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
                            btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
                        }
                    }""")
                    await page.wait_for_timeout(5000)

            if await step_email.is_visible(timeout=500):
                body = await page.inner_text("body")
                if "already exists" in body.lower():
                    print(f"  Account already exists — switching to sign-in mode")
                    await _click_visible_button(page, "Sign In")
                    await page.wait_for_timeout(2000)
                    if password:
                        step_email = page.locator('[data-automation-id="email"], input[type="email"]').first
                        if await step_email.is_visible(timeout=2000):
                            await step_email.fill(email)
                            pw_f = page.locator('[data-automation-id="password"], input[type="password"]').first
                            if await pw_f.is_visible(timeout=500):
                                await pw_f.fill(password)
                                await page.keyboard.press("Enter")
                                await page.wait_for_timeout(4000)
                else:
                    print(f"  ⚠ Could not advance past wizard auth")
                    return False
            return True

        # Check for Sign In modal/overlay (different structure — common on KLA/TAMU/CVS)
        # Look for heading or button text containing "Sign In"
        try:
            heading = page.locator('h1:has-text("Sign In"), h2:has-text("Sign In"), h3:has-text("Sign In")').first
            if await heading.is_visible(timeout=500):
                print(f"  Wizard auth: Sign In heading found (alternative layout)")

                # Many Workday Sign In pages have "Sign in with email" as a separate button
                # that reveals the email/password form
                email_btn = page.locator(
                    '[data-automation-id="SignInWithEmailButton"], '
                    'button:has-text("Sign in with email"), '
                    'button:has-text("Sign in with Email")'
                ).first
                if await email_btn.is_visible(timeout=500):
                    print(f"  Clicking 'Sign in with email' button...")
                    await email_btn.click(force=True, timeout=5000)
                    await page.wait_for_timeout(3000)

                # Now look for email input
                email_input = page.locator(
                    'input[type="email"], '
                    '[data-automation-id="email"], '
                    'input[aria-label*="email" i]'
                ).first
                if await email_input.is_visible(timeout=3000):
                    # Check if we need to create an account first
                    create_acct_link = page.locator(
                        '[data-automation-id="createAccountLink"], '
                        'button:has-text("Create Account"):not([data-automation-id*="Submit"])'
                    ).first
                    if await create_acct_link.is_visible(timeout=500):
                        print(f"  Clicking 'Create Account' link (no existing account)...")
                        await create_acct_link.click(force=True, timeout=3000)
                        await page.wait_for_timeout(2000)
                        # Now on the full Create Account form
                        email_input = page.locator(
                            'input[type="email"], [data-automation-id="email"]'
                        ).first
                        if await email_input.is_visible(timeout=2000):
                            await email_input.fill(email)
                            pw_input = page.locator(
                                'input[type="password"], [data-automation-id="password"]'
                            ).first
                            if await pw_input.is_visible(timeout=500):
                                await pw_input.fill(pwd)
                                verify_pw = page.locator('[data-automation-id="verifyPassword"]')
                                if await verify_pw.is_visible(timeout=300):
                                    await verify_pw.fill(pwd)
                                await page.wait_for_timeout(200)
                                # Click via overlay
                                create_overlay = page.locator(
                                    '[data-automation-id="click_filter"][aria-label="Create Account"]'
                                ).first
                                if await create_overlay.is_visible(timeout=500):
                                    await create_overlay.click(force=True, timeout=5000)
                                else:
                                    submit_btn = page.locator(
                                        '[data-automation-id="createAccountSubmitButton"]'
                                    ).first
                                    if await submit_btn.is_visible(timeout=300):
                                        await submit_btn.click(force=True, timeout=5000)
                                await page.wait_for_timeout(5000)
                                return True
                    else:
                        # Fill Sign In form
                        await email_input.fill(email)
                        pw_input = page.locator(
                            'input[type="password"], '
                            '[data-automation-id="password"]'
                        ).first
                        if await pw_input.is_visible(timeout=1000):
                            await pw_input.fill(pwd)
                            await page.wait_for_timeout(300)
                            # Click the submit overlay directly
                            submit_overlay = page.locator(
                                '[data-automation-id="click_filter"][aria-label="Submit"]'
                            ).first
                            if await submit_overlay.is_visible(timeout=500):
                                await submit_overlay.click(force=True, timeout=5000)
                            else:
                                await _click_visible_button(page, "Sign In")
                            await page.wait_for_timeout(5000)
                            return True
        except Exception:
            pass

        return False  # No auth step detected

    # Run wizard auth handler
    generated_pw = _accounts.generate_password()
    actual_pw = password if password else generated_pw
    if await _handle_wizard_auth(page, actual_pw):
        # If we generated a password and created an account, save it
        if password is None:
            sl = page.locator('button:has-text("Create Account"), [data-automation-id="createAccountSubmitButton"]')
            gone = not await sl.is_visible(timeout=500)
            if gone:
                # Account was created or signed in — save credentials
                if domain:
                    _accounts.save_account(domain, email, actual_pw)
                    print(f"  ✓ Saved new account for {domain}")
        await _page_debug("after-wizard-auth")

    # -- PHASE 5: Wizard walk-through with Simplify --
    # Wait for Simplify to detect and fill
    print(f"  Waiting for Simplify...")
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    await page.wait_for_timeout(8000)

    # Fill any remaining fields
    filled = await _fill_workday_fields(page)
    if filled:
        print(f"  Filled {filled} field(s) Simplify missed")

    # Remove any initial overlays
    await _remove_overlays(page)

    async def _scan_all_buttons(page) -> str | None:
        """Scan every visible button and return the text of the first one that
        looks like a forward-action button (submit, continue, next, agree, etc.)."""
        keywords = ["submit", "continue", "next", "save", "finish", "done",
                     "review", "agree", "accept", "confirm", "apply", "send"]
        try:
            all_buttons = await page.evaluate("""() => {
                const buttons = document.querySelectorAll('button, [role="button"], input[type="submit"]');
                return Array.from(buttons).map(b => ({
                    text: (b.innerText || b.value || '').trim().substring(0, 40),
                    visible: b.offsetParent !== null,
                    disabled: b.disabled || b.getAttribute('aria-disabled') === 'true'
                }));
            }""")
            for btn in all_buttons:
                if btn.get("visible") and not btn.get("disabled"):
                    text = btn.get("text", "").lower()
                    for kw in keywords:
                        if kw in text:
                            return btn["text"]
        except Exception:
            pass
        return None

    async def _handle_review_page(page) -> bool:
        """Handle review page tasks: agreement checkboxes, electronic signature fields.
        Returns True if it clicked something that should advance the page."""
        try:
            # Check for agreement/consent checkbox
            agree_cb = page.locator(
                'input[type="checkbox"]:near(:text("I agree")), '
                'input[type="checkbox"]:near(:text("I consent")), '
                'input[type="checkbox"]:near(:text("terms")), '
                'input[type="checkbox"]:near(:text("signature"))'
            ).first
            if await agree_cb.is_visible(timeout=500):
                if not await agree_cb.is_checked():
                    await agree_cb.check()
                    print(f"  ✓ Checked agreement/consent checkbox")
                    await page.wait_for_timeout(500)
                    return True

            # Check for agreement checkbox by data-automation-id
            cb2 = page.locator('[data-automation-id*="agree"], [data-automation-id*="consent"], '
                               '[data-automation-id*="acceptTerms"]').first
            if await cb2.is_visible(timeout=500):
                if not await cb2.is_checked():
                    await cb2.check()
                    print(f"  ✓ Checked agreement checkbox (data-automation-id)")
                    await page.wait_for_timeout(500)
                    return True

            # Check for electronic signature field (type full name)
            sig_input = page.locator('input[data-automation-id*="signature"], '
                                     'input[placeholder*="Full Name"], '
                                     'input[placeholder*="signature"], '
                                     'input[placeholder*="type your name"]').first
            if await sig_input.is_visible(timeout=500):
                current = await sig_input.input_value()
                if not current.strip():
                    await sig_input.fill("Kyler Cao")
                    print(f"  ✓ Filled electronic signature")
                    await page.wait_for_timeout(500)
                    return True
        except Exception:
            pass
        return False

    # Wizard loop
    last_body = ""
    stuck_count = 0
    for step_num in range(500):
        try:
            body = await page.inner_text("body")
        except Exception:
            body = ""

        # Check for submission confirmation
        if any(w in body.lower() for w in ["thank you", "submitted", "Your application", "application has been submitted"]):
            print(f"  ✅ SUBMITTED at step {step_num+1}!")
            return _success_result()

        # Stuck detection
        if body == last_body:
            stuck_count += 1
            if stuck_count > 5:
                print(f"  → Stuck at step {step_num+1} (page not changing)")
                # Dump debug info before breaking
                try:
                    buttons = await page.evaluate("""() => Array.from(
                        document.querySelectorAll('button, [role="button"], input[type="submit"]')
                    ).map(b => ({
                        text: (b.innerText || b.value || '').trim().substring(0, 50),
                        visible: b.offsetParent !== null,
                        disabled: b.disabled,
                        'data-automation-id': b.getAttribute('data-automation-id') || ''
                    })).filter(b => b.visible)""")
                    if buttons:
                        print(f"  📋 Visible buttons ({len(buttons)}):")
                        for b in buttons[:20]:
                            d = f"[{b['text']}] disabled={b['disabled']} auto-id={b.get('data-automation-id', '')}"
                            print(f"    - {d}")
                    inputs = await page.evaluate("""() => Array.from(
                        document.querySelectorAll('input:not([type="hidden"])')
                    ).map(inp => ({
                        type: inp.type,
                        placeholder: inp.placeholder || '',
                        id: inp.id || '',
                        'data-automation-id': inp.getAttribute('data-automation-id') || ''
                    })).filter(inp => inp.type !== 'submit')""")
                    if inputs:
                        print(f"  📋 Visible inputs ({len(inputs)}):")
                        for inp in inputs[:10]:
                            print(f"    - type={inp['type']} placeholder={inp['placeholder'][:30]} id={inp['id'][:20]}")
                except Exception:
                    pass
                break
        else:
            stuck_count = 0
            last_body = body

        # Remove blocking overlays
        await _remove_overlays(page)

        # Handle review page tasks (agreement, signature)
        await _handle_review_page(page)

        # Fill remaining fields — do this every iteration to catch validation errors
        filled_here = await _fill_workday_fields(page)
        if filled_here and step_num < 10:
            print(f"  Filled {filled_here} field(s) at step {step_num+1}")

        # Try submit buttons first
        clicked = await _click_visible_button(page,
            "Submit Application", "Submit", "Review and Submit", "Finish", "Done", "Review")
        if clicked:
            await page.wait_for_timeout(4000)
            continue

        # Then try advance buttons
        clicked = await _click_visible_button(page,
            "Save and Continue", "Save & Continue", "Continue", "Next", "Save")
        if clicked:
            await page.wait_for_timeout(3000)
            continue

        # Try any visible button with a forward-action keyword
        keyword_btn = await _scan_all_buttons(page)
        if keyword_btn:
            print(f"  → Clicking keyword-matched button: '{keyword_btn}'")
            if await _click_text(page, keyword_btn):
                await page.wait_for_timeout(4000)
                continue

        # Last resort: keyboard Enter
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)
        try:
            new_body = await page.inner_text("body")
            if new_body != body:
                continue
        except Exception:
            pass

        if step_num == 0:
            print(f"  → No buttons found on first step")
            # Dump debug info to understand the page state
            try:
                title = await page.title()
                print(f"  📋 Page title: {title}")
                url_cur = page.url[:100]
                print(f"  📋 URL: {url_cur}")
                buttons = await page.evaluate("""() => Array.from(
                    document.querySelectorAll('button, [role="button"], input[type="submit"]')
                ).map(b => ({
                    text: (b.innerText || b.value || '').trim().substring(0, 50),
                    visible: b.offsetParent !== null,
                    disabled: b.disabled,
                    'data-automation-id': b.getAttribute('data-automation-id') || ''
                })).filter(b => b.visible)""")
                if buttons:
                    print(f"  📋 Visible buttons ({len(buttons)}):")
                    for b in buttons[:20]:
                        print(f"    - [{b['text']}] disabled={b['disabled']} auto-id={b.get('data-automation-id', '')}")
                else:
                    print(f"  📋 No visible buttons found")
                # Check for any heading/instruction text
                try:
                    body_snippet = (await page.inner_text("body"))[:500]
                    print(f"  📋 Body: {body_snippet}")
                except Exception:
                    pass
            except Exception:
                pass
        break

    # Final submission check
    try:
        final = await page.inner_text("body")
        if any(w in final.lower() for w in ["thank you", "submitted", "Your application"]):
            print(f"  ✅ SUBMITTED!")
            return _success_result()
    except Exception:
        pass

    print(f"  → WIZARD_END")
    return _error_result("wizard_end", "Reached end of wizard — review debug output above")


async def _fill_workday_fields(page) -> int:
    """Fill common Workday fields that Simplify might miss, including multiselect."""
    field_map = {
        "name--legalName--firstName": "Kyler",
        "name--legalName--lastName": "Cao",
        "address--addressLine1": "9810 Orchid Cove Court",
        "address--city": "Cypress",
        "address--state": "Texas",
        "address--postalCode": "77433",
        "phoneNumber--phoneNumber": "18329664150",
        "emailAddress--emailAddress": "kcao@tamu.edu",
    }
    # Multiselect fields: (label text to find, value text to select)
    multiselect_fields = [
        ("How Did You Hear About Us?", "Cox Career Site"),
        ("How Did You Hear About Us", "Cox Career Site"),
    ]
    # Radio button questions: (label text containing question, value text to select)
    radio_questions = [
        ("have you ever worked", "No"),
        ("have you been employed", "No"),
        ("currently employed", "No"),
        ("have you previously", "No"),
    ]
    # Combobox/select fields: (label text, value to select)
    select_fields = [
        ("state", "Texas"),
        ("phone device", "Mobile"),
        ("country", "United States of America"),
        ("phone country", "United States (+1)"),
    ]
    filled = 0

    # Regular text/input fields
    for field_id, value in field_map.items():
        try:
            el = page.locator(f"#{field_id}")
            if await el.is_visible(timeout=200):
                current = await el.input_value()
                if current and current.strip():
                    continue
                await el.fill(value)
                filled += 1
        except Exception:
            pass

    # Combobox/select via data-automation-id pattern
    for label_kw, value in select_fields:
        try:
            # Find select/combobox elements whose aria-label or nearby label contains the keyword
            el = page.locator(
                f'select:near(:text(\"{label_kw}\", i)), '
                f'[role="combobox"]:near(:text(\"{label_kw}\", i)), '
                f'input[list]:near(:text(\"{label_kw}\", i)), '
                f'[data-automation-id*=\"{label_kw}\"]'
            ).first
            if await el.is_visible(timeout=200):
                current = await el.input_value() if hasattr(el, 'input_value') else ""
                if current and current.strip():
                    continue
                # Try native select option
                try:
                    await el.select_option(value)
                    filled += 1
                    continue
                except Exception:
                    pass
                # Try typing into combobox
                try:
                    await el.click()
                    await page.wait_for_timeout(200)
                    await el.fill(value)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(300)
                    filled += 1
                except Exception:
                    pass
        except Exception:
            pass

    # Radio button questions
    for q_kw, value in radio_questions:
        try:
            # Find the radio group by looking for labels containing the question keyword
            radio_label = page.locator(
                f'span:has-text(\"{q_kw}\", i), '
                f'label:has-text(\"{q_kw}\", i), '
                f'fieldset:has-text(\"{q_kw}\", i) legend'
            ).first
            if await radio_label.is_visible(timeout=200):
                # Find the radio input with matching label
                radio = page.locator(
                    f'label:has-text(\"{value}\") input[type=\"radio\"]:near(:text(\"{q_kw}\", i)), '
                    f'label:has-text(\"{value}\"):near(:text(\"{q_kw}\", i))'
                ).first
                if await radio.is_visible(timeout=500):
                    await radio.click()
                    filled += 1
                else:
                    # Try clicking the label text directly
                    btn = page.locator(f'label:has-text(\"{value}\"):near(:text(\"{q_kw}\", i))').first
                    if await btn.is_visible(timeout=200):
                        await btn.click()
                        filled += 1
        except Exception:
            pass

    # Multiselect/combobox fields — click to open, then select option
    for label, option_text in multiselect_fields:
        try:
            # Find the visible multiselect container by looking for the label text
            # then clicking its sibling input container
            label_el = page.locator(f'label:has-text("{label}"), span:has-text("{label}")').first
            if not await label_el.is_visible(timeout=200):
                continue

            # Find the parent field container, then the multiselect div
            field_group = label_el.locator('xpath=ancestor::div[contains(@data-automation-id, "formField")]')
            multiselect = field_group.locator('[data-automation-id="multiselectInputContainer"]')

            if await multiselect.is_visible(timeout=500):
                # Check if already has a selection (text shows "1 item selected" not "0 items selected")
                text = await multiselect.inner_text()
                if "0 items selected" not in text:
                    continue  # Already filled

                # Click to open the dropdown
                await multiselect.click()
                await page.wait_for_timeout(500)

                # Click the option with matching text
                option = page.locator(f'[role="option"]:has-text("{option_text}")').first
                if await option.is_visible(timeout=2000):
                    await option.click()
                    await page.wait_for_timeout(300)
                    filled += 1
        except Exception:
            pass

    # "Select One" dropdowns — Workday comboboxes that default to "Select One"
    select_one_map = {
        "State": "Texas",
        "Phone Device": "Mobile",
        "Device Type": "Mobile",
        "Country": "United States of America",
        "Phone Country": "United States (+1)",
    }
    try:
        for label_kw, value in select_one_map.items():
            # Find a "Select One" button near a label containing the keyword
            btn = page.locator(
                f'button:has-text("Select One"):near(:text("{label_kw}", i)), '
                f'button:has-text("-- Select --"):near(:text("{label_kw}", i))'
            ).first
            if await btn.is_visible(timeout=100):
                await btn.click()
                await page.wait_for_timeout(400)
                # Select the option — try multiple strategies
                opt = page.locator(
                    f'[role="option"]:has-text("{value}"), '
                    f'li:has-text("{value}"), '
                    f'div[role="listbox"] :text-is("{value}")'
                ).first
                if await opt.is_visible(timeout=1500):
                    await opt.click()
                    await page.wait_for_timeout(300)
                    filled += 1
                    continue
                # Fallback: type in the search field and press Enter
                search = page.locator(
                    f'input[role="combobox"]:near(:text("{label_kw}", i)), '
                    f'input[type="text"]:near(:text("{label_kw}", i))'
                ).first
                if await search.is_visible(timeout=300):
                    await search.fill(value)
                    await page.wait_for_timeout(300)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(500)
                    filled += 1
    except Exception:
        pass

    return filled


async def _handle_ashby(page, ctx, job: dict[str, Any], acct: dict[str, Any] | None = None) -> dict[str, Any]:
    """Ashby flow: upload resume, fill fields, submit."""
    url: str = job["url"]

    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    await _click_text(page, "Accept")
    await page.wait_for_timeout(2000)

    # Upload resume FIRST (Ashby re-renders after upload)
    if RESUME_PATH.exists():
        try:
            file_input = page.locator('input[type="file"]').first
            if await file_input.is_visible(timeout=2000):
                await file_input.set_input_files(str(RESUME_PATH))
                await page.wait_for_timeout(3000)
        except Exception:
            pass

    # Wait for Simplify
    await page.wait_for_timeout(5000)

    return await _click_submit_flow(page)


async def _handle_greenhouse(page, ctx, job: dict[str, Any], acct: dict[str, Any] | None = None) -> dict[str, Any]:
    """Greenhouse flow: fill fields, attach resume, submit."""
    url: str = job["url"]

    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    await _click_text(page, "Accept")

    # Upload resume
    if RESUME_PATH.exists():
        try:
            file_input = page.locator('input[type="file"]').first
            if await file_input.is_visible(timeout=2000):
                await file_input.set_input_files(str(RESUME_PATH))
                await page.wait_for_timeout(3000)
        except Exception:
            pass

    # Wait for Simplify
    await page.wait_for_timeout(5000)

    return await _click_submit_flow(page)


async def _handle_generic(page, ctx, job: dict[str, Any], acct: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generic/fallback flow: navigate, let Simplify fill, click submit."""
    url: str = job["url"]

    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    await _click_text(page, "Accept")
    await page.wait_for_timeout(2000)

    # Check for external apply link
    for text in ["Apply on company site", "Apply externally", "Apply on website"]:
        try:
            link = page.locator(f'a:has-text("{text}")').first
            if await link.is_visible(timeout=500):
                href = await link.get_attribute("href")
                if href:
                    print(f"  → External link: {href[:60]}")
                    return _skip_result(f"EXTERNAL_LINK: {href[:40]}")
        except Exception:
            pass

    # Click "Apply" first, then submit
    for apply_text in ["Apply for this job", "Apply Now", "Apply", "Easy Apply"]:
        if await _click_text(page, apply_text):
            await page.wait_for_timeout(5000)
            break

    # Wait for Simplify
    await page.wait_for_timeout(5000)

    return await _click_submit_flow(page)


async def _handle_icims(page, ctx, job: dict[str, Any], acct: dict[str, Any] | None = None) -> dict[str, Any]:
    """iCIMS flow — may need account creation."""
    return await _handle_generic(page, ctx, job)


async def _handle_smartrecruiters(page, ctx, job: dict[str, Any], acct: dict[str, Any] | None = None) -> dict[str, Any]:
    """SmartRecruiters flow."""
    return await _handle_generic(page, ctx, job)


async def _click_submit_flow(page) -> dict[str, Any]:
    """Try to click Submit or equivalent, check confirmation."""
    # Try Submit buttons
    for name in ["Submit Application", "Submit your application", "Submit", "Send Application"]:
        if await _click_text(page, name):
            await page.wait_for_timeout(4000)
            break

    # If no Submit button, try "Apply" buttons
    for name in ["Apply for this job", "Apply Now", "Apply", "Easy Apply"]:
        if await _click_text(page, name):
            await page.wait_for_timeout(4000)
            break

    # Check for confirmation
    try:
        body = await page.inner_text("body")
    except Exception:
        body = ""
    for word in ["thank you", "submitted", "Your application", "application has been submitted"]:
        if word in body.lower():
            print(f"  ✅ SUBMITTED!")
            return _success_result()

    print(f"  → Applied (submit clicked, awaiting confirmation)")
    return _success_result(method="simplify", status="applied")


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------
def _success_result(
    method: str = "auto",
    status: str = "applied",
    confirmation: str | None = None,
    resume_used: str | None = None,
) -> dict[str, Any]:
    return {
        "method": method,
        "result": "success",
        "status": status,
        "applied_date": date.today().isoformat(),
        "needs_review": False,
        "confirmation": confirmation,
        "resume_used": resume_used,
        "error": None,
    }


def _error_result(
    error_type: str,
    error_msg: str,
    method: str = "auto",
    needs_review: bool = True,
) -> dict[str, Any]:
    return {
        "method": method,
        "result": error_type,
        "status": "needs-review",
        "needs_review": needs_review,
        "applied_date": None,
        "confirmation": None,
        "resume_used": None,
        "error": error_msg,
    }


def _skip_result(reason: str) -> dict[str, Any]:
    return {
        "method": "none",
        "result": "skipped",
        "status": "to-apply",
        "needs_review": False,
        "applied_date": None,
        "confirmation": None,
        "resume_used": None,
        "error": reason,
    }


# ---------------------------------------------------------------------------
# ATS dispatch table
# ---------------------------------------------------------------------------
ATS_DISPATCH: dict[str, Any] = {
    "workday": _handle_workday,
    "ashby": _handle_ashby,
    "greenhouse": _handle_greenhouse,
    "lever": _handle_generic,
    "icims": _handle_icims,
    "smartrecruiters": _handle_smartrecruiters,
    "oracle": _handle_generic,
    "successfactors": _handle_generic,
    "generic": _handle_generic,
}


def _ats_name(site: str) -> str:
    """Human-friendly ATS name for logging."""
    names = {
        "workday": "Workday",
        "ashby": "Ashby",
        "greenhouse": "Greenhouse",
        "lever": "Lever",
        "icims": "iCIMS",
        "smartrecruiters": "SmartRecruiters",
        "oracle": "Oracle",
        "successfactors": "SuccessFactors",
    }
    return names.get(site, site.title())


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
class ApplyRunner:
    """Orchestrates the apply pipeline for a queue of jobs."""

    def __init__(self, *, dry_run: bool = False, limit: int | None = None):
        self.dry_run = dry_run
        self.limit = limit
        self.rate_tracker = RateTracker()
        self.results: list[dict[str, Any]] = []
        self.verified: list[dict[str, Any]] = []

    async def run(self) -> int:
        """Run the pipeline. Returns exit code (0 = all ok)."""
        queue = build_queue()
        if self.limit:
            queue = queue[: self.limit]

        if not queue:
            print("Queue is empty — nothing to apply to.")
            return 0

        print(f"Queue: {len(queue)} jobs")
        if self.dry_run:
            self._dry_run_report(queue)
            return 0

        # Ensure extensions are ready
        nopecha_ready = _nopecha.is_ready()
        simplify_ready = _simplify.is_ready()
        print(f"Extensions: NopeCHA={'✓' if nopecha_ready else '✗'} Simplify={'✓' if simplify_ready else '✗'}")

        # Build Playwright args with both extensions
        ext_args: list[str] = []
        if nopecha_ready and simplify_ready:
            ext_args = _simplify.playwright_args_with_nopecha()
        elif nopecha_ready:
            ext_args = _nopecha.playwright_args()
        elif simplify_ready:
            ext_args = _simplify.playwright_args()
        ext_args.extend(["--no-sandbox", "--disable-blink-features=AutomationControlled"])

        # Clean profile from previous runs
        if os.path.exists(PROFILE):
            shutil.rmtree(PROFILE)

        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE,
                headless=False,
                args=ext_args,
            )

            try:
                for idx, job in enumerate(queue):
                    # Re-create page if the previous job crashed it
                    page = None
                    try:
                        if ctx.pages:
                            page = ctx.pages[0]
                            _ = await page.title()
                        else:
                            page = await ctx.new_page()
                    except Exception:
                        print(f"  Page crashed — creating new one for job {idx+1}")
                        try:
                            page = await ctx.new_page()
                        except Exception:
                            print(f"  Browser context dead — re-launching...")
                            await ctx.close()
                            ctx = await p.chromium.launch_persistent_context(
                                user_data_dir=PROFILE,
                                headless=False,
                                args=ext_args,
                            )
                            page = ctx.pages[0] if ctx.pages else await ctx.new_page()

                    result = await self._process_one(page, job)
                    self.results.append(result)
                    write_back(job, result)
                    print()  # blank line between jobs

                # Verification pass: re-check submitted jobs
                verified = await self._verify_submissions(page, queue)
                self.verified = verified

            finally:
                await ctx.close()

        self._print_summary()
        return 0

    def _dry_run_report(self, queue: list[dict[str, Any]]) -> None:
        print(f"\n{'DRY RUN':=^60}")
        print(f"{'#':>3} | {'Company':25s} | {'ATS':15s} | {'Account':10s} | {'Rate OK':6s}")
        print("-" * 65)
        for idx, job in enumerate(queue):
            url = job.get("url", "")
            site = detect_site(url)
            has_acct = _accounts.has_account(url) if site == "workday" else False
            rate_ok = self.rate_tracker.can_attempt(site)
            print(
                f"{idx+1:>3} | {job['company']:25s} | {_ats_name(site):15s} "
                f"| {'✓' if has_acct else '✗':10s} | {'✓' if rate_ok else '✗':6s}"
            )
            self.rate_tracker.record_attempt(site)

    async def _process_one(self, page, job: dict[str, Any]) -> dict[str, Any]:
        url: str = job.get("url", "")
        company: str = job.get("company", "?")
        role: str = job.get("role", "?")

        if not url:
            print(f"\n{company} — {role}")
            print(f"  ✗ No URL, skipping")
            return _skip_result("no_url")

        site = detect_site(url)
        ats = _ats_name(site)

        print(f"\n{'=' * 60}")
        print(f"{company} — {role}")
        print(f"  ATS: {ats}")
        print(f"  {url[:90]}")

        # Rate limit check
        if not self.rate_tracker.can_attempt(site):
            print(f"  ✗ Rate limit reached for {ats}")
            return _skip_result(f"rate_limit_{site}")

        self.rate_tracker.record_attempt(site)

        # Account check for Workday
        acct = None
        if site == "workday":
            domain = _accounts.tenant_domain(url)
            if domain:
                acct = _accounts.get_account(domain)
            if acct:
                print(f"  Account: {acct['email']} ✓")

        # Dispatch to handler
        handler = ATS_DISPATCH.get(site, _handle_generic)
        try:
            raw_result = await handler(page, None, job, acct)
        except Exception as exc:
            print(f"  ✗ Error: {exc}")
            raw_result = _error_result("exception", str(exc))

        # Augment with job info
        result = {**raw_result, "company": company, "role": role}
        if raw_result["result"] == "success" and not result.get("resume_used"):
            result["resume_used"] = "resume.pdf"

        # Log result
        status_icon = "✅" if result["result"] == "success" else "❌" if result["result"] != "skipped" else "⏭️"
        status_str = result["result"]
        error_str = f" — {result['error'][:60]}" if result.get("error") else ""
        print(f"  {status_icon} {status_str}{error_str}")

        return result

    async def _verify_submissions(
        self, page, queue: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Re-check submitted jobs to confirm they actually went through.

        Navigates back to each 'success' result's URL and looks for
        confirmation text. Reverts vault status if not confirmed.
        Updates the result list with 'confirmed' flags.
        """
        from datetime import datetime

        success_results = [
            (i, r) for i, r in enumerate(self.results)
            if r.get("result") == "success" and r.get("url")
        ]

        if not success_results:
            return []

        print(f"\n{'=' * 60}")
        print(f"VERIFICATION PASS — {len(success_results)} jobs to re-check")
        verified: list[dict[str, Any]] = []

        for idx, (orig_idx, result) in enumerate(success_results):
            company = result.get("company", "?")
            url = result.get("url", "")
            print(f"\n  [{idx + 1}/{len(success_results)}] {company}")
            print(f"    {url[:80]}")

            try:
                await page.goto(url, timeout=20000, wait_until="domcontentloaded")
                await page.wait_for_timeout(5000)

                body = await page.inner_text("body")
                body_lower = body.lower()

                # Check for confirmation signals
                confirmed = any(w in body_lower for w in [
                    "thank you", "submitted", "application has been submitted",
                    "your application", "application received", "we've received",
                    "successfully submitted", "application complete",
                ])

                if not confirmed:
                    try:
                        btn = page.get_by_role("button", name="Applied", exact=False)
                        if await btn.count() > 0:
                            confirmed = True
                    except: pass

                entry = {
                    "company": company,
                    "url": url,
                    "original_result": result.get("status", "applied"),
                    "confirmed": confirmed,
                }
                verified.append(entry)

                if confirmed:
                    print(f"    ✅ CONFIRMED — application went through")
                else:
                    print(f"    ❌ NOT CONFIRMED — reverting vault status")
                    # Revert the vault note: set status back to 'to-apply'
                    result["status"] = "to-apply"
                    result["result"] = "not_confirmed"
                    result["applied_date"] = None
                    # Find matching job in queue and write back
                    for job in queue:
                        if job.get("url") == url or (
                            job.get("company", "").lower() == company.lower()
                        ):
                            from .vault import read_note, set_fm_field, write_note
                            path_obj = Path(job["path"])
                            _, fm_text, body_text = read_note(path_obj)
                            fm_text = set_fm_field(fm_text, "status", "to-apply")
                            fm_text = set_fm_field(fm_text, "applied_date", None)
                            fm_text = set_fm_field(fm_text, "apply_result", "not_confirmed")
                            write_note(path_obj, fm_text, body_text)
                            print(f"      Reverted {job.get('company', '?')} in vault")
                            break

            except Exception as exc:
                print(f"    ⚠ Error checking: {exc}")
                verified.append({
                    "company": company,
                    "url": url,
                    "original_result": result.get("status", "applied"),
                    "confirmed": False,
                    "error": str(exc)[:100],
                })

        # Update results in-place
        self.results = [
            {**r, "confirmed": next(
                (v["confirmed"] for v in verified if v["company"] == r.get("company") and v["url"] == r.get("url")),
                False
            )} if r.get("result") == "success" else r
            for r in self.results
        ]

        confirmed_count = sum(1 for v in verified if v["confirmed"])
        print(f"\n  Verification: {confirmed_count}/{len(verified)} confirmed")
        return verified

    def _print_summary(self) -> None:
        print(f"\n{'=' * 60}")
        print("RESULTS:")
        successes = sum(1 for r in self.results if r["result"] == "success")
        errors = sum(1 for r in self.results if r["result"] in ("exception", "wizard_end", "step1_blocked", "password_wrong"))
        skips = sum(1 for r in self.results if r["result"] == "skipped")
        print(f"  ✅ Success: {successes}")
        print(f"  ❌ Errors:  {errors}")
        print(f"  ⏭️  Skips:   {skips}")
        if self.verified:
            confirmed = sum(1 for v in self.verified if v["confirmed"])
            print(f"  🔍 Verified: {confirmed}/{len(self.verified)} confirmed")
        print(f"  Rate summary: {self.rate_tracker.summary}")
        for r in self.results:
            name = f"{r.get('company', '?')} — {r.get('role', '?')}"
            icon = "✅" if r["result"] == "success" else "❌" if r["result"] != "skipped" else "⏭️"
            err = f" — {r['error'][:60]}" if r.get("error") else ""
            confirmed_tag = " [VERIFIED]" if r.get("confirmed") else " [NOT CONFIRMED]" if r.get("confirmed") is False and r.get("result") == "success" else ""
            print(f"  {icon} {name}: {r['result']}{err}{confirmed_tag}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def apply_queue(
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> int:
    """Run the apply pipeline (synchronous entry point called from cli.py)."""
    runner = ApplyRunner(dry_run=dry_run, limit=limit)
    return asyncio.run(runner.run())

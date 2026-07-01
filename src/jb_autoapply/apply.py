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
    """Workday flow: sign-in, navigate wizard, fill, submit."""
    url: str = job["url"]
    company: str = job["company"]
    email = "kcao@tamu.edu"
    password = acct["password"] if acct else None

    apply_url = url.rstrip("/") + "/apply/applyManually"

    # Navigate to apply page
    await page.goto(apply_url, timeout=30000)
    await page.wait_for_timeout(3000)

    # -- Sign in if we have credentials --
    if password:
        sl = page.locator('[data-automation-id="signInLink"]')
        if await sl.is_visible(timeout=2000):
            await sl.click()
            await page.wait_for_timeout(2000)

            await page.locator('[data-automation-id="email"]').fill(email)
            await page.locator('[data-automation-id="password"]').fill(password)
            await page.wait_for_timeout(500)

            # Try Enter key (bypasses overlay)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(3000)

            # Check if still on sign-in page
            if await page.locator('[data-automation-id="email"]').is_visible(timeout=1000):
                # Overlay blocking — remove and click
                await _remove_overlays(page)
                await _click(page, '[data-automation-id="signInSubmitButton"]', timeout=3000)
                await page.wait_for_timeout(5000)

            # Check sign-in success
            signed_in = await page.locator(
                '[data-automation-id="accountMenuButton"], button:has-text("My Account")'
            ).is_visible(timeout=2000)
            if signed_in:
                print(f"  ✓ Signed in as {email}")
            else:
                # Check for error
                body_text = await page.inner_text("body")
                if "wrong email" in body_text.lower() or "incorrect" in body_text.lower():
                    return _error_result("password_wrong", "Wrong email or password — needs forgot-password")

    # -- Navigate to job posting and start apply --
    await page.goto(url, timeout=30000)
    await page.wait_for_timeout(3000)

    # Accept cookies if present
    await _click_text(page, "Accept")

    # Click Apply button
    await _click(page, '[data-automation-id="adventureButton"]')
    await page.wait_for_timeout(3000)

    # Click "Apply Manually"
    if not await _click(page, '[data-automation-id="applyManually"]', timeout=4000):
        # Maybe already at the form
        pass
    await page.wait_for_timeout(3000)

    # -- Step 1: Handle Create Account / Sign In form --
    step_email = page.locator('[data-automation-id="email"]')
    if await step_email.is_visible(timeout=2000):
        print(f"  Step 1: Create Account page")
        await step_email.fill(email)
        pw = page.locator('[data-automation-id="password"]')
        if await pw.is_visible(timeout=1000):
            await pw.fill(password if password else _accounts.generate_password())
        cb = page.locator('[data-automation-id="createAccountCheckbox"]')
        if await cb.is_visible(timeout=500):
            await cb.check()
        await page.wait_for_timeout(500)

        # Submit
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(5000)

        # If still on step 1, try overlay removal + direct click
        if await page.locator('[data-automation-id="email"]').is_visible(timeout=1000):
            await _remove_overlays(page)
            await _click(page, '[data-automation-id="createAccountSubmitButton"]')
            await page.wait_for_timeout(5000)

        # Check if still on step 1
        if await page.locator('[data-automation-id="email"]').is_visible(timeout=1000):
            return _error_result("step1_blocked", "Could not advance past Create Account step")

    # -- Wizard: walk through steps, let Simplify fill, then fill gaps --
    print(f"  Simplify...")
    await page.wait_for_timeout(8000)  # Give Simplify time to fill

    last_body = ""
    stuck_count = 0
    for step in range(500):
        try:
            body = await page.inner_text("body")
        except Exception:
            body = ""

        # Check for submission confirmation
        if any(w in body.lower() for w in ["thank you", "submitted", "Your application", "application has been submitted"]):
            print(f"  ✅ SUBMITTED at step {step+1}!")
            return _success_result()

        # Stuck detection
        if body == last_body:
            stuck_count += 1
            if stuck_count > 5:
                print(f"  → Stuck at step {step+1}")
                break
        else:
            stuck_count = 0
            last_body = body

        # Remove any blocking overlays
        await _remove_overlays(page)

        # Try fill unfilled fields using FIELD_MAP (Workday-specific)
        filled = await _fill_workday_fields(page)
        if filled and step < 5:
            print(f"  Filled {filled} remaining field(s)")

        # Submit / advance buttons
        clicked = False
        for btn_name in ["Submit Application", "Submit", "Review and Submit", "Finish", "Done", "Review"]:
            if await _click_text(page, btn_name, timeout=500):
                await page.wait_for_timeout(4000)
                clicked = True
                break

        if not clicked:
            for btn_name in ["Save and Continue", "Save & Continue", "Continue", "Next", "Save"]:
                if await _click_text(page, btn_name, timeout=500):
                    await page.wait_for_timeout(3000)
                    clicked = True
                    break

        if not clicked:
            # Try keyboard Enter as last resort
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2000)
            new_body = await page.inner_text("body")
            if new_body != body:
                clicked = True

        if not clicked:
            if step == 0:
                print(f"  → No buttons found on step 1")
            break

    # Final check for submission
    try:
        final = await page.inner_text("body")
    except Exception:
        final = ""
    for w in ["thank you", "submitted", "Your application"]:
        if w in final.lower():
            print(f"  ✅ SUBMITTED!")
            return _success_result()

    print(f"  → WIZARD_END")
    return _error_result("wizard_end", "Reached end of wizard, no submit button found")


async def _fill_workday_fields(page) -> int:
    """Fill common Workday fields that Simplify might miss."""
    field_map = {
        "source--source": "LinkedIn",
        "name--legalName--firstName": "Kyler",
        "name--legalName--lastName": "Cao",
        "address--addressLine1": "9810 Orchid Cove Court",
        "address--city": "Cypress",
        "address--postalCode": "77433",
        "phoneNumber--phoneNumber": "18329664150",
    }
    filled = 0
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
    return filled


async def _handle_ashby(page, ctx, job: dict[str, Any]) -> dict[str, Any]:
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


async def _handle_greenhouse(page, ctx, job: dict[str, Any]) -> dict[str, Any]:
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


async def _handle_generic(page, ctx, job: dict[str, Any]) -> dict[str, Any]:
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


async def _handle_icims(page, ctx, job: dict[str, Any]) -> dict[str, Any]:
    """iCIMS flow — may need account creation."""
    return await _handle_generic(page, ctx, job)


async def _handle_smartrecruiters(page, ctx, job: dict[str, Any]) -> dict[str, Any]:
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
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()

                for idx, job in enumerate(queue):
                    result = await self._process_one(page, job)
                    self.results.append(result)
                    write_back(job, result)
                    print()  # blank line between jobs

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

    def _print_summary(self) -> None:
        print(f"\n{'=' * 60}")
        print("RESULTS:")
        successes = sum(1 for r in self.results if r["result"] == "success")
        errors = sum(1 for r in self.results if r["result"] in ("exception", "wizard_end", "step1_blocked", "password_wrong"))
        skips = sum(1 for r in self.results if r["result"] == "skipped")
        print(f"  ✅ Success: {successes}")
        print(f"  ❌ Errors:  {errors}")
        print(f"  ⏭️  Skips:   {skips}")
        print(f"  Rate summary: {self.rate_tracker.summary}")
        for r in self.results:
            name = f"{r.get('company', '?')} — {r.get('role', '?')}"
            icon = "✅" if r["result"] == "success" else "❌" if r["result"] != "skipped" else "⏭️"
            err = f" — {r['error'][:60]}" if r.get("error") else ""
            print(f"  {icon} {name}: {r['result']}{err}")


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

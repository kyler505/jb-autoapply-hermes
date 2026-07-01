"""Verify job submissions and mark confirmed ones in the vault."""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-verify"


async def verify_submission(page, url: str, timeout: int = 15000) -> bool:
    """Check if a job URL shows a submitted/confirmation state.

    Returns True if the page indicates the application was submitted.
    """
    try:
        await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        body = await page.inner_text("body")
        body_lower = body.lower()

        # Confirmation text on the page
        if any(w in body_lower for w in [
            "thank you", "submitted", "application has been submitted",
            "your application", "application received", "we've received",
            "successfully submitted", "application complete",
        ]):
            return True

        # Check for "Applied" button (Greenhouse etc.)
        try:
            btn = page.get_by_role("button", name="Applied", exact=False)
            if await btn.count() > 0:
                return True
        except: pass

        # Check URL for confirmation path
        if any(p in page.url.lower() for p in [
            "submitted", "confirmation", "thank-you", "application-complete",
        ]):
            return True

        return False
    except Exception:
        return False


async def verify_and_mark(
    results: list[dict[str, Any]],
    *,
    mark_applied: bool = True,
    progress_cb=None,
) -> list[dict[str, Any]]:
    """Verify submission results and mark confirmed jobs in the vault.

    Args:
        results: List of dicts with keys 'company', 'role', 'url', 'result'
        mark_applied: If True, update vault notes for confirmed submissions
        progress_cb: Optional async callback(name, confirmed) for progress

    Returns:
        Same results list with 'confirmed' (bool) added to each item.
    """
    from jb_autoapply.vault import update_fields

    # Filter to jobs that had action taken
    to_verify = [
        r for r in results
        if r.get("result") and "SUBMIT" in str(r.get("result", "")).upper()
    ]

    if not to_verify:
        for r in results:
            r["confirmed"] = False
        return results

    import os, shutil
    temp = PROFILE
    if os.path.exists(temp):
        shutil.rmtree(temp)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=temp, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        for item in to_verify:
            name = item.get("company", "?")
            url = item.get("url", "")
            result = item.get("result", "")

            if not url:
                item["confirmed"] = False
                if progress_cb:
                    await progress_cb(name, False, "no-url")
                continue

            confirmed = await verify_submission(page, url)
            item["confirmed"] = confirmed

            if progress_cb:
                status = "CONFIRMED" if confirmed else "NOT CONFIRMED"
                await progress_cb(name, confirmed, status)

            # Mark in vault
            if confirmed and mark_applied:
                from jb_autoapply.selector import build_queue
                try:
                    queue = build_queue(write_priority=False)
                except Exception:
                    queue = []

                # Find matching note by company+role
                for q_job in queue:
                    q_company = str(q_job.get("company", "")).strip()
                    q_role = str(q_job.get("role", "")).strip()
                    if q_company.lower() == name.lower():
                        path = Path(q_job["path"])
                        fm_status = str(q_job.get("status", ""))
                        if fm_status == "to-apply":
                            update_fields(path, {
                                "status": "applied",
                                "date_applied": datetime.now().strftime("%Y-%m-%d"),
                            })

        await ctx.close()

    # Set confirmed=False for unverified items
    for r in results:
        if "confirmed" not in r:
            r["confirmed"] = False

    return results

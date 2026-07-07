#!/usr/bin/env python3
"""Mass reverification: re-check all jobs marked 'applied' on a given date.

Usage:
  python scripts/reverify.py               # reverify today's applied jobs
  python scripts/reverify.py 2026-07-06    # reverify specific date
  python scripts/reverify.py --all         # reverify ALL applied jobs
"""
from __future__ import annotations

import asyncio, os, shutil, sys
from datetime import datetime
from glob import glob
from pathlib import Path

CACHE = "/tmp/reverify_results.json"

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-reverify"


def list_applied_jobs(date_filter: str | None = None, include_pending: bool = False) -> list[dict]:
    """
    Scan the vault and return all jobs marked `status: applied`.
    If include_pending is True, also include `status: pending`.
    If date_filter is given, only return jobs with `applied_date` matching.
    """
    vdir = Path.home() / "Obsidian" / "jb" / "Jobs"
    results = []
    for fpath in sorted(glob(str(vdir / "*.md"))):
        with open(fpath) as fh:
            lines = fh.readlines()
            if not lines or lines[0].strip() != "---":
                continue
            fm: dict[str, str] = {}
            for line in lines[1:]:
                if line.strip() == "---":
                    break
                if ":" in line:
                    k, v = line.split(":", 1)
                    fm[k.strip()] = v.strip()

            status = fm.get("status", "").strip()
            if include_pending:
                if status not in ("applied", "pending"):
                    continue
            else:
                if status != "applied":
                    continue

            applied_date = fm.get("applied_date", "").strip()
            if date_filter and applied_date != date_filter:
                continue

            results.append({
                "path": fpath,
                "company": fm.get("company", "").strip(),
                "role": fm.get("role", "").strip(),
                "url": fm.get("url", "").strip(),
                "applied_date": applied_date,
                "status": status,
            })
    return results


def find_url_in_body(lines: list[str]) -> str:
    """Extract the application URL from the note body."""
    body_start = False
    for line in lines:
        if not body_start:
            if line.strip() == "---":
                body_start = True
                continue
            # Skip frontmatter
            if line.strip() == "---":
                body_start = True
            continue
        # After frontmatter, look for URL
        stripped = line.strip()
        if stripped.startswith("https://") and ("application" in stripped.lower()
                                                or "apply" in stripped.lower()
                                                or "job" in stripped.lower()):
            return stripped
        # Check for link format: [text](url)
        if "](" in stripped and "https://" in stripped:
            url = stripped.split("](")[-1].rstrip(")")
            if "application" in url.lower() or "apply" in url.lower() or "job" in url.lower():
                return url
    return ""


async def verify_submission(page, url: str) -> bool:
    """Visit the URL and check for confirmation indicators."""
    if not url:
        return False
    try:
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")
        await page.wait_for_timeout(6000)
        body_lower = (await page.inner_text("body")).lower()

        # Confirmation text
        if any(w in body_lower for w in [
            "thank you", "submitted", "application has been submitted",
            "your application", "application received", "we've received",
            "successfully submitted", "application complete",
        ]):
            return True

        # "Applied" button (Greenhouse post-submit state)
        try:
            btn = page.get_by_role("button", name="Applied", exact=False)
            if await btn.count() > 0:
                return True
        except Exception:
            pass

        # URL contains confirmation path
        if any(p in page.url.lower() for p in [
            "submitted", "confirmation", "thank-you", "application-complete",
        ]):
            return True

        # Check for "Application submitted" heading
        try:
            h = page.locator('h1, h2, h3').filter(has_text="applied|submitted|thank you")
            if await h.count() > 0:
                return True
        except Exception:
            pass

        return False
    except Exception:
        return False


def revert_vault(path: str) -> None:
    """Change a vault note from 'applied' (or 'pending') back to 'to-apply'."""
    with open(path) as fh:
        content = fh.read()

    # Replace in frontmatter
    lines = content.split("\n")
    in_fm = False
    modified = False
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                break
        if in_fm and line.startswith("status:") and ("applied" in line or "pending" in line):
            lines[i] = line.replace(line.split(":")[1].strip(), "to-apply", 1)
            modified = True
        if in_fm and line.startswith("applied_date:"):
            lines[i] = "applied_date: null"
            modified = True
        if in_fm and line.startswith("confirmation:"):
            lines[i] = "confirmation: null"
            modified = True

    if modified:
        with open(path, "w") as fh:
            fh.write("\n".join(lines))


def confirm_vault(path: str) -> None:
    """Upgrade a vault note from 'pending' to 'applied'."""
    with open(path) as fh:
        content = fh.read()

    lines = content.split("\n")
    in_fm = False
    modified = False
    for i, line in enumerate(lines):
        if line.strip() == "---":
            if not in_fm:
                in_fm = True
                continue
            else:
                break
        if in_fm and line.startswith("status:") and "pending" in line:
            lines[i] = line.replace("pending", "applied", 1)
            modified = True

    if modified:
        with open(path, "w") as fh:
            fh.write("\n".join(lines))


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Mass reverify job applications")
    parser.add_argument("date", nargs="?", default=None, help="Date filter (default: today)")
    parser.add_argument("--all", action="store_true", help="Reverify ALL applied jobs")
    parser.add_argument("--pending", action="store_true", help="Also reverify pending jobs (submit clicked, no in-session conf)")
    args = parser.parse_args()

    if args.all:
        date_filter = None
    elif args.date:
        date_filter = args.date
    else:
        date_filter = datetime.now().strftime("%Y-%m-%d")

    jobs = list_applied_jobs(date_filter, include_pending=args.pending)
    if not jobs:
        print(f"No applied jobs found{' for ' + date_filter if date_filter else ''}")
        return 0

    print(f"Found {len(jobs)} jobs to reverify"
          f"{' (' + date_filter + ')' if date_filter else ' (all)'}")
    print()

    # Clean profile
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    from playwright.async_api import async_playwright

    confirmed_count = 0
    reverted_count = 0
    error_count = 0

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            headless=False,
            args=[
                f"--load-extension={SDIR},{NDIR}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        try:
            for i, job in enumerate(jobs):
                company = job["company"]
                role = job["role"]
                url = job["url"]
                print(f"[{i+1}/{len(jobs)}] {company} — {role}", end=" ", flush=True)

                if not url:
                    print("⚠ No URL — can't verify")
                    error_count += 1
                    continue

                try:
                    confirmed = await verify_submission(page, url)
                except Exception as exc:
                    print(f"⚠ Error: {exc}")
                    error_count += 1
                    continue

                if confirmed:
                    print("✅ CONFIRMED")
                    confirmed_count += 1
                    if job["status"] == "pending":
                        confirm_vault(job["path"])
                else:
                    print(f"❌ NOT CONFIRMED → reverting")
                    revert_vault(job["path"])
                    reverted_count += 1

                # Small delay between checks
                await page.wait_for_timeout(1000)

        finally:
            await ctx.close()

    print()
    print("=" * 60)
    print(f"Total: {len(jobs)}")
    print(f"  ✅ Confirmed: {confirmed_count}")
    print(f"  ❌ Reverted: {reverted_count}")
    print(f"  ⚠ Errors: {error_count}")

    # Save results
    import json
    with open(CACHE, "w") as fh:
        json.dump({
            "date": date_filter or "all",
            "total": len(jobs),
            "confirmed": confirmed_count,
            "reverted": reverted_count,
            "errors": error_count,
        }, fh)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
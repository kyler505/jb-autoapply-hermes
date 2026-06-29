#!/usr/bin/env python3
"""Batch apply to all queue jobs using Simplify Copilot."""
import asyncio, os, shutil, sys
from pathlib import Path

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-batch"

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accounts
from jb_autoapply.selector import build_queue
from playwright.async_api import async_playwright


async def click_submit(page):
    """Try to click Submit or equivalent button."""
    for name in ["Submit Application", "Submit", "Submit your application", "Send Application", "Apply"]:
        try:
            btn = page.get_by_role("button", name=name)
            if await btn.count() > 0:
                await btn.first.click()
                return True, name
        except: pass
        try:
            btn = page.locator(f'button:has-text("{name}")')
            if await btn.is_visible(timeout=500):
                await btn.click()
                return True, name
        except: pass
    return False, None


async def apply_to_job(page, job):
    """Try to apply to a single job with Simplify."""
    url = job["url"]
    company = job["company"]
    role = job.get("role", "")
    
    print(f"\n{'='*60}")
    print(f"{company} — {role}")
    print(f"  {url[:80]}")
    
    # Navigate and wait for Simplify
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(5000)  # Initial load
    
    # Check for cookie banners and accept
    for text in ["Accept Cookies", "Accept All", "Accept", "Allow All", "I Accept"]:
        try:
            btn = page.get_by_role("button", name=text)
            if await btn.count() > 0:
                await btn.first.click()
                await page.wait_for_timeout(1000)
                break
        except: pass
    
    # Wait for Simplify to detect and fill
    await page.wait_for_timeout(8000)
    
    # Check what's on the page
    body = await page.inner_text("body")
    
    # Look for Apply/Submit buttons
    clicked, name = await click_submit(page)
    if clicked:
        print(f"  → Clicked '{name}', waiting...")
        await page.wait_for_timeout(5000)
        body2 = await page.inner_text("body")
        for w in ["thank you", "submitted", "Your application", "application has been submitted"]:
            if w in body2.lower():
                print(f"  ✅ SUBMITTED!")
                return "SUBMITTED"
        print(f"  After click: {page.url[:60]}")
        return f"CLICKED_{name}"
    
    # Check if we need to click "Apply" first
    for text in ["Apply for this job", "Apply Now", "Apply", "Easy Apply"]:
        try:
            btn = page.get_by_role("link", name=text)
            if await btn.count() == 0:
                btn = page.get_by_role("button", name=text)
            if await btn.count() > 0:
                print(f"  → '{text}' button, clicking...")
                await btn.first.click()
                await page.wait_for_timeout(5000)
                clicked2, name2 = await click_submit(page)
                if clicked2:
                    print(f"  → Clicked '{name2}'")
                    await page.wait_for_timeout(5000)
                    body3 = await page.inner_text("body")
                    for w in ["thank you", "submitted", "Your application"]:
                        if w in body3.lower():
                            print(f"  ✅ SUBMITTED!")
                            return "SUBMITTED"
                return f"CLICKED_{text}"
        except: pass
    
    # Check for external apply link
    for text in ["Apply on company site", "Apply externally", "Apply on website"]:
        try:
            btn = page.get_by_role("link", name=text)
            if await btn.count() == 0:
                btn = page.get_by_role("button", name=text)
            if await btn.count() > 0:
                href = await btn.first.get_attribute("href")
                if href:
                    print(f"  → External link: {href[:60]}")
                    return f"EXTERNAL:{href[:40]}"
        except: pass
    
    print(f"  → No apply action found")
    return "NO_ACTION"


async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    
    queue = build_queue()
    print(f"Queue: {len(queue)} jobs")
    
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        results = []
        for job in queue:
            company = job["company"]
            url = job.get("url", "")
            
            # Skip Workday jobs (handled by run_queue.py)
            if "workday" in url.lower():
                print(f"\n  Skipping {company} (Workday - use run_queue.py)")
                results.append((company, "WORKDAY"))
                continue
            
            result = await apply_to_job(page, job)
            results.append((company, result))
        
        print(f"\n{'='*60}")
        print("RESULTS:")
        successes = 0
        for c, r in results:
            status = "✅" if "SUBMIT" in str(r) or "CLICKED" in str(r) else "❌"
            print(f"  {status} {c:25s}: {r}")
            if "SUBMIT" in str(r): successes += 1
        print(f"\nSubmitted: {successes}/{len(results)}")
        
        await ctx.close()


asyncio.run(main())

#!/usr/bin/env python3
"""Run the queue with Simplify + NopeCHA + account store."""
import asyncio, os, shutil, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-run"
RESUME = "/home/kyler/.hermes/.playwright-mcp/uploads/resume_har.pdf"

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accounts
from jb_autoapply.selector import build_queue


async def apply_workday(page, job, acct):
    """Apply to a Workday job using stored credentials."""
    url = job["url"]
    domain = _accounts.tenant_domain(url)
    company = job["company"]
    role = job["role"]
    
    print(f"\n{'='*60}")
    print(f"Applying: {company} — {role}")
    print(f"  URL: {url}")
    print(f"  Account: {acct['email']} ({domain})")
    
    async def wd_click(text):
        """Click Workday button using Playwright's native .click()."""
        aid_map = {"Create Account": "createAccountSubmitButton", "Sign In": "createAccountSubmitButton"}
        aid = aid_map.get(text)
        if aid:
            btn = page.locator(f'[data-automation-id="{aid}"]')
            if await btn.is_visible(timeout=2000):
                await btn.click(); return True
        try:
            btn = page.get_by_role("button", name=text)
            if await btn.count() > 0:
                await btn.first.click(); return True
        except: pass
        try:
            btn = page.locator(f'button:has-text("{text}")')
            if await btn.is_visible(timeout=2000):
                await btn.click(); return True
        except: pass
        return False
    
    # Navigate to apply page
    apply_url = url.rstrip("/") + "/apply/applyManually"
    await page.goto(apply_url, timeout=30000)
    await page.wait_for_timeout(3000)
    body = await page.inner_text("body")
    
    if "Sign In" in body and "Email" in body and "Password" in body and "Create Account" not in body.split("Sign In")[0]:
        print("  → Signing in (stored credentials)...")
        await page.locator('#input-4').fill(acct["email"])
        await page.locator('#input-5').fill(acct["password"])
        await page.wait_for_timeout(500)
        if await wd_click("Sign In"):
            await page.wait_for_timeout(5000)
            body = await page.inner_text("body")
            if "My Information" in body or "my information" in body.lower():
                print("  ✅ SIGNED IN!")
            elif "wrong" in body.lower():
                print("  ⚠ Wrong password")
                return "WRONG_PASSWORD"
        else:
            return "CLICK_FAILED"
    elif "Create Account" in body:
        print("  → Creating account...")
        pwd = _accounts.generate_password()
        await page.locator('#input-4').fill(acct["email"])
        await page.locator('#input-5').fill(pwd)
        await page.locator('#input-6').fill(pwd)
        await page.locator('#input-9').check()
        await page.wait_for_timeout(500)
        if await wd_click("Create Account"):
            await page.wait_for_timeout(5000)
            body = await page.inner_text("body")
            if "My Information" in body or "my information" in body.lower():
                if domain: _accounts.save_account(domain, acct["email"], pwd)
                print("  ✅ ACCOUNT CREATED!")
            else:
                print(f"  After create: {body[:200]}")
                return "CREATE_FAILED"
    
    # Wait for Simplify autofill
    print("  → Waiting for Simplify...")
    await page.wait_for_timeout(8000)
    
    body = await page.inner_text("body")
    if "Submit" in body or "Review" in body:
        print("  → Submit/Review found")
        return "READY_FOR_SUBMIT"
    return "NO_SUBMIT"
    
    return "SIGNED_IN"


async def main():
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    # Load queue
    queue = build_queue()
    print(f"Queue has {len(queue)} jobs")
    
    # Filter to Workday jobs with stored accounts
    targets = []
    for job in queue:
        url = job.get("url", "")
        if _accounts.tenant_domain(url) and _accounts.has_account(url):
            domain = _accounts.tenant_domain(url)
            if not domain:
                continue
            acct = _accounts.get_account(domain)
            targets.append((job, acct))
    
    print(f"Jobs with stored accounts: {len(targets)}")
    for job, acct in targets:
        print(f"  • {job['company']:25s} — {acct['email']} ({_accounts.tenant_domain(job['url'])})")
    
    if not targets:
        print("No jobs with stored accounts. Nothing to apply to.")
        return
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
            slow_mo=200,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Login to Simplify
        print("\n1. Syncing Simplify profile...")
        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except: pass
        await page.wait_for_timeout(500)
        await page.locator('#email, input[placeholder="Email Address"]').first.fill("kylercao18@gmail.com")
        await page.locator('#password, input[placeholder="Password"]').first.fill("Monkeytype1511")
        await page.wait_for_timeout(500)
        await page.locator('button[type="submit"]').first.click()
        await page.wait_for_timeout(5000)
        print(f"   Simplify logged in: {'dashboard' in page.url}")
        
        # Apply to each target
        results = []
        for job, acct in targets:
            result = await apply_workday(page, job, acct)
            results.append((job["company"], result))
            print(f"  Result: {result}")
        
        # Summary
        print(f"\n{'='*60}")
        print("RESULTS:")
        for company, result in results:
            print(f"  {company:25s}: {result}")
        
        await context.close()


asyncio.run(main())

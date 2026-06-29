#!/usr/bin/env python3
"""Run the Workday queue: sign in or create account, advance wizard, submit."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-run"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accounts
from jb_autoapply.selector import build_queue


async def _has_button(page, text):
    try:
        if await page.locator(f'[aria-label="{text}"][data-automation-id="click_filter"]').is_visible(timeout=500): return True
    except: pass
    try:
        if await page.get_by_role("button", name=text).count() > 0: return True
    except: pass
    return False


async def wd_click(page, text):
    """Click a Workday button. Strategy: click_filter overlay > automation-id > role > text."""
    # Try click_filter overlay first
    try:
        ov = page.locator(f'[data-automation-id="click_filter"][aria-label="{text}"]')
        if await ov.count() > 0:
            await ov.first.click()
            return True
    except: pass
    # Try get_by_role (finds overlay by its aria-label)
    try:
        btn = page.get_by_role("button", name=text)
        if await btn.count() > 0:
            await btn.first.click()
            return True
    except: pass
    # Try automation-id mapping
    aids = {"Create Account": "createAccountSubmitButton", "Sign In": "signInSubmitButton"}
    if text in aids:
        try:
            btn = page.locator(f'[data-automation-id="{aids[text]}"]')
            if await btn.is_visible(timeout=1000):
                await btn.click(force=True)
                return True
        except: pass
    return False


async def apply_workday(page, job, acct):
    url = job["url"]
    domain = _accounts.tenant_domain(url)
    company = job["company"]
    role = job["role"]

    print(f"\n{'='*60}")
    print(f"Applying: {company} — {role}")
    print(f"  URL: {url}")
    print(f"  Account: {acct['email']} ({domain})")

    apply_url = url.rstrip("/") + "/apply/applyManually"
    await page.goto(apply_url, timeout=30000)
    await page.wait_for_timeout(3000)
    # Check if we're on the form or still need to sign in
    initial_body = await page.inner_text("body")
    
    # If the page has "Apply Manually" (job listing), we need to start the application
    if "Apply Manually" in initial_body and "First Name" not in initial_body:
        am = page.locator('[data-automation-id="applyManually"]')
        if await am.is_visible(timeout=2000):
            print("  → Clicking Apply Manually...")
            await am.click()
            await page.wait_for_timeout(5000)
            initial_body = await page.inner_text("body")
    
    # If we see the Create Account form with sign-in options
    if "Create Account" in initial_body and "Email" in initial_body:
        if _accounts.has_account(url):
            print("  → Trying stored credentials...")
            await page.locator('[data-automation-id="signInLink"]').click()
            await page.wait_for_timeout(3000)
            await page.locator('[data-automation-id="email"]').fill(acct["email"])
            await page.locator('[data-automation-id="password"]').fill(acct["password"])
            await page.wait_for_timeout(500)
            await wd_click(page, "Sign In")
            await page.wait_for_timeout(5000)
            
            # After sign-in, navigate back to the job page and click Apply Manually
            # (navigating directly to /apply/applyManually doesn't work when signed in)
            job_url = url.rstrip("/")
            await page.goto(job_url, timeout=30000)
            await page.wait_for_timeout(3000)
            
            # Click Apply button
            apply_btn = page.locator('[data-automation-id="adventureButton"]')
            if await apply_btn.is_visible(timeout=3000):
                await apply_btn.click()
                await page.wait_for_timeout(3000)
            
            # Click Apply Manually
            am = page.locator('[data-automation-id="applyManually"]')
            if await am.is_visible(timeout=3000):
                await am.click()
                await page.wait_for_timeout(5000)
            
            body2 = await page.inner_text("body")
            
            if "First Name" in body2 or "Save and Continue" in body2:
                print("  ✅ SIGNED IN AND ON FORM!")
            elif "Start Your Application" in body2 or "Apply Manually" in body2:
                # Click Apply Manually
                am = page.locator('[data-automation-id="applyManually"]')
                if await am.is_visible(timeout=2000):
                    await am.click()
                    await page.wait_for_timeout(5000)
                    body3 = await page.inner_text("body")
                    if "First Name" in body3:
                        print("  ✅ FORM AFTER APPLY MANUALLY!")
            elif "Sign In" in body2:
                if "wrong" in body2.lower() or "locked" in body2.lower():
                    print("  ⚠ Wrong password")
                    return "WRONG_PASSWORD"
                print(f"  Still on sign-in: {body2[:200]}")
            else:
                print(f"  After sign-in state: {body2[:200]}")
        else:
            return await create_account(page, acct, domain, url)
    
    elif "My Information" in initial_body or "Hello" in initial_body or "First Name" in initial_body:
        print("  ✅ Already signed in or on form!")
    elif "Start Your Application" in initial_body or "Apply Manually" in initial_body:
        print("  → Clicking Apply Manually...")
        am = page.locator('[data-automation-id="applyManually"]')
        if await am.is_visible(timeout=2000):
            await am.click()
            await page.wait_for_timeout(5000)
    
    return await advance_wizard(page)


async def create_account(page, acct, domain, url):
    print("  → Creating account...")
    pwd = _accounts.generate_password()
    try:
        await page.locator('#input-4').fill(acct["email"])
        await page.locator('#input-5').fill(pwd)
        await page.locator('#input-6').fill(pwd)
        await page.locator('#input-9').check()
        await page.wait_for_timeout(500)
    except Exception as e:
        print(f"  ⚠ Form fill error: {e}")
        return "FILL_FAILED"

    if await wd_click(page, "Create Account"):
        await page.wait_for_timeout(5000)
        body = await page.inner_text("body")
        if "My Information" in body or "my information" in body.lower() or "Hello" in body:
            if domain: _accounts.save_account(domain, acct["email"], pwd)
            print("  ✅ ACCOUNT CREATED!")
            return await advance_wizard(page)
        elif "Sign In" in body:
            # Account exists with this email
            if domain: _accounts.save_account(domain, acct["email"], pwd)
            await page.locator('[data-automation-id="email"]').fill(acct["email"])
            await page.locator('[data-automation-id="password"]').fill(pwd)
            await page.wait_for_timeout(500)
            if await wd_click(page, "Sign In"):
                await page.wait_for_timeout(5000)
                body2 = await page.inner_text("body")
                if "My Information" in body2 or "Hello" in body2:
                    print("  ✅ SIGNED IN AFTER CREATE!")
                    return await advance_wizard(page)
        print(f"  After create: {body[:200]}")
        return "CREATE_FAILED"
    return "CLICK_FAILED"


async def advance_wizard(page):
    """Advance through Workday wizard steps and submit."""
    print("  → Waiting for Simplify autofill...")
    await page.wait_for_timeout(8000)

    for step in range(10):
        # Check for submit button
        if await _has_button(page, "Submit Application") or await _has_button(page, "Submit"):
            print("  → Submit button found!")
            for name in ["Submit Application", "Submit"]:
                if await wd_click(page, name):
                    await page.wait_for_timeout(5000)
                    body = await page.inner_text("body")
                    for word in ["thank you", "submitted", "Your application"]:
                        if word in body.lower():
                            print("  ✅ APPLICATION SUBMITTED!")
                            return "SUBMITTED"
                    print(f"  After submit: {page.url[:80]}")
                    break
            return "REVIEW_STEP"

        # Click next/continue
        for name in ["Save and Continue", "Continue", "Next"]:
            if await _has_button(page, name) and await wd_click(page, name):
                await page.wait_for_timeout(3000)
                print(f"  → Clicked '{name}' (step {step+1})")
                break
        else:
            print(f"  → No navigation buttons found (step {step+1})")
            break
    return "WIZARD_END"


async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)

    queue = build_queue()
    targets = []
    for job in queue:
        url = job.get("url", "")
        if _accounts.tenant_domain(url):
            domain = _accounts.tenant_domain(url)
            if not domain: continue
            acct = _accounts.get_account(domain)
            if acct:
                targets.append((job, acct))

    print(f"Queue: {len(queue)} jobs | Workday with accounts: {len(targets)}")
    for job, acct in targets:
        print(f"  • {job['company']:25s} — {acct['email']}")

    if not targets:
        print("No Workday jobs with accounts.")
        return

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        results = []
        for job, acct in targets:
            r = await apply_workday(page, job, acct)
            results.append((job["company"], r))

        print(f"\n{'='*60}\nRESULTS:")
        for company, result in results:
            print(f"  {company:25s}: {result}")

        await ctx.close()


asyncio.run(main())

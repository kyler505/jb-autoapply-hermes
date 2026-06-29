#!/usr/bin/env python3
"""Run queue with longer timeout for Boeing/Cox/Sentry only."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-run"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accounts
from jb_autoapply.selector import build_queue

async def click_wd(page, text):
    """Click Workday button - force-click actual button first, then overlay fallback."""
    # Try force-clicking the actual button first
    aids = {"Create Account": "createAccountSubmitButton", "Sign In": "signInSubmitButton",
            "Submit": "resetPasswordButton", "Save and Continue": "saveAndContinueButton"}
    if text in aids:
        try:
            b = page.locator(f'[data-automation-id="{aids[text]}"]')
            if await b.is_visible(timeout=1000):
                await b.click(force=True)
                return True
        except: pass
    # Fallback: get_by_role (finds click_filter overlays)
    try:
        btn = page.get_by_role("button", name=text)
        if await btn.count() > 0:
            await btn.first.click()
            return True
    except: pass
    return False

async def has_wd(page, text):
    try: return await page.get_by_role("button", name=text).count() > 0
    except: return False

async def apply_job(page, job, acct):
    url, domain, company = job["url"], _accounts.tenant_domain(url:=job["url"]), job["company"]
    job_url, apply_url = url.rstrip("/"), url.rstrip("/") + "/apply/applyManually"
    email, pwd = acct["email"], acct["password"]
    print(f"\n{'='*60}\n{company} ({domain})")

    await page.goto(apply_url, timeout=30000)
    await page.wait_for_timeout(3000)
    sl = page.locator('[data-automation-id="signInLink"]')
    if await sl.is_visible(timeout=3000):
        await sl.click(); await page.wait_for_timeout(2000)
        await page.locator('[data-automation-id="email"]').fill(email)
        await page.locator('[data-automation-id="password"]').fill(pwd)
        await page.wait_for_timeout(500)
        await click_wd(page, "Sign In"); await page.wait_for_timeout(5000)

    await page.goto(job_url, timeout=30000)
    await page.wait_for_timeout(3000)
    ab = page.locator('[data-automation-id="adventureButton"]')
    if await ab.is_visible(timeout=3000):
        await ab.click(); await page.wait_for_timeout(3000)
        am = page.locator('[data-automation-id="applyManually"]')
        if await am.is_visible(timeout=5000):
            await am.click(); await page.wait_for_timeout(5000)
            ef = page.locator('[data-automation-id="email"]').first
            if await ef.is_visible(timeout=3000):
                await ef.fill(email)
                await page.locator('[data-automation-id="password"]').first.fill(pwd)
                vp = page.locator('[data-automation-id="verifyPassword"]')
                if await vp.is_visible(timeout=1000): await vp.fill(pwd)
                cb = page.locator('[data-automation-id="createAccountCheckbox"]')
                if await cb.is_visible(timeout=1000): await cb.check()
                await page.wait_for_timeout(500)
                if await click_wd(page, "Create Account"):
                    await page.wait_for_timeout(8000)
                    print("  → Step 1 submitted")
                    # Verify - check page state
                    body = await page.inner_text("body")
                    if "First Name" in body or "Save and Continue" in body:
                        print("  ✅ On step 2+!")
                else:
                    print("  ⚠ Create Account click failed")
        else: print("  ⚠ No Apply Manually")
    else: print("  ⚠ No Apply button")

    print("  → Simplify...")
    await page.wait_for_timeout(10000)

    for step in range(20):
        if await has_wd(page, "Submit") or await has_wd(page, "Submit Application"):
            for name in ["Submit Application", "Submit"]:
                if await click_wd(page, name):
                    await page.wait_for_timeout(5000)
                    b = await page.inner_text("body")
                    for w in ["thank you", "submitted", "Your application"]:
                        if w in b.lower(): return "SUBMITTED"
                    return "REVIEW"
        for name in ["Save and Continue", "Continue", "Next", "Save & Continue"]:
            if await has_wd(page, name) and await click_wd(page, name):
                await page.wait_for_timeout(3000)
                print(f"  → {name}")
                break
        else:
            print("  → End"); break
    return "WIZARD_END"

targets = []
for job in build_queue():
    d = _accounts.tenant_domain(job.get("url", ""))
    if d:
        acct = _accounts.get_account(d)
        if acct and not d.startswith("intel"):  # skip Intel (invalid URL)
            targets.append((job, acct))
print(f"Targets: {len(targets)}")

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        results = [(j["company"], await apply_job(page, j, a)) for j, a in targets]
        print(f"\n{'='*60}\nRESULTS:")
        for c, r in results: print(f"  {c:25s}: {r}")
        await ctx.close()

asyncio.run(main())

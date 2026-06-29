#!/usr/bin/env python3
"""Production Workday flow: create account, sign in, autofill, submit."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-prod"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accts


async def apply(page, url, email, domain, pwd):
    apply_url = url.rstrip("/") + "/apply/applyManually"
    await page.goto(apply_url, timeout=30000, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    body = await page.inner_text("body")

    # If sign-in page -> sign in
    if "Sign In" in body and "Email" in body and "Password" in body and "Create Account" not in body.split("Sign In")[0]:
        acct = _accts.get_account(domain)
        if acct:
            print(f"  → Signing in with stored password")
            await page.locator('#input-4').fill(acct["email"])
            await page.locator('#input-5').fill(acct["password"])
            await page.wait_for_timeout(500)
            cf = page.locator('[data-automation-id="click_filter"]')
            await cf.first.click(timeout=5000)
            await page.wait_for_timeout(5000)
            b2 = await page.inner_text("body")
            if "My Information" in b2 or "my information" in b2.lower():
                return "SIGNED_IN"
            elif "wrong" in b2.lower() or "locked" in b2.lower():
                return "WRONG_PASSWORD"
        return "SIGNIN_FAILED"

    # If create account page -> create account
    if "Create Account" in body:
        print(f"  → Creating account")
        await page.locator('#input-4').fill(email)
        await page.locator('#input-5').fill(pwd)
        await page.locator('#input-6').fill(pwd)
        await page.locator('#input-9').check()
        await page.wait_for_timeout(500)
        cf = page.locator('[data-automation-id="click_filter"]')
        await cf.first.click(timeout=5000)
        await page.wait_for_timeout(5000)
        b2 = await page.inner_text("body")
        if "My Information" in b2 or "my information" in b2.lower():
            _accts.save_account(domain, email, pwd)
            return "ACCOUNT_CREATED"
        elif "Sign In" in b2 and "Email" in b2:
            # Account exists already
            _accts.save_account(domain, email, pwd)
            await page.locator('#input-4').fill(email)
            await page.locator('#input-5').fill(pwd)
            await page.wait_for_timeout(500)
            cf2 = page.locator('[data-automation-id="click_filter"]')
            await cf2.first.click(timeout=5000)
            await page.wait_for_timeout(5000)
            b3 = await page.inner_text("body")
            if "My Information" in b3:
                return "SIGNED_IN_AFTER_CREATE"
        return "CREATE_FAILED"
    return "UNKNOWN"


async def main():
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Test Cox
        print("=== Cox ===")
        r = await apply(page,
            "https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352",
            "kcao@tamu.edu", "cox.wd1.myworkdayjobs.com",
            "Cox2026!WorkdayApp")
        print(f"  Result: {r}")

        body = await page.inner_text("body")
        if "My Information" in body:
            print("✅ ON APPLICATION FORM!")
            print(body[:800])

        await page.screenshot(path="/tmp/wd-final.png")
        print(f"\nAccounts:")
        for d, i in _accts.list_accounts().items():
            print(f"  {d:40s} {i['password']}")
        await context.close()


asyncio.run(main())

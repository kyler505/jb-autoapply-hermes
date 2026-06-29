#!/usr/bin/env python3
"""Simple: use Playwright .click() on the click_filter."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright
SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-simple"

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = context.pages[0] if context.pages else await context.new_page()

        url = "https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually"
        await page.goto(url, timeout=30000)
        await page.wait_for_timeout(4000)
        print(f"URL: {page.url}")

        # Check what's on the page
        body = await page.inner_text("body")
        
        if "Hello, Kyler" in body:
            print("✅ Already logged in!")
        elif "Sign In" in body and "Email" in body:
            print("Sign-in page - trying stored credentials...")
            acct = __import__("sys").path.insert(0, str(Path(__file__).resolve().parent / "src"))
            from jb_autoapply import accounts as a
            acct = a.get_account("cox.wd1.myworkdayjobs.com")
            if acct:
                await page.locator('#input-4').fill(acct["email"])
                await page.locator('#input-5').fill(acct["password"])
                await page.wait_for_timeout(500)
                # Use Playwright's native click on the actual button
                btn = page.get_by_role("button", name="Sign In")
                c = await btn.count()
                if c > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(5000)
                    print(f"  After sign-in: {page.url[:100]}")
                    body2 = await page.inner_text("body")
                    if "Hello" in body2 or "My Information" in body2:
                        print("✅ SIGNED IN!")
        elif "Create Account" in body:
            pwd = "Cox2026!TestApp"
            print("Create account page...")
            await page.locator('#input-4').fill("kcao@tamu.edu")
            await page.locator('#input-5').fill(pwd)
            await page.locator('#input-6').fill(pwd)
            await page.locator('#input-9').check()
            await page.wait_for_timeout(500)
            # Use Playwright's native click - click the actual button
            btn = page.locator('button[data-automation-id="createAccountSubmitButton"]')
            await btn.click(timeout=5000)
            await page.wait_for_timeout(5000)
            print(f"  After create: {page.url[:100]}")
            body2 = await page.inner_text("body")
            if "My Information" in body2:
                print("✅ ACCOUNT CREATED!")
                from jb_autoapply import accounts as a
                a.save_account("cox.wd1.myworkdayjobs.com", "kcao@tamu.edu", pwd)
            elif "Sign In" in body2:
                print("→ Sign-in page (account may already exist)")
        
        print(f"\nBody: {body[:300]}")
        await page.screenshot(path="/tmp/wd-simple.png")
        await context.close()
asyncio.run(main())

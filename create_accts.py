#!/usr/bin/env python3
"""Create Workday account from scratch using click_filter overlay."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-create-acct"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _a

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        for company, domain, url, email in [
            ("Cox", "cox.wd1.myworkdayjobs.com",
             "https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually",
             "kcao@tamu.edu"),
        ]:
            print(f"\n=== {company} ===")
            pwd = _a.generate_password()
            print(f"  Email: {email}")
            print(f"  Password: {pwd}")

            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(3000)

            # Fill create account form
            await page.locator('#input-4').fill(email)
            await page.locator('#input-5').fill(pwd)
            await page.locator('#input-6').fill(pwd)
            await page.locator('#input-9').check()
            await page.wait_for_timeout(500)

            # Click Create Account via get_by_role (finds click_filter overlay)
            btn = page.get_by_role("button", name="Create Account")
            c = await btn.count()
            print(f"  'Create Account' buttons found: {c}")
            if c > 0:
                await btn.first.click()
                print("  Clicked!")
                await page.wait_for_timeout(5000)

            print(f"  URL after: {page.url}")
            body = await page.inner_text("body")

            # Check result  
            if "Sign In" in body and "Email" in body and "Password" in body:
                print("  → Account exists. Trying sign-in with generated password...")
                await page.locator('[data-automation-id="email"]').fill(email)
                await page.locator('[data-automation-id="password"]').fill(pwd)
                await page.wait_for_timeout(500)
                si = page.get_by_role("button", name="Sign In")
                if await si.count() > 0:
                    await si.first.click()
                    await page.wait_for_timeout(5000)
                    print(f"  URL: {page.url}")
                    body2 = await page.inner_text("body")
                    if "My Information" in body2 and "Save" not in body2:
                        print(f"  ✅ SIGNED IN! Form fields visible: {'First Name' in body2}")
                        _a.save_account(domain, email, pwd) if 'First Name' in body2 else None
                    elif "wrong" in body2.lower():
                        print("  ❌ Wrong password")
                    else:
                        print(f"  Body: {body2[:300]}")
            elif "My Information" in body:
                # Check if we're ACTUALLY on the form (not just progress bar)
                # Look for form fields
                has_fields = "First Name" in body or "Last Name" in body or "Email" in body
                print(f"  Has form fields: {has_fields}")
                if has_fields:
                    _a.save_account(domain, email, pwd)
                    print(f"  ✅ ACCOUNT CREATED AND SAVED!")
                else:
                    print(f"  ⚠ Progress bar shows My Info but form not visible")
                    print(f"  Body: {body[:500]}")
            elif "wrong" in body.lower():
                print(f"  ❌ Error: {body[:200]}")
            elif "Create Account" in body:
                print(f"  Still on create account page")
                print(f"  Body: {body[:300]}")
            else:
                print(f"  Body: {body[:300]}")

        await ctx.close()
asyncio.run(main())

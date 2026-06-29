#!/usr/bin/env python3
"""Step 1: Trigger forgot-password emails for all Workday accounts."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-trigger"

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        for name, url in [
            ("Cox", "https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually"),
            ("KLA", "https://kla.wd1.myworkdayjobs.com/en-US/Search/job/Milpitas-CA/Sr-Software-Engineer_2638120/apply/applyManually"),
            ("Sentry", "https://sentryinsurance.wd1.myworkdayjobs.com/en-US/SentryCareers/job/Stevens-Point-WI/Software-Developer--Hybrid-Work-Model-_JR-142351/apply/applyManually"),
        ]:
            print(f"\n=== {name} ===")
            await page.goto(url, timeout=30000)
            await page.wait_for_timeout(3000)

            # Click Forgot Password
            fp = page.locator('[data-automation-id="forgotPasswordLink"]')
            if await fp.is_visible(timeout=3000):
                await fp.click()
                await page.wait_for_timeout(2000)
                print("  Forgot password dialog opened")

            # Fill email
            ei = page.locator('[data-automation-id="email"]')
            if await ei.is_visible(timeout=3000):
                await ei.fill("kcao@tamu.edu")
                await page.wait_for_timeout(500)
                print("  Email filled")

            # Click Reset Password
            rp = page.get_by_role("button", name="Reset Password")
            c = await rp.count()
            print(f"  Reset Password buttons: {c}")
            if c > 0:
                await rp.first.click()
                await page.wait_for_timeout(3000)
                body = await page.inner_text("body")
                # Check for confirmation
                if "sent" in body.lower() or "email" in body.lower() or "check" in body.lower():
                    print("  ✅ Reset email sent!")
                else:
                    print(f"  After click: {body[:200]}")
            else:
                print("  ❌ No Reset Password button found")

        await ctx.close()
        print("\nDone. Check Gmail for reset links.")

asyncio.run(main())

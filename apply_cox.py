#!/usr/bin/env python3
"""Apply to Cox (Workday) using Simplify + NopeCHA from filled profile."""
import asyncio, os
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-filled-v2"  # Same profile from simplify_fill_profile.py


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
            slow_mo=300,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Go to Cox Workday job
        print("1. Navigating to Cox job...")
        await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"   URL: {page.url}")

        # Step 2: Click Apply Manually
        print("2. Clicking Apply Manually...")
        try:
            await page.getByRole('button', { name: 'Apply Manually' }).click()
            await page.wait_for_timeout(4000)
        except:
            # Fallback
            try:
                await page.evaluate("document.querySelector('button[data-automation-id=\"applyManually\"]')?.click()")
                await page.wait_for_timeout(4000)
            except:
                print("   Trying alternative...")
                await page.goto(page.url + "/applyManually", timeout=30000)
                await page.wait_for_timeout(4000)
        
        print(f"   URL: {page.url}")

        # Step 3: Check if we need to create account or sign in
        body = await page.inner_text("body")
        
        if "Create Account" in body or "create an account" in body.lower():
            print("3. Creating Workday account...")
            # Fill account creation form
            await page.locator('[data-automation-id="email"]').fill("kcao@tamu.edu")
            await page.locator('[data-automation-id="password"]').fill("CoxApp2026!Secure")
            await page.locator('[data-automation-id="verifyPassword"]').fill("CoxApp2026!Secure")
            await page.locator('[data-automation-id="createAccountCheckbox"]').check()
            await page.wait_for_timeout(500)
            await page.getByRole('button', { name: 'Create Account' }).click()
            await page.wait_for_timeout(5000)
            print(f"   URL: {page.url}")

        if "Sign In" in body or "sign in" in body.lower():
            print("3. At sign-in page, signing in...")
            try:
                await page.locator('[data-automation-id="email"]').fill("kcao@tamu.edu")
                await page.locator('[data-automation-id="password"]').fill("CoxApp2026!Secure!")
                await page.wait_for_timeout(500)
                await page.getByRole('button', { name: 'Sign In' }).click()
                await page.wait_for_timeout(5000)
            except:
                pass

        # Step 4: Let Simplify auto-fill + NopeCHA handle CAPTCHAs
        print("4. Waiting for Simplify to detect and fill form...")
        await page.wait_for_timeout(5000)
        
        # Take screenshot
        await page.screenshot(path="/tmp/cox-apply-state.png")
        print(f"   Current URL: {page.url}")
        body2 = await page.inner_text("body")
        print(f"   Body: {body2[:800]}")

        # Step 5: Check for Submit button and click
        if "Submit" in body2 or "Review" in body2 or "Continue" in body2:
            print("5. Form loaded, attempting to submit...")
            # Wait for Simplify to fill
            await page.wait_for_timeout(3000)
            
            # Try clicking Submit
            for btn_text in ["Submit Application", "Submit", "Save and Continue", "Review and Submit"]:
                try:
                    btn = page.getByRole('button', { name: btn_text })
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(3000)
                        print(f"   Clicked '{btn_text}'")
                        break
                except:
                    pass
        
        await page.screenshot(path="/tmp/cox-final-state.png")
        print(f"\nFinal URL: {page.url}")
        body3 = await page.inner_text("body")
        print(f"Final body: {body3[:500]}")
        
        # Keep browser open for 30s to see result
        await page.wait_for_timeout(5000)
        await context.close()


asyncio.run(main())

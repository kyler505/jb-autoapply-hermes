#!/usr/bin/env python3
"""Apply to Muru using Simplify + NopeCHA (retry with CAPTCHA handling)."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-muru"
RESUME = "/home/kyler/.hermes/.playwright-mcp/uploads/resume_har.pdf"


async def main():
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
            slow_mo=200,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Login to Simplify
        print("1. Logging into Simplify...")
        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except: pass
        await page.locator('input[placeholder="Email Address"]').fill("kylercao18@gmail.com")
        await page.locator('input[placeholder="Password"]').fill("Monkeytype1511")
        await page.wait_for_timeout(1000)
        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(5000)
        print(f"   Simplify: {'dashboard' in page.url}")

        # Navigate to Muru job
        print("2. Navigating to Muru job...")
        await page.goto("https://www.murumed.com/job-listings/web-software-engineer-intern", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"   URL: {page.url}")

        # Wait for NopeCHA + Simplify
        print("3. Waiting for NopeCHA/Solve CAPTCHA + Simplify autofill...")
        await page.wait_for_timeout(10000)

        # Check page state
        body = await page.inner_text("body")
        print(f"   Body: {body[:1000]}")

        # Look for application form
        if "First Name" in body or "apply" in body.lower():
            print("\n4. Form found, attempting to fill and submit...")
            
            # Upload resume if needed
            file_input = page.locator('input[type="file"]')
            if await file_input.is_visible(timeout=3000):
                await file_input.set_input_files(RESUME)
                await page.wait_for_timeout(2000)

            # Try submitting
            for btn_text in ["Submit", "Apply", "Send Application"]:
                try:
                    btn = page.locator(f'button:has-text("{btn_text}")')
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(5000)
                        break
                except: pass

        await page.screenshot(path="/tmp/muru-result.png")
        print(f"\nFinal URL: {page.url}")
        body2 = await page.inner_text("body")
        if "thank you" in body2.lower() or "submitted" in body2.lower():
            print("✅ APPLICATION SUBMITTED!") 
        else:
            print(f"Final: {body2[:500]}")
        
        await context.close()


asyncio.run(main())

#!/usr/bin/env python3
"""Apply to Abound (Ashby) using Simplify + NopeCHA."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-abound"


async def main():
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
            slow_mo=100,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Login to Simplify so profile is available
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

        # Navigate to Abound job on Ashby
        print("2. Navigating to Abound job...")
        await page.goto("https://jobs.ashbyhq.com/Abound/7ae69c2b-1dae-40c6-a5b2-8f5b42157263/application", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"   URL: {page.url}")

        # Wait for Simplify to detect and fill
        print("3. Waiting for Simplify autofill + NopeCHA CAPTCHA...")
        body_before = await page.inner_text("body")
        if "Autofill from resume" in body_before or "Upload file" in body_before:
            print("   Simplify popup detected!")
        await page.wait_for_timeout(8000)

        # Check what's on the page
        body = await page.inner_text("body")
        print(f"   Body: {body[:800]}")

        # Check for Submit button
        for btn_name in ["Submit Application", "Submit", "Save and Continue"]:
            try:
                btn = page.getByRole('button', { name: btn_name })
                if await btn.is_visible(timeout=2000):
                    print(f"   ✅ '{btn_name}' button visible!")
                    await btn.click()
                    await page.wait_for_timeout(5000)
                    print(f"   URL after submit: {page.url}")
                    body2 = await page.inner_text("body")
                    print(f"   Body: {body2[:500]}")
                    break
            except:
                pass

        await page.screenshot(path="/tmp/abound-result.png")
        print(f"\nFinal URL: {page.url}")
        await context.close()


asyncio.run(main())

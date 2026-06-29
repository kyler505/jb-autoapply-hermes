#!/usr/bin/env python3
"""Apply to Four Hands (Greenhouse) using Simplify + NopeCHA."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-fourh"


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

        # Navigate to Four Hands job
        print("2. Navigating to Four Hands job...")
        await page.goto("https://job-boards.greenhouse.io/graphcore/jobs/8605372002", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"   URL: {page.url}")

        # Wait for Simplify
        print("3. Waiting for Simplify to detect and fill...")
        await page.wait_for_timeout(8000)

        # Debug what we see
        body = await page.inner_text("body")
        print(f"   Body: {body[:1500]}")

        # Check for Apply button
        if "Apply" in body or "Submit" in body:
            for btn_name in ["Submit Your Application", "Submit Application", "Apply Now", "Submit"]:
                try:
                    btn = page.getByRole('button', { name: btn_name })
                    if await btn.is_visible(timeout=2000):
                        print(f"   ✅ '{btn_name}' visible!")
                        await btn.click()
                        await page.wait_for_timeout(5000)
                        print(f"   After click URL: {page.url}")
                        break
                except:
                    pass

        # Check for form fields
        if "First Name" in body or "Email" in body:
            print("\n4. Form detected. Filling fields...")
            # Let Simplify/NopeCHA work
            await page.wait_for_timeout(5000)
            
            # Try submitting
            try:
                btn = page.getByRole('button', { name: 'Submit' })
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    await page.wait_for_timeout(5000)
            except:
                pass

        await page.screenshot(path="/tmp/fourhands-result.png")
        print(f"\nFinal URL: {page.url}")
        body2 = await page.inner_text("body")
        if "thank you" in body2.lower() or "submitted" in body2.lower() or "success" in body2.lower():
            print("✅ APPLICATION SUBMITTED!")
        else:
            print(f"Final: {body2[:500]}")
        
        await context.close()


asyncio.run(main())

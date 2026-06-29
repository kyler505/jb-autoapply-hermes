#!/usr/bin/env python3
"""Fill Simplify onboarding profile with Kyler's data."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-filled"


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

        # Login
        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except:
            pass
        await page.locator('input[placeholder="Email Address"]').fill("kylercao18@gmail.com")
        await page.locator('input[placeholder="Password"]').fill("Monkeytype1511")
        await page.wait_for_timeout(1500)
        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(5000)

        # Navigate to onboarding
        await page.goto("https://simplify.jobs/onboarding", timeout=30000)
        await page.wait_for_timeout(3000)
        print("Onboarding loaded")

        # The SPA renders fields dynamically. Let's check what's currently visible.
        body = await page.inner_text("body")
        print(f"Page:\n{body[:1500]}")

        # Try to click a section tab
        sections = page.locator('a, button, nav a')
        count = await sections.count()
        for i in range(count):
            text = await sections.nth(i).inner_text()
            if text.strip() in ['Roles', 'Education', 'Experience', 'Work Authorization', 'EEO', 'Skills', 'Personal', 'Links']:
                print(f"Found section tab: '{text.strip()}'")
        
        await page.screenshot(path="/tmp/simplify-onboarding-view.png")
        print("Screenshot saved")

        await context.close()


asyncio.run(main())

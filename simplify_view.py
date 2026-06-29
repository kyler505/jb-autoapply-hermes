#!/usr/bin/env python3
"""View Simplify profile."""
import asyncio, sys, os
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-p2"


async def main():
    # Clean old profile
    import shutil
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)

        # Cookie
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except:
            pass

        # Login
        await page.locator('input[placeholder="Email Address"]').fill("kylercao18@gmail.com")
        await page.locator('input[placeholder="Password"]').fill("Monkeytype1511")
        await page.wait_for_timeout(1500)
        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(5000)

        print(f"URL: {page.url}")

        if "dashboard" in page.url:
            # Go to profile
            await page.goto("https://simplify.jobs/dashboard/profile", timeout=30000)
            await page.wait_for_timeout(4000)
            print(f"Profile URL: {page.url}")

        await page.screenshot(path="/tmp/simplify-view.png", full_page=True)
        body = await page.inner_text("body")
        print(f"Body:\n{body[:3000]}")

        await context.close()


asyncio.run(main())

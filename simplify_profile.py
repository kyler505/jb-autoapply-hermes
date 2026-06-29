#!/usr/bin/env python3
"""Open Simplify dashboard and navigate to profile settings."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

SIMPLIFY_DIR = str(Path.home() / ".simplify" / "chromium")
NOPECHA_DIR = str(Path.home() / ".nopecha" / "chromium")


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/simplify-profile",
            headless=False,
            args=[
                f"--load-extension={SIMPLIFY_DIR},{NOPECHA_DIR}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Go to dashboard (already logged in from previous session)
        await page.goto("https://simplify.jobs/dashboard/profile", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"URL: {page.url}")

        await page.screenshot(path="/tmp/simplify-profile.png", full_page=True)
        print("Profile screenshot saved")

        # Print what's on the page
        body = await page.inner_text("body")
        print(f"Body: {body[:2000]}")

        # Keep open for user interaction
        print("\nBrowser is open. Press Ctrl+C to close.")
        await asyncio.sleep(300)

        await context.close()


asyncio.run(main())

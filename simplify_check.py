#!/usr/bin/env python3
"""Quick Simplify login check with screenshot."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

EMAIL = "kylercao18@gmail.com"
PASSWORD = "Monkeytype1511"
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

        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)

        try:
            await page.locator('button:has-text("Accept All")').click(timeout=5000)
            await page.wait_for_timeout(1000)
        except:
            pass

        await page.locator('input[placeholder="Email Address"]').fill(EMAIL)
        await page.wait_for_timeout(300)
        await page.locator('input[placeholder="Password"]').fill(PASSWORD)
        await page.wait_for_timeout(500)

        await page.screenshot(path="/tmp/simplify-before-submit.png")
        print("Screenshot 1: before submit")

        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(3000)

        await page.screenshot(path="/tmp/simplify-after-submit.png")
        print("Screenshot 2: after submit")
        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        body = await page.inner_text("body")
        print(f"Body: {body[:1000]}")

        await context.close()


asyncio.run(main())

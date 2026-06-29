#!/usr/bin/env python3
"""Login to Simplify using Playwright with NopeCHA + Simplify extensions loaded."""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

EMAIL = "kylercao18@gmail.com"
PASSWORD = "Monkeytype1511"
SIMPLIFY_DIR = Path.home() / ".simplify" / "chromium"
NOPECHA_DIR = Path.home() / ".nopecha" / "chromium"


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/simplify-login-profile",
            headless=False,
            args=[
                f"--load-extension={SIMPLIFY_DIR},{NOPECHA_DIR}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            slow_mo=300,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        print("1. Navigating to Simplify login...")
        await page.goto("https://simplify.jobs/auth/login", timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Dismiss cookie banner
        try:
            accept = page.locator('button:has-text("Accept All")')
            if await accept.is_visible(timeout=3000):
                await accept.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        print("2. Filling email...")
        await page.locator('input[placeholder="Email Address"]').fill(EMAIL)
        await page.wait_for_timeout(500)

        print("3. Filling password...")
        await page.locator('input[placeholder="Password"]').fill(PASSWORD)
        await page.wait_for_timeout(1000)

        # NopeCHA handles any CAPTCHA
        print("4. Waiting for NopeCHA to handle CAPTCHA...")
        await page.wait_for_timeout(3000)

        print("5. Clicking Sign In...")
        await page.locator('button:has-text("Sign in")').click()
        await page.wait_for_timeout(8000)

        print(f"URL: {page.url}")
        print(f"Title: {await page.title()}")

        await page.screenshot(path="/tmp/simplify-login-result.png")
        print("Screenshot saved")

        if "dashboard" in page.url.lower() or "app" in page.url.lower() or "profile" in page.url.lower():
            print("✅ LOGIN SUCCESSFUL!")
            await page.goto("https://simplify.jobs/dashboard/profile", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path="/tmp/simplify-profile.png")
            print("Profile screenshot saved")

            # Keep the browser open for 5 minutes so the user can interact
            print("\nBrowser is open. Press Ctrl+C to close.")
            await asyncio.sleep(300)
        else:
            print("⚠️  Still on login page")
            body = await page.inner_text("body")
            print(body[:1500])

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Explore Simplify dashboard."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-p3"


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

        print(f"Dashboard URL: {page.url}")

        # Try common profile URLs
        profile_urls = [
            "/dashboard",
            "/settings",
            "/profile",
            "/applications",
            "/account",
            "/onboarding",
        ]
        for path in profile_urls:
            await page.goto(f"https://simplify.jobs{path}", timeout=15000)
            await page.wait_for_timeout(2000)
            body = await page.inner_text("body")
            print(f"\n{path} -> {page.url}")
            print(f"  {body[:200].strip()}")

        await page.screenshot(path="/tmp/simplify-dashboard.png")
        await context.close()


asyncio.run(main())

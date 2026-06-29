#!/usr/bin/env python3
"""Check Simplify onboarding/profile state."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-p4"


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

        # Login first
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

        # Go to onboarding
        await page.goto("https://simplify.jobs/onboarding", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"Onboarding URL: {page.url}")

        # Check each section
        sections = ["roles", "experience", "education", "work-authorization", "eeo", "skills", "personal", "links"]
        for s in sections:
            await page.goto(f"https://simplify.jobs/onboarding#{s}", timeout=15000)
            await page.wait_for_timeout(2000)
            body = await page.inner_text("body")
            # Get 5 lines
            lines = [l.strip() for l in body.split('\n') if l.strip()]
            print(f"\n=== {s} ===")
            for l in lines[:15]:
                print(f"  {l}")

        await page.screenshot(path="/tmp/simplify-onboarding.png")
        await context.close()


asyncio.run(main())

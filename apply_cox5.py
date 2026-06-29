#!/usr/bin/env python3
"""Check if Cox account was created and sign in."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-cox2"


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate to job and try signing in
        await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply", timeout=30000)
        await page.wait_for_timeout(3000)

        # Click Sign In in the top nav
        await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.innerText.trim() === 'Sign In' && b.offsetParent !== null) {
                        b.click();
                        return;
                    }
                }
            }
        """)
        await page.wait_for_timeout(3000)

        # Click Sign In in dialog
        await page.locator('#input-4').fill("kcao@tamu.edu")
        await page.locator('#input-5').fill("CoxApp2026!Secure1")
        await page.wait_for_timeout(500)

        # Click dialog sign in button
        await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.innerText.trim() === 'Sign In' && b.offsetParent !== null) {
                        b.click();
                        return;
                    }
                }
            }
        """)
        await page.wait_for_timeout(5000)

        print(f"URL: {page.url}")
        body = await page.inner_text("body")
        print(f"Body: {body[:1000]}")

        # Check if logged in (look for My Information)
        if "My Information" in body:
            print("✅ SIGNED IN! Application form should load...")
            await page.wait_for_timeout(3000)

        await page.screenshot(path="/tmp/cox-signin.png")
        await context.close()


asyncio.run(main())

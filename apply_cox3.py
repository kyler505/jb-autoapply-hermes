#!/usr/bin/env python3
"""Cox Workday account creation with debugging."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-cox"


async def main():
    import shutil, os
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Go directly to account creation
        await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(3000)

        # Debug: find all input elements
        inputs = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('input');
                return Array.from(all).map(i => ({
                    id: i.id,
                    type: i.type,
                    'data-automation-id': i.getAttribute('data-automation-id'),
                    placeholder: i.placeholder,
                    className: i.className.slice(0,40)
                }));
            }
        """)
        print("Inputs found:")
        for inp in inputs:
            print(f"  {inp}")

        # Fill fields by ID
        pwd = "CoxApp2026!Secure1"
        await page.locator('#input-4').fill("kcao@tamu.edu")
        await page.wait_for_timeout(200)
        await page.locator('#input-5').fill(pwd)
        await page.wait_for_timeout(200)
        await page.locator('#input-6').fill(pwd)
        await page.wait_for_timeout(200)
        await page.locator('#input-9').check()
        await page.wait_for_timeout(500)

        # Click Create Account button
        btn_result = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.innerText.includes('Create Account')) {
                        b.click();
                        return 'clicked';
                    }
                }
                return 'no button found';
            }
        """)
        print(f"Button click: {btn_result}")
        await page.wait_for_timeout(5000)

        print(f"\nURL: {page.url}")
        body = await page.inner_text("body")
        print(f"Body: {body[:1500]}")

        await page.screenshot(path="/tmp/cox-account.png")
        await context.close()


asyncio.run(main())

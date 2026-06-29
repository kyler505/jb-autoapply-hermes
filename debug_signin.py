#!/usr/bin/env python3
"""Debug sign-in dialog after clicking Sign In link."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright
SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-signin-debug"

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = context.pages[0] if context.pages else await context.new_page()
        
        await page.goto("https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Click Sign In link
        await page.locator('[data-automation-id="signInLink"]').click()
        await page.wait_for_timeout(3000)
        
        # Find all inputs in the dialog
        inputs = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('input');
                return Array.from(all).map(i => ({
                    id: i.id,
                    type: i.type,
                    'data-automation-id': i.getAttribute('data-automation-id'),
                    placeholder: i.placeholder,
                    visible: i.offsetParent !== null,
                }));
            }
        """)
        print("Inputs after clicking Sign In:")
        for inp in inputs:
            print(f"  id={inp['id']:10s} type={inp['type']:10s} auto={inp['data-automation-id']}")
        
        # Find all click_filter overlays
        filters = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('[data-automation-id="click_filter"]');
                return Array.from(els).map(el => ({
                    ariaLabel: el.getAttribute('aria-label'),
                    visible: el.offsetParent !== null
                }));
            }
        """)
        print("\nClick filters:")
        for f in filters:
            print(f"  aria='{f['ariaLabel']}' visible={f['visible']}")
        
        await context.close()
asyncio.run(main())

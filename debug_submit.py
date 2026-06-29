#!/usr/bin/env python3
"""Debug Submit button on Workday form."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright
SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-submit-debug"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as a

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = context.pages[0] if context.pages else await context.new_page()

        # Go to Sentry (we have working sign-in)
        acct = a.get_account("sentryinsurance.wd1.myworkdayjobs.com")
        await page.goto("https://sentryinsurance.wd1.myworkdayjobs.com/en-US/SentryCareers/job/Stevens-Point-WI/Software-Developer--Hybrid-Work-Model-_JR-142351/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(3000)

        # Sign in
        await page.locator('[data-automation-id="signInLink"]').click()
        await page.wait_for_timeout(3000)
        await page.locator('[data-automation-id="email"]').fill(acct["email"])
        await page.locator('[data-automation-id="password"]').fill(acct["password"])
        await page.wait_for_timeout(500)
        si = page.locator('[data-automation-id="signInSubmitButton"]')
        if await si.is_visible(timeout=3000):
            await si.click()
            await page.wait_for_timeout(5000)
        
        # Wait for form + Simplify
        print("Waiting for Simplify...")
        await page.wait_for_timeout(8000)
        
        click_filter_info = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('[data-automation-id="click_filter"]');
                return Array.from(els).map(el => ({
                    ariaLabel: el.getAttribute('aria-label'),
                    parentText: (el.parentElement?.innerText || '').trim().slice(0,60),
                }));
            }
        """)
        print("Click filters:")
        for f in click_filter_info:
            print(f"  aria='{f['ariaLabel']}' parent='{f['parentText']}'")
        
        # Check for buttons with Submit and continue/save
        buttons_info = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button, [role="button"]');
                return Array.from(btns).map(b => ({
                    text: (b.innerText || '').trim().slice(0,40),
                    autoId: b.getAttribute('data-automation-id'),
                    ariaLabel: b.getAttribute('aria-label'),
                    visible: b.offsetParent !== null,
                })).filter(b => b.visible && (b.text || b.ariaLabel));
            }
        """)
        print("\nVisible buttons:")
        for b in buttons_info:
            print(f"  text='{b['text']}' auto='{b['autoId']}' aria='{b['ariaLabel']}'")
        
        print("\nLooking for 'Submit', 'Review', 'Continue', 'Save'...")
        for b in buttons_info:
            t = (b['text'] + ' ' + (b['ariaLabel'] or '')).lower()
            if any(k in t for k in ['submit', 'review', 'continue', 'save', 'finish']):
                print(f"  ✅ FOUND: text='{b['text']}' auto='{b['autoId']}' aria='{b['ariaLabel']}'")

        await context.close()
asyncio.run(main())

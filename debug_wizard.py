#!/usr/bin/env python3
"""Debug Workday wizard steps and buttons."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright
SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-wizard"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as a

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = context.pages[0] if context.pages else await context.new_page()
        
        acct = a.get_account("cox.wd1.myworkdayjobs.com")
        await page.goto("https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Sign in via click_filter overlay (same as wd_click in run_queue.py)
        await page.locator('[data-automation-id="signInLink"]').click()
        await page.wait_for_timeout(3000)
        await page.locator('[data-automation-id="email"]').fill(acct["email"])
        await page.locator('[data-automation-id="password"]').fill(acct["password"])
        await page.wait_for_timeout(500)
        overlay = page.locator('[data-automation-id="click_filter"][aria-label="Sign In"]').first
        if await overlay.is_visible(timeout=3000):
            await overlay.click()
            await page.wait_for_timeout(5000)
        
        # Now on form - check step progress
        body = await page.inner_text("body")
        print("Step progress found in body:")
        for line in body.split('\n'):
            step = line.strip()
            if 'step' in step.lower() or 'current' in step.lower():
                print(f"  {step}")
        
        # Find clickable buttons (not hidden)
        btns = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('button, [role="button"]');
                return Array.from(all).map(b => ({
                    text: (b.innerText || '').trim().slice(0,40),
                    autoId: b.getAttribute('data-automation-id'),
                    aria: b.getAttribute('aria-label'),
                    visible: b.offsetParent !== null,
                    rect: b.offsetParent ? 'visible' : 'hidden'
                })).filter(b => b.visible && (b.text || b.aria));
            }
        """)
        print("\nClickable buttons:")
        for b in btns:
            print(f"  text='{b['text']}' auto='{b['autoId']}' aria='{b['aria']}'")
        
        await context.close()
asyncio.run(main())

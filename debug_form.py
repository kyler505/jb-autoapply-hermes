#!/usr/bin/env python3
"""Debug Workday form buttons after sign-in."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright
SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-form-debug"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as a

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        acct = a.get_account("cox.wd1.myworkdayjobs.com")
        await page.goto("https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(3000)
        
        # Sign in
        await page.locator('[data-automation-id="signInLink"]').click()
        await page.wait_for_timeout(3000)
        await page.locator('[data-automation-id="email"]').fill(acct["email"])
        await page.locator('[data-automation-id="password"]').fill(acct["password"])
        await page.wait_for_timeout(500)
        await page.get_by_role("button", name="Sign In").first.click()
        await page.wait_for_timeout(5000)
        
        print(f"URL: {page.url}")
        
        # Find ALL interactive elements
        btns = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('button, [role="button"], a, input[type="submit"]');
                return Array.from(all).map(b => ({
                    tag: b.tagName,
                    text: (b.innerText || b.value || '').trim().slice(0,50),
                    autoId: b.getAttribute('data-automation-id'),
                    aria: b.getAttribute('aria-label'),
                    visible: b.offsetParent !== null,
                    tabIndex: b.getAttribute('tabindex'),
                })).filter(b => b.visible);
            }
        """)
        for b in btns:
            print(f"  [{b['tag']:6s}] text='{b['text']:30s}' auto={str(b['autoId']):30s} aria='{b['aria']}' tab={b['tabIndex']}")
        
        await ctx.close()
asyncio.run(main())

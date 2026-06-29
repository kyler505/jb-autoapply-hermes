#!/usr/bin/env python3
"""Debug reset password page buttons."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright
SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")

async def main():
    p = "/tmp/wd-reset-debug"
    if os.path.exists(p): shutil.rmtree(p)
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(user_data_dir=p, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        # Use the Cox reset link
        await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/passwordreset/13gktktcvl93at98zw1vwvcdm", timeout=30000)
        await page.wait_for_timeout(3000)
        print(f"URL: {page.url}")
        
        # Find all buttons and interactive elements
        btns = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('button, [role="button"], input[type="submit"]');
                return Array.from(all).map(b => ({
                    tag: b.tagName,
                    text: (b.innerText || b.value || '').trim().slice(0,40),
                    autoId: b.getAttribute('data-automation-id'),
                    aria: b.getAttribute('aria-label'),
                    visible: b.offsetParent !== null,
                    tab: b.getAttribute('tabindex'),
                })).filter(b => b.visible);
            }
        """)
        for b in btns:
            print(f"  [{b['tag']:6s}] text='{b['text']:30s}' auto={str(b['autoId']):30s} aria='{b['aria']}'")
        
        await ctx.close()
asyncio.run(main())

#!/usr/bin/env python3
"""Explore Muru job page for apply flow."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-muru2"


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

        await page.goto("https://www.murumed.com/job-listings/web-software-engineer-intern", timeout=30000)
        await page.wait_for_timeout(3000)

        # Find all links and buttons on the page
        elements = await page.evaluate("""
            () => {
                const links = document.querySelectorAll('a, button, [role="button"]');
                return Array.from(links).map(el => ({
                    tag: el.tagName,
                    text: (el.innerText || '').trim().slice(0, 50),
                    href: el.href ? el.href.slice(0, 100) : '',
                    visible: el.offsetParent !== null
                })).filter(el => el.text || el.href);
            }
        """)
        print("Interactive elements:")
        for el in elements:
            if el['visible']:
                print(f"  [{el['tag']}] {el['text'][:40]:40s} {el['href'][:60]}")

        await context.close()


asyncio.run(main())

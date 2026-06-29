#!/usr/bin/env python3
"""Inspect Simplify onboarding sections to see available fields."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-inspect"


async def main():
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
            slow_mo=200,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Login
        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except: pass
        await page.locator('input[placeholder="Email Address"]').fill("kylercao18@gmail.com")
        await page.locator('input[placeholder="Password"]').fill("Monkeytype1511")
        await page.wait_for_timeout(1500)
        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(5000)
        print("Logged in")

        # Go to onboarding and inspect each section tab
        await page.goto("https://simplify.jobs/onboarding", timeout=30000)
        await page.wait_for_timeout(3000)

        # Click each section and dump the field labels
        sections = [
            ("Roles", "onboarding-roles"),
            ("Education", "onboarding-education"),
            ("Experience", "onboarding-experience"),
            ("Work Authorization", "onboarding-work-authorization"),
            ("EEO", "onboarding-eeo"),
            ("Skills", "onboarding-skills"),
            ("Personal", "onboarding-personal"),
            ("Links", "onboarding-links"),
        ]
        
        for section_name, section_hash in sections:
            await page.goto(f"https://simplify.jobs/onboarding#{section_hash}", timeout=15000)
            await page.wait_for_timeout(2000)
            
            # Get all visible labels, inputs, selects
            fields = await page.evaluate("""
                () => {
                    const labels = document.querySelectorAll('label, [class*="label"], p, span, h1, h2, h3, h4');
                    const result = [];
                    labels.forEach(l => {
                        const text = l.innerText.trim();
                        if (text && text.length > 2 && text.length < 100) {
                            result.push(text);
                        }
                    });
                    return [...new Set(result)].slice(0, 60);
                }
            """)
            
            print(f"\n=== {section_name} ===")
            for f in fields:
                print(f"  {f}")

        await context.close()


asyncio.run(main())

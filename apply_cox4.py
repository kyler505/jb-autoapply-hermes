#!/usr/bin/env python3
"""Cox account creation with error checking."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-cox2"


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

        await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(3000)

        pwd = "CoxApp2026!Secure1"

        # Type into fields (real typing, not fill)
        await page.locator('#input-4').press_sequentially("kcao@tamu.edu", delay=50)
        await page.wait_for_timeout(300)
        await page.locator('#input-5').press_sequentially(pwd, delay=50)
        await page.wait_for_timeout(300)
        await page.locator('#input-6').press_sequentially(pwd, delay=50)
        await page.wait_for_timeout(300)
        await page.locator('#input-9').check()
        await page.wait_for_timeout(1000)

        # Check field values
        values = await page.evaluate("""
            () => ({
                email: document.getElementById('input-4')?.value,
                pwd: document.getElementById('input-5')?.value ? 'set' : 'empty',
                verify: document.getElementById('input-6')?.value ? 'set' : 'empty',
                checked: document.getElementById('input-9')?.checked,
            })
        """)
        print(f"Values before submit: {values}")

        # Click Create Account
        await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.innerText.includes('Create Account') && b.offsetParent !== null) {
                        b.click();
                        return 'clicked';
                    }
                }
                return 'not found';
            }
        """)
        await page.wait_for_timeout(5000)

        # Check for errors
        errors = await page.evaluate("""
            () => {
                const result = [];
                document.querySelectorAll('*').forEach(el => {
                    if ((el.getAttribute('role') === 'alert') ||
                        el.getAttribute('aria-invalid') === 'true' ||
                        (el.className && el.className.includes && el.className.includes('error'))) {
                        result.push({
                            tag: el.tagName,
                            id: el.id,
                            text: (el.innerText || '').slice(0,100),
                            invalid: el.getAttribute('aria-invalid')
                        });
                    }
                });
                return result.slice(0,10);
            }
        """)
        print(f"Errors: {errors}")
        
        # Check values after submit
        values2 = await page.evaluate("""
            () => ({
                email: document.getElementById('input-4')?.value,
                url: window.location.href,
            })
        """)
        print(f"After submit: {values2}")

        await page.screenshot(path="/tmp/cox-account2.png")
        await context.close()


asyncio.run(main())

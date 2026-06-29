#!/usr/bin/env python3
"""Try Workday apply via direct URL patterns."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-workday"


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

        # Try using the en-US locale path (worked for Interac)
        await page.goto("https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(4000)
        print(f"URL: {page.url}")
        body = await page.inner_text("body")
        print(f"Body: {body[:500]}")
        
        if "Create Account" in body:
            print("\nCreating account...")
            pwd = "Cox2026!AppSecureX"
            # Type fields slowly
            await page.locator('#input-4').press_sequentially("kcao@tamu.edu", delay=30)
            await page.wait_for_timeout(200)
            await page.locator('#input-5').press_sequentially(pwd, delay=30)
            await page.wait_for_timeout(200)
            await page.locator('#input-6').press_sequentially(pwd, delay=30)
            await page.wait_for_timeout(200)
            await page.locator('#input-9').check()
            await page.wait_for_timeout(500)
            
            # Try both possible create account buttons
            await page.evaluate("""
                () => {
                    // Try dispatching mouse events for Workday buttons
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (b.innerText.includes('Create Account')) {
                            // Dispatch proper click event
                            b.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                            b.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                            b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                            return 'clicked';
                        }
                    }
                    return 'not found';
                }
            """)
            await page.wait_for_timeout(8000)
            print(f"After create: {page.url}")
            body2 = await page.inner_text("body")
            if "My Information" in body2:
                print("✅ ACCOUNT CREATED! FORM LOADED!")
                print(body2[:800])
            elif "Sign In" in body2 and "Email" in body2:
                print("Account created. Trying to sign in...")
                # Try signing in
                await page.locator('#input-4').press_sequentially("kcao@tamu.edu", delay=30)
                await page.locator('#input-5').press_sequentially(pwd, delay=30)
                await page.wait_for_timeout(500)
                await page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            if (b.innerText.trim() === 'Sign In' && b.offsetParent !== null) {
                                b.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                                b.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                                b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                                return 'clicked';
                            }
                        }
                        return 'not found';
                    }
                """)
                await page.wait_for_timeout(8000)
                print(f"After sign in: {page.url}")
                body3 = await page.inner_text("body")
                print(f"Body: {body3[:800]}")
            else:
                print(f"Unexpected state. Body: {body2[:500]}")

        await page.screenshot(path="/tmp/cox-direct-url.png")
        await context.close()


asyncio.run(main())

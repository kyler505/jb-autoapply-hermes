#!/usr/bin/env python3
"""Try Use My Last Application or Autofill with Resume on Cox Workday."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-cox3"


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

        await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply", timeout=30000)
        await page.wait_for_timeout(3000)

        # Try "Use My Last Application"
        print("Trying 'Use My Last Application'...")
        clicked = await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = b.innerText.trim();
                    if (t.includes('Use My Last') && b.offsetParent !== null) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }
        """)
        print(f"  Clicked Use My Last: {clicked}")
        await page.wait_for_timeout(5000)
        print(f"  URL: {page.url}")
        
        body = await page.inner_text("body")
        if "My Information" in body or "My Experience" in body:
            print("✅ Application form loaded via Use My Last!")

            # Simplify should auto-fill. Wait for it.
            print("Waiting for Simplify autofill...")
            await page.wait_for_timeout(5000)

            # Look for submit button
            for btn_text in ["Submit", "Review", "Save and Continue", "Continue"]:
                found = await page.evaluate(f"""() => {{
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {{
                        if (b.innerText.trim() === '{btn_text}') return true;
                    }}
                    return false;
                }}""")
                if found:
                    print(f"  '{btn_text}' button found!")
                    
            await page.screenshot(path="/tmp/cox-use-last.png")
        else:
            print(f"  Body: {body[:500]}")
            print("Use My Last didn't work. Trying Autofill with Resume...")
            
            # Try "Autofill with Resume"
            await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (b.innerText.trim().includes('Autofill with Resume') && b.offsetParent !== null) {
                            b.click();
                            return;
                        }
                    }
                }
            """)
            await page.wait_for_timeout(8000)
            print(f"  URL: {page.url}")
            body2 = await page.inner_text("body")
            print(f"  Body: {body2[:500]}")
            
            # Try creating account properly
            if "Create Account" in body2 or "Email Address" in body2:
                print("Creating account...")
                pwd = "CoxApp2026!Xy1!"
                await page.locator('#input-4').press_sequentially("kcao@tamu.edu", delay=30)
                await page.locator('#input-5').press_sequentially(pwd, delay=30)
                await page.locator('#input-6').press_sequentially(pwd, delay=30)
                await page.wait_for_timeout(300)
                await page.locator('#input-9').check()
                await page.wait_for_timeout(500)
                
                await page.evaluate("""
                    () => {
                        const btns = document.querySelectorAll('button');
                        for (const b of btns) {
                            if (b.innerText.includes('Create Account') && b.offsetParent !== null) {
                                b.click();
                                return;
                            }
                        }
                    }
                """)
                await page.wait_for_timeout(5000)
                print(f"  After create: {page.url}")
                body3 = await page.inner_text("body")
                if "My Information" in body3:
                    print("✅ Account created! Form loaded.")
                    await page.wait_for_timeout(5000)
                else:
                    print(f"  Still on: {body3[:500]}")

        await page.screenshot(path="/tmp/cox-final-result.png")
        await context.close()


asyncio.run(main())

#!/usr/bin/env python3
"""Apply to Cox Workday with Simplify profile + NopeCHA."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-filled"  # Has seeded Simplify profile data


async def click_wd(page, text):
    """Click a Workday button via JS mouse events."""
    return await page.evaluate(f"""() => {{
        const all = document.querySelectorAll('button, a, [role="button"], span, div');
        for (const el of all) {{
            if (el.innerText?.trim() === '{text}' && el.offsetParent !== null) {{
                el.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
                el.dispatchEvent(new MouseEvent('mouseup', {{ bubbles: true }}));
                el.dispatchEvent(new MouseEvent('click', {{ bubbles: true, view: window }}));
                return true;
            }}
        }}
        return false;
    }}""")


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Step 1: Login to Simplify to sync profile to extension
        print("1. Syncing Simplify profile...")
        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except: pass
        await page.locator('input[placeholder="Email Address"]').fill("kylercao18@gmail.com")
        await page.locator('input[placeholder="Password"]').fill("Monkeytype1511")
        await page.wait_for_timeout(1000)
        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(5000)
        print(f"   Simplify logged in: {'dashboard' in page.url}")

        # Step 2: Go to Cox Workday and create account
        print("2. Creating Cox Workday account...")
        await page.goto("https://cox.wd1.myworkdayjobs.com/en-US/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
        await page.wait_for_timeout(3000)
        
        pwd = "Cox2026!AppSecure"
        # Type fields slowly for Workday validation
        await page.locator('#input-4').press_sequentially("kcao@tamu.edu", delay=40)
        await page.locator('#input-5').press_sequentially(pwd, delay=40)
        await page.locator('#input-6').press_sequentially(pwd, delay=40)
        await page.wait_for_timeout(300)
        await page.locator('#input-9').check()
        await page.wait_for_timeout(500)

        # Click Create Account via proper event chain
        await click_wd(page, "Create Account")
        await page.wait_for_timeout(5000)
        print(f"   After create: {page.url}")
        body = await page.inner_text("body")

        if "My Information" in body:
            print("✅ Account created! Form loaded!")
        elif "my information" in body.lower():
            print("✅ Account created! Form loaded!")
        else:
            print(f"   State: {body[:200]}")

        # Step 3: Wait for Simplify autofill
        print("3. Waiting for Simplify to detect and fill Workday form...")
        await page.wait_for_timeout(8000)

        # Step 4: Look for submit/save buttons
        print("4. Checking for submit options...")
        body2 = await page.inner_text("body")
        for btn in ["Submit", "Save and Continue", "Continue", "Review"]:
            if btn in body2:
                print(f"   '{btn}' found on page")

        await page.screenshot(path="/tmp/cox-simplify-result.png")
        print(f"\nFinal URL: {page.url}")

        # Keep open briefly to see result
        await page.wait_for_timeout(2000)
        await context.close()


asyncio.run(main())

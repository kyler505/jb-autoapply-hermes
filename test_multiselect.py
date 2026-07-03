"""Test Workday multiselect interaction using pressSequentially."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

# Toyota URL
URL = "https://toyota.wd503.myworkdayjobs.com/tmna/job/Plano-Texas/Software-Engineer_10319691-2/apply/applyManually"
EMAIL = "kcao@tamu.edu"
PASS = "A!bc1234xyz56789"

async def main():
    async with async_playwright() as p:
        # Use same profile as pipeline
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/jb-simplify-profile",
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-gpu",
            ],
            viewport={"width": 1920, "height": 1080},
        )
        page = ctx.pages[0]

        # Navigate to apply page
        await page.goto(URL, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        print(f"[1] Page: {await page.title()} | URL: {page.url[:80]}")

        # Create account
        email_el = page.locator('[data-automation-id="email"]').first
        pw_el = page.locator('[data-automation-id="password"]').first
        vpw_el = page.locator('[data-automation-id="verifyPassword"]').first
        
        if await email_el.is_visible(timeout=2000):
            await email_el.fill(EMAIL)
            await pw_el.fill(PASS)
            if await vpw_el.is_visible():
                await vpw_el.fill(PASS)
            # Click overlay
            overlay = page.locator('[data-automation-id="click_filter"][aria-label="Create Account"]').first
            if await overlay.is_visible():
                await overlay.click(force=True)
            await page.wait_for_timeout(5000)
            print(f"[2] After create: {page.url[:80]}")

        # Handle login redirect
        if "login" in page.url.lower():
            await page.wait_for_timeout(3000)
            email_el = page.locator('[data-automation-id="email"]').first
            if await email_el.is_visible():
                await email_el.fill(EMAIL)
                await page.locator('[data-automation-id="password"]').first.fill(PASS)
                overlay = page.locator('[data-automation-id="click_filter"][aria-label="Submit"]').first
                if await overlay.is_visible():
                    await overlay.click(force=True)
                await page.wait_for_timeout(5000)
                print(f"[3] After login: {page.url[:80]}")

        # Navigate to job page and click Apply -> Apply Manually
        await page.goto("https://toyota.wd503.myworkdayjobs.com/tmna/job/Plano-Texas/Software-Engineer_10319691-2", timeout=20000)
        await page.wait_for_timeout(3000)
        
        apply_btn = page.locator('[data-automation-id="adventureButton"]').first
        if await apply_btn.is_visible():
            await apply_btn.click()
            await page.wait_for_timeout(2000)
            manual = page.locator('[data-automation-id="applyManually"]').first
            if await manual.is_visible():
                await manual.click()
                await page.wait_for_timeout(3000)
        print(f"[4] After apply: {page.url[:80]}")

        # Handle re-auth on step 1
        await page.wait_for_timeout(3000)
        email_el = page.locator('[data-automation-id="email"], input[type="email"]').first
        if await email_el.is_visible():
            await email_el.fill(EMAIL)
            await page.locator('[data-automation-id="password"], input[type="password"]').first.fill(PASS)
            overlay = page.locator('[data-automation-id="click_filter"]').first
            if await overlay.is_visible():
                await overlay.click(force=True)
            await page.wait_for_timeout(5000)
        print(f"[5] After re-auth: {page.url[:80]}")

        # Navigate to step 4-5 where multiselect appears (click Save and Continue multiple times)
        for i in range(8):
            await page.wait_for_timeout(2000)
            # Look for Save and Continue
            btn = page.locator('[data-automation-id="pageFooterNextButton"], button:has-text("Save and Continue")').first
            if await btn.is_visible():
                await btn.click(force=True)
                await page.wait_for_timeout(3000)
                print(f"[6.{i}] Clicked Save and Continue | step {i+1}")

        # Now check for multiselect — should be on step 4 or 5
        search = page.locator('#source--source').first
        if await search.is_visible(timeout=2000):
            print("=== MULTISELECT FOUND ===")
            
            # Test 1: fill() approach
            await search.click()
            await page.wait_for_timeout(300)
            await search.fill("LinkedIn")
            await page.wait_for_timeout(1500)
            opts = await page.locator('[role="option"]').count()
            print(f"  Test 1 (fill): {opts} options visible")
            
            # Dump all visible options text
            if opts > 0:
                for i in range(opts):
                    text = await page.locator('[role="option"]').nth(i).text_content()
                    print(f"    opt[{i}]: {text}")
            
            # Clear and try Test 2: pressSequentially
            await search.fill("")
            await page.wait_for_timeout(500)
            
            await search.click()
            await page.wait_for_timeout(300)
            await search.press_sequentially("LinkedIn", delay=80)
            await page.wait_for_timeout(1500)
            opts2 = await page.locator('[role="option"]').count()
            print(f"  Test 2 (pressSequentially): {opts2} options visible")
            if opts2 > 0:
                for i in range(opts2):
                    text = await page.locator('[role="option"]').nth(i).text_content()
                    print(f"    opt[{i}]: {text}")

        await ctx.close()

asyncio.run(main())
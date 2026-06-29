#!/usr/bin/env python3
"""Apply to Cox Workday with proper Workday click handling."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-filled-v2"


async def click_wd(page, text):
    """Click a Workday button by finding it in shadow DOM or regular DOM."""
    result = await page.evaluate(f"""() => {{
        // Try regular DOM
        const all = document.querySelectorAll('button, a, [role="button"], span, div');
        for (const el of all) {{
            if (el.innerText?.trim() === '{text}') {{
                el.click();
                return 'clicked: ' + '{text}';
            }}
        }}
        // Try data-automation-id
        const byAttr = document.querySelector('[data-automation-id*="{text.lower()}"], [data-automation-id*="{text}"]');
        if (byAttr) {{ byAttr.click(); return 'clicked via attr: ' + byAttr.outerHTML?.slice(0,80); }}
        return 'not found: {text}';
    }}""")
    return result


async def main():
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Navigate
        await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply", timeout=30000)
        await page.wait_for_timeout(3000)

        # Click "Apply Manually"
        print("Clicking Apply Manually...")
        result = await click_wd(page, "Apply Manually")
        print(f"  {result}")
        await page.wait_for_timeout(4000)

        # Check current state
        print(f"URL after: {page.url}")
        body = await page.inner_text("body")

        # If still on same page, try the URL directly
        if "applyManually" not in page.url and "Start Your Application" in body:
            print("Direct navigation to applyManually...")
            await page.goto("https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352/apply/applyManually", timeout=30000)
            await page.wait_for_timeout(4000)
            print(f"URL: {page.url}")

        body = await page.inner_text("body")
        print(f"Body: {body[:1000]}")

        # If Create Account visible, fill it
        if "Create Account" in body and "Email" in body:
            print("\nFilling account creation...")
            await page.locator('[data-automation-id="email"]').fill("kcao@tamu.edu")
            await page.locator('[data-automation-id="password"]').fill("CoxApp2026!Secure!")
            await page.locator('[data-automation-id="verifyPassword"]').fill("CoxApp2026!Secure!")
            await page.locator('[data-automation-id="createAccountCheckbox"]').check()
            await page.wait_for_timeout(500)
            await click_wd(page, "Create Account")
            await page.wait_for_timeout(5000)
            print(f"URL after create: {page.url}")

        # Wait for Simplify to fill
        print("\nWaiting for Simplify autofill...")
        await page.wait_for_timeout(5000)

        # Screenshot
        await page.screenshot(path="/tmp/cox-result.png")
        print(f"Final URL: {page.url}")
        body_final = await page.inner_text("body")
        print(f"Final: {body_final[:800]}")

        await context.close()


asyncio.run(main())

"""
Retry SpaceX — Greenhouse form with reCAPTCHA at submit.
Launch with NopeCHA, fill remaining fields, solve reCAPTCHA, submit.
"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from jb_autoapply import nopecha
from playwright.async_api import async_playwright

URL = "https://job-boards.greenhouse.io/spacex/jobs/8603667002"
RESUME = "/home/kyler/.hermes/.playwright-mcp/resume.pdf"

async def main():
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="/tmp/nopecha-spacex",
            headless=False,
            args=nopecha.playwright_args(),
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(URL, timeout=30000, wait_until="load")
        await page.wait_for_timeout(2000)
        print(f"Loaded: {page.url}")

        # Scroll down to check for reCAPTCHA
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)

        # Check for reCAPTCHA iframe
        recaptcha = await page.locator('iframe[src*="recaptcha"]').count()
        print(f"reCAPTCHA iframes: {recaptcha}")

        if recaptcha:
            print("Waiting for reCAPTCHA solve (up to 90s)...")
            for i in range(90):
                val = await page.evaluate("""() => {
                    const ta = document.getElementById('g-recaptcha-response');
                    return ta ? ta.value : '';
                }""")
                if val and len(val) > 10:
                    print(f"reCAPTCHA solved after {i+1}s!")
                    break
                await page.wait_for_timeout(1000)
            else:
                print("reCAPTCHA NOT solved in 60s")

        # Try to submit
        submit_btn = page.locator('input[type="submit"], button[type="submit"]').first
        if await submit_btn.count():
            await submit_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await submit_btn.click()
            await page.wait_for_timeout(5000)
            print(f"Clicked Submit. URL: {page.url}")
        else:
            print("No submit button found")

        body = await page.locator("body").inner_text()
        print(f"Result (first 1000): {body[:1000]}")
        
        success = "thank you" in body.lower() or "submitted" in body.lower() or "success" in body.lower()
        print(f"\n{'✅ SUBMITTED' if success else '❌ Still blocked'}")
        
        await context.close()
        return success

if __name__ == "__main__":
    asyncio.run(main())

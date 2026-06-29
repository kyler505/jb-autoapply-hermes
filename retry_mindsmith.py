"""
Retry Mindsmith — Dover form with CAPTCHA.
"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from jb_autoapply import nopecha
from playwright.async_api import async_playwright

RESUME = "/home/kyler/.hermes/.playwright-mcp/resume.pdf"
URL = "https://app.dover.com/apply/mindsmith/e0ca8149-6811-4de9-ba38-65a0244a2b7e"

async def main():
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="/tmp/nopecha-mindsmith",
            headless=False, args=nopecha.playwright_args(), no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(URL, timeout=30000, wait_until="load")
        await page.wait_for_timeout(2000)
        print(f"Loaded: {page.url}")

        # Dover loads the Apply button first, then form
        await page.wait_for_timeout(1000)

        # Fill core fields by input type and position
        textboxes = page.locator('input[type="text"], input:not([type])')
        count = await textboxes.count()
        print(f"Textboxes found: {count}")
        
        field_values = ["Kyler", "Cao", "kcao@tamu.edu", "https://linkedin.com/in/kylercao", "(832) 966-4150"]
        for i, val in enumerate(field_values):
            if i < count:
                await textboxes.nth(i).fill(val)
                print(f"Filled field {i}: {val.split('@')[0] if '@' in val else val}")

        # Upload resume via the file input
        file_input = page.locator('input[type="file"]').first
        if await file_input.count():
            await file_input.set_input_files(RESUME)
            await page.wait_for_timeout(1000)
            print("Resume attached")
        else:
            # Click the drag-and-drop area first
            upload_area = page.locator('button:has-text("browse computer")').first
            if await upload_area.count():
                await upload_area.click()
                await page.wait_for_timeout(1000)
                file_input = page.locator('input[type="file"]').first
                if await file_input.count():
                    await file_input.set_input_files(RESUME)
                    await page.wait_for_timeout(1000)
                    print("Resume attached via upload button")

        await page.wait_for_timeout(2000)

        # Look for reCAPTCHA
        recaptcha = await page.locator('iframe[src*="recaptcha"]').count()
        print(f"reCAPTCHA iframes: {recaptcha}")

        if recaptcha:
            for i in range(60):
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

        # Submit
        submit_btn = page.locator('button[type="submit"], button:has-text("Submit"), button:has-text("Apply")').first
        if await submit_btn.count():
            await submit_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await submit_btn.click()
            await page.wait_for_timeout(5000)
            print(f"Clicked Submit. URL: {page.url}")
        else:
            print("No submit button found")

        # Check result
        body = await page.locator("body").inner_text()
        print(f"Body (first 1000): {body[:1000]}")
        
        success = ("submitted" in body.lower() or "success" in body.lower() or 
                   "thank" in body.lower() or "we'll be in touch" in body.lower())
        form_gone = not await page.locator('input[type="email"]').count()
        print(f"Success: {success}, Form gone: {form_gone}")
        
        await context.close()
        return success

if __name__ == "__main__":
    success = asyncio.run(main())
    print(f"\n{'✅ SUCCESS' if success else '❌ FAILED'}")

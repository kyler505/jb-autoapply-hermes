"""
Retry Muru — form is embedded on the page with reCAPTCHA.
Fill fields, upload resume, let NopeCHA solve, submit.
"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from jb_autoapply import nopecha
from playwright.async_api import async_playwright

RESUME_PATH = "/home/kyler/.hermes/.playwright-mcp/resume.pdf"

async def main():
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="/tmp/nopecha-muru",
            headless=False,
            args=nopecha.playwright_args(),
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto("https://www.murumed.com/job-listings/web-software-engineer-intern", timeout=30000, wait_until="load")
        await page.wait_for_timeout(2000)
        print(f"Loaded: {page.url}")

        # Fill form
        fields = {
            "First Name": "Kyler",
            "Last Name": "Cao",
            "Phone Number": "(832) 966-4150",
            "Email Address": "kcao@tamu.edu",
        }
        for label, value in fields.items():
            el = page.locator(f'input[placeholder*="{label}" i]').first
            if not await el.count():
                el = page.get_by_role("textbox", name=label)
            if await el.count():
                await el.fill(value)
                print(f"Filled {label}")
            else:
                print(f"Could not find {label}")

        # Upload resume
        file_input = page.locator('input[type="file"]').first
        if await file_input.count():
            await file_input.set_input_files(RESUME_PATH)
            await page.wait_for_timeout(1000)
            print("Resume attached")
        else:
            print("No file input found, trying upload button...")
            upload_btn = page.locator('button:has-text("Upload File")').first
            if await upload_btn.count():
                await upload_btn.click()
                await page.wait_for_timeout(1000)
                file_input = page.locator('input[type="file"]').first
                if await file_input.count():
                    await file_input.set_input_files(RESUME_PATH)
                    await page.wait_for_timeout(1000)
                    print("Resume attached after clicking upload")

        # Wait for reCAPTCHA solve by NopeCHA
        print("Waiting for reCAPTCHA solve (up to 60s)...")
        for i in range(60):
            val = await page.evaluate("""() => {
                const ta = document.getElementById('g-recaptcha-response');
                return ta ? ta.value : '';
            }""")
            if val and len(val) > 10:
                print(f"reCAPTCHA solved after {i+1}s! Token: {val[:20]}...")
                break
            await page.wait_for_timeout(1000)
        else:
            print("reCAPTCHA NOT solved within 60s — submitting anyway")

        # Scroll to submit and click
        submit_btn = page.locator('input[type="submit"], button[type="submit"]').first
        if await submit_btn.count():
            await submit_btn.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            await submit_btn.click()
            await page.wait_for_timeout(5000)
            print(f"Clicked Submit. URL: {page.url}")

            # Check form state immediately after submit
            form_gone = await page.evaluate("""() => {
                const form = document.querySelector('form');
                return form ? getComputedStyle(form).display === 'none' : true;
            }""")
            post_text = await page.locator("body").inner_text()
            print(f"Form gone: {form_gone}")
            print(f"Has thank you: {'thank' in post_text.lower()}")
            print(f"Has success msg: {'submitted' in post_text.lower() or 'success' in post_text.lower()}")
            print(f"Post-text (first 2000): {post_text[:2000]}")
        else:
            print("No submit button found")

        result_text = await page.locator("body").inner_text()
        print(f"Result (first 1000): {result_text[:1000]}")

        # Check for success indicators
        success = False
        if "thank you" in result_text.lower() or "submitted" in result_text.lower() or "success" in result_text.lower():
            success = True

        print(f"\n{'✅ SUCCESS' if success else '❌ FAILED — check result above'}")
        await context.close()
        return success

if __name__ == "__main__":
    asyncio.run(main())

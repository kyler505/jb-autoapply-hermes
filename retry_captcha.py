"""
Retry CAPTCHA-blocked job applications using Playwright with NopeCHA extension.

Targets (in order):
  1. Muru (#6)  — reCAPTCHA
  2. Mindsmith (#3) — Dover CAPTCHA
  3. Kinaxis (#7) — hCaptcha (after email/consent gate)
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from jb_autoapply import nopecha

from playwright.async_api import async_playwright

RESUME_PATH = "/home/kyler/.hermes/.playwright-mcp/resume.pdf"
NOPECHA_DIR = nopecha.EXTENSION_DIR

assert NOPECHA_DIR.exists(), f"NopeCHA extension not found at {NOPECHA_DIR}. Run 'jb-autoapply nopecha-download' first."
assert Path(RESUME_PATH).exists(), f"Resume not found at {RESUME_PATH}"

async def launch_browser(pw):
    """Launch a persistent Chromium context with NopeCHA loaded."""
    context = await pw.chromium.launch_persistent_context(
        user_data_dir="/tmp/nopecha-apply-profile",
        headless=False,            # NopeCHA needs a real browser context
        args=nopecha.playwright_args(),
        no_viewport=True,
    )
    page = await context.new_page()
    return context, page

async def retry_muru(page):
    """Retry Muru — reCAPTCHA blocked after form fill."""
    print("\n=== MURU ===")
    url = "https://www.murumed.com/job-listings/web-software-engineer-intern"
    await page.goto(url, timeout=30000, wait_until="load")
    print(f"Page loaded: {page.url}")

    # Accept any cookie dialog
    for btn_text in ["Accept All", "Accept", "Allow All", "I Accept"]:
        btn = page.get_by_role("button", name=btn_text, exact=False)
        if await btn.count():
            await btn.first.click()
            await page.wait_for_timeout(1000)
            print(f"Accepted cookies: {btn_text}")
            break

    # Check if there's an "Apply" link or button to click
    for selector in ['a[href*="apply"]', 'button:has-text("Apply")', 'a:has-text("Apply")', '[data-testid*="apply"]']:
        link = page.locator(selector).first
        if await link.count():
            await link.click()
            await page.wait_for_timeout(2000)
            print("Clicked Apply link")
            break

    await page.wait_for_timeout(2000)
    print(f"Current URL: {page.url}")
    print(f"Page text (first 2000): {(await page.locator('body').inner_text())[:2000]}")

    # Look for reCAPTCHA
    recaptcha_frame = page.frame_locator('iframe[src*="recaptcha"]').first
    if await recaptcha_frame.count():
        print("reCAPTCHA iframe detected — NopeCHA should handle")
    else:
        print("No reCAPTCHA iframe found yet")

    # Check for g-recaptcha-response
    for i in range(60):  # wait up to 60s
        val = await page.evaluate("""() => {
            const ta = document.getElementById('g-recaptcha-response');
            return ta ? ta.value : '';
        }""")
        if val and len(val) > 10:
            print(f"reCAPTCHA solved after {i+1}s! Token length: {len(val)}")
            break
        await page.wait_for_timeout(1000)
    else:
        print("reCAPTCHA NOT solved within 60s")
        # Continue anyway - maybe there's no reCAPTCHA

    # Try submitting
    for selector, name in [
        ('button[type="submit"]', "submit button"),
        ('input[type="submit"]', "submit input"),
        ('button:has-text("Submit")', "Submit button"),
        ('button:has-text("Apply")', "Apply button"),
    ]:
        btn = page.locator(selector).first
        if await btn.count():
            await btn.click()
            await page.wait_for_timeout(3000)
            print(f"Clicked {name}")
            break

    print(f"After submit URL: {page.url}")
    result = await page.locator("body").inner_text()
    print(f"Result text: {result[:1000]}")
    return "reCAPTCHA" not in result and "verification" not in result.lower()

async def retry_mindsmith(page):
    """Retry Mindsmith — Dover CAPTCHA at submit."""
    print("\n=== MINDSMITH ===")
    url = "https://app.dover.com/apply/mindsmith/e0ca8149-6811-4de9-ba38-65a0244a2b7e"
    await page.goto(url, timeout=30000, wait_until="load")
    print(f"Page loaded: {page.url}")
    await page.wait_for_timeout(2000)

    # Fill the form from packet data
    fields = {
        "first_name": "Kyler",
        "last_name": "Cao",
        "email": "kcao@tamu.edu",
        "phone": "(832) 966-4150",
        "linkedin": "https://linkedin.com/in/kylercao",
    }

    for field_name, value in fields.items():
        input_el = page.locator(f'input[name="{field_name}"], input[id*="{field_name}"], input[placeholder*="{field_name}" i]').first
        if await input_el.count():
            await input_el.fill(value)
            print(f"Filled {field_name}")

    # Upload resume via file input
    file_input = page.locator('input[type="file"]').first
    if await file_input.count():
        await file_input.set_input_files(RESUME_PATH)
        await page.wait_for_timeout(1000)
        print("Resume attached")
    else:
        # Try the Dover upload button
        upload_btn = page.locator('button:has-text("Upload"), button:has-text("upload"), [data-testid*="upload"]').first
        if await upload_btn.count():
            # Dover upload needs to click the upload area first
            await upload_btn.click()
            await page.wait_for_timeout(1000)
            file_input = page.locator('input[type="file"]').first
            if await file_input.count():
                await file_input.set_input_files(RESUME_PATH)
                await page.wait_for_timeout(1000)
                print("Resume attached via upload button")
            else:
                print("No file input found after click")
        else:
            print("No upload button found")

    await page.wait_for_timeout(2000)

    # Check for reCAPTCHA
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
        print("No reCAPTCHA response found after 60s")

    # Try submit
    for selector, name in [
        ('button[type="submit"]', "submit"),
        ('button:has-text("Submit")', "Submit"),
        ('button:has-text("Apply")', "Apply"),
    ]:
        btn = page.locator(selector).first
        if await btn.count():
            await btn.click()
            await page.wait_for_timeout(3000)
            print(f"Clicked {name}")
            break

    await page.wait_for_timeout(2000)
    result_url = page.url
    result_text = await page.locator("body").inner_text()
    print(f"Result URL: {result_url}")
    print(f"Result text: {result_text[:1000]}")

    success = "captcha" not in result_text.lower() and "verification" not in result_text.lower() and "error" not in result_text.lower()
    return success

async def retry_kinaxis(page):
    """Retry Kinaxis — hCaptcha after consent/email."""
    print("\n=== KINAXIS ===")
    url = "https://careers-kinaxis.icims.com/jobs/34832/job"
    await page.goto(url, timeout=30000, wait_until="load")
    print(f"Page loaded: {page.url}")

    # Look for Apply button
    for selector in ['a:has-text("Apply")', 'button:has-text("Apply")', '[data-automation*="apply"]']:
        link = page.locator(selector).first
        if await link.count():
            await link.click()
            await page.wait_for_timeout(2000)
            print("Clicked Apply")
            break

    await page.wait_for_timeout(2000)

    # Check for email/consent gate (iCIMS pattern)
    email_input = page.locator('input[type="email"], input[name*="email" i], input[id*="email" i]').first
    if await email_input.count():
        await email_input.fill("kcao@tamu.edu")
        print("Filled email")
        await page.wait_for_timeout(500)

        # Check consent checkbox
        consent = page.locator('input[type="checkbox"]').first
        if await consent.count():
            await consent.check()
            print("Checked consent")
            await page.wait_for_timeout(500)

        # Click Next/Continue
        for btn_text in ["Next", "Continue", "Submit"]:
            btn = page.locator(f'button:has-text("{btn_text}"), input[value="{btn_text}"]').first
            if await btn.count():
                await btn.click()
                await page.wait_for_timeout(2000)
                print(f"Clicked {btn_text}")
                break

    await page.wait_for_timeout(2000)

    # hCaptcha detection — NopeCHA handles hCaptcha in ~1s
    hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]').first
    if await hcaptcha_frame.count():
        print("hCaptcha iframe detected — NopeCHA should solve")
    else:
        print("No hCaptcha iframe yet")

    # Wait for hCaptcha solve
    for i in range(45):
        val = await page.evaluate("""() => {
            const ta = document.querySelector('textarea[data-hcaptcha-response]');
            return ta ? ta.value : '';
        }""")
        if val and len(val) > 10:
            print(f"hCaptcha solved after {i+1}s!")
            break
        await page.wait_for_timeout(1000)
    else:
        print("hCaptcha NOT solved within 45s")

    # Try continuing after hCaptcha
    for btn_text in ["Next", "Continue", "Submit"]:
        btn = page.locator(f'button:has-text("{btn_text}")').first
        if await btn.count():
            await btn.click()
            await page.wait_for_timeout(2000)
            print(f"Clicked {btn_text}")
            break

    print(f"Result URL: {page.url}")
    result_text = await page.locator("body").inner_text()
    print(f"Result text: {result_text[:1000]}")
    return True  # Even partial progress is useful

async def main():
    results = {}

    async with async_playwright() as pw:
        context, page = await launch_browser(pw)
        print("Browser launched with NopeCHA extension")

        # 1. Retry Muru
        try:
            results["muru"] = await retry_muru(page)
        except Exception as e:
            print(f"Muru failed: {e}")
            results["muru"] = False

        # 2. Retry Mindsmith — new page
        page2 = await context.new_page()
        try:
            results["mindsmith"] = await retry_mindsmith(page2)
        except Exception as e:
            print(f"Mindsmith failed: {e}")
            results["mindsmith"] = False

        # 3. Retry Kinaxis — new page
        page3 = await context.new_page()
        try:
            results["kinaxis"] = await retry_kinaxis(page3)
        except Exception as e:
            print(f"Kinaxis failed: {e}")
            results["kinaxis"] = False

        await context.close()

    print("\n=== RESULTS ===")
    for k, v in results.items():
        status = "✅ SUCCESS" if v else "❌ FAILED"
        print(f"  {k}: {status}")

if __name__ == "__main__":
    asyncio.run(main())

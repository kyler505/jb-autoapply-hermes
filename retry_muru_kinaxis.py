"""
Retry Muru and Kinaxis with better apply/iframe handling.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
from jb_autoapply import nopecha

from playwright.async_api import async_playwright

RESUME_PATH = "/home/kyler/.hermes/.playwright-mcp/resume.pdf"

async def retry_muru(page):
    print("\n=== MURU ===")
    await page.goto("https://www.murumed.com/job-listings/web-software-engineer-intern", timeout=30000, wait_until="load")
    await page.wait_for_timeout(3000)

    # Dump full HTML looking for apply links/buttons
    html = await page.content()
    # Search for "apply" in the page
    print(f"Page title: {await page.title()}")
    print(f"URL: {page.url}")

    # Check for any link with apply, or embedded ATS URLs
    import re
    apply_links = re.findall(r'href="([^"]*apply[^"]*)"', html, re.I)
    for link in apply_links:
        print(f"Apply link found: {link}")

    lever_links = re.findall(r'href="([^"]*lever[^"]*)"', html, re.I)
    for link in lever_links:
        print(f"Lever link: {link}")

    greenhouse_links = re.findall(r'href="([^"]*greenhouse[^"]*)"', html, re.I)
    for link in greenhouse_links:
        print(f"Greenhouse link: {link}")

    # Also look for data attributes, onclick handlers with apply
    data_apply = re.findall(r'data-[^=]*="[^"]*apply[^"]*"', html, re.I)
    for d in data_apply[:5]:
        print(f"Data apply attr: {d}")

    # Try clicking everything that looks like an apply button
    for sel in [
        '[data-apply]',
        '[data-action="apply"]',
        '[data-testid*="apply" i]',
        'a[href*="career" i]',
        'a[href*="job" i]',
        'a[href*="position" i]',
        'button, a',
    ]:
        els = await page.locator(sel).all()
        for el in els:
            text = (await el.inner_text()).strip().lower()
            if text in ["apply", "apply now", "apply for this job", "apply here"]:
                print(f"Found element with text '{text}' via selector '{sel}'")
                await el.click()
                await page.wait_for_timeout(3000)
                print(f"After click URL: {page.url}")
                break
        else:
            continue
        break
    else:
        print("No apply found from common selectors")

    await page.wait_for_timeout(2000)
    print(f"Final URL: {page.url}")
    return True

async def retry_kinaxis(page):
    print("\n=== KINAXIS ===")
    await page.goto("https://careers-kinaxis.icims.com/jobs/34832/job", timeout=30000, wait_until="load")
    await page.wait_for_timeout(3000)

    # The job is inside an iframe — get the iframe source
    src = await page.locator('iframe').first.get_attribute('src')
    print(f"Iframe src: {src}")

    if src:
        # Navigate to the iframe's URL directly
        await page.goto(src, timeout=30000, wait_until="load")
        await page.wait_for_timeout(2000)
        print(f"Direct URL: {page.url}")

    # Now look for apply
    for sel in [
        'a:has-text("Apply")',
        'button:has-text("Apply")',
        '[class*="apply"]',
        'a[href*="apply"]',
        'input[value*="Apply"]',
        'button[type="submit"]',
    ]:
        els = page.locator(sel)
        cnt = await els.count()
        if cnt:
            print(f"Found '{sel}': {cnt} — clicking first")
            await els.first.click()
            await page.wait_for_timeout(3000)
            print(f"After click: {page.url}")
            break

    await page.wait_for_timeout(2000)
    print(f"URL: {page.url}")

    # Fill email if present
    email_input = page.locator('input[type="email"]').first
    if await email_input.count():
        await email_input.fill("kcao@tamu.edu")
        print("Filled email")

    # Check consent boxes
    chk = page.locator('input[type="checkbox"]').first
    if await chk.count():
        await chk.check()
        print("Checked consent")

    # Click Next
    for btn_text in ["Next", "Continue"]:
        btn = page.locator(f'button:has-text("{btn_text}")').first
        if await btn.count():
            await btn.click()
            await page.wait_for_timeout(2000)
            print(f"Clicked {btn_text}")

    await page.wait_for_timeout(2000)
    print(f"Final URL: {page.url}")

    # Check hCaptcha
    hc = await page.locator('iframe[src*="hcaptcha"]').count()
    print(f"hCaptcha iframes: {hc}")

    for i in range(60):
        val = await page.evaluate("""() => {
            const ta = document.querySelector('textarea[data-hcaptcha-response]');
            return ta ? ta.value : '';
        }""")
        if val and len(val) > 10:
            print(f"hCaptcha solved after {i+1}s!")
            break
        await page.wait_for_timeout(1000)
    else:
        print("hCaptcha NOT solved in 60s")

    print(f"Body: {(await page.locator('body').inner_text())[:500]}")
    return True

async def main():
    results = {}
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="/tmp/nopecha-apply-v3",
            headless=False,
            args=nopecha.playwright_args(),
            no_viewport=True,
        )

        p1 = await context.new_page()
        try:
            results["muru"] = await retry_muru(p1)
        except Exception as e:
            import traceback; traceback.print_exc()
            results["muru"] = False

        p2 = await context.new_page()
        try:
            results["kinaxis"] = await retry_kinaxis(p2)
        except Exception as e:
            import traceback; traceback.print_exc()
            results["kinaxis"] = False

        await context.close()

    print("\n=== RESULTS ===")
    for k, v in results.items():
        print(f"  {k}: {'✅' if v else '❌'}")

if __name__ == "__main__":
    asyncio.run(main())

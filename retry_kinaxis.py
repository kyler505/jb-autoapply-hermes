"""
Retry Kinaxis — iCIMS job in iframe. Try mobile URL for simpler flow.
"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from jb_autoapply import nopecha
from playwright.async_api import async_playwright

URL = "https://careers-kinaxis.icims.com/jobs/34832/job?mobile=true&needsRedirect=false"

async def main():
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir="/tmp/nopecha-kinaxis",
            headless=False,
            args=nopecha.playwright_args(),
            no_viewport=True,
        )
        page = await context.new_page()
        await page.goto(URL, timeout=30000, wait_until="load")
        await page.wait_for_timeout(3000)
        print(f"Loaded: {page.url}")
        print(f"Title: {await page.title()}")

        # Dump page source looking for apply elements
        html = await page.content()
        import re
        apply_links = re.findall(r'href="([^"]*apply[^"]*)"', html, re.I)
        for l in apply_links:
            print(f"Apply href: {l}")

        # Try to find Apply in any iframe
        iframes = page.locator("iframe")
        cnt = await iframes.count()
        print(f"Iframes: {cnt}")
        
        for i in range(cnt):
            ifr = iframes.nth(i)
            src = await ifr.get_attribute("src")
            name = await ifr.get_attribute("name") or ""
            print(f"  [{i}] src='{src}' name='{name}'")
            
            # Check if the page loaded the full iCIMS apply page directly (mobile URL)
        body_text = await page.locator("body").inner_text()
        print(f"Body (first 1000): {body_text[:1000]}")
        
        # Look for Apply button
        for sel in [
            'a:has-text("Apply")', 'button:has-text("Apply")', 
            'input[value*="Apply"]', '[class*="apply"]',
            'a[href*="apply"]', '[data-automation*="apply"]',
        ]:
            el = page.locator(sel).first
            if await el.count() and await el.is_visible():
                print(f"Found '{sel}'")
                await el.click()
                await page.wait_for_timeout(3000)
                print(f"After click: {page.url}")
                break
        else:
            print("No Apply button found on main page")
        
        # Check if frames have the apply flow
        for frame in page.frames:
            try:
                ft = await frame.locator("body").inner_text(timeout=3000)
                print(f"\nFrame '{frame.name}': {ft[:200]}")
                if "apply" in ft.lower():
                    print("  → Has apply text!")
                    # Look for apply link
                    apply = frame.locator('a:has-text("Apply")').first
                    if await apply.count():
                        await apply.click()
                        await page.wait_for_timeout(3000)
                        print("  → Clicked Apply in frame")
                        break
            except:
                pass
        
        # Fill email if we got to gate
        email_input = page.locator('input[type="email"]').first
        if await email_input.count():
            await email_input.fill("kcao@tamu.edu")
            print("Filled email")
            chk = page.locator('input[type="checkbox"]').first
            if await chk.count():
                await chk.check()
                print("Checked consent")
            for btn_text in ["Next", "Continue"]:
                btn = page.locator(f'button:has-text("{btn_text}")').first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(3000)
                    print(f"Clicked {btn_text} — new URL: {page.url}")
                    break
        
        await page.wait_for_timeout(2000)
        print(f"\nAfter gate URL: {page.url}")
        
        # hCaptcha detection
        hc = await page.locator('iframe[src*="hcaptcha"]').count()
        print(f"hCaptcha iframes: {hc}")
        
        # Also check for hCaptcha inside the page DOM
        hc_textarea = await page.evaluate("""() => {
            const ta = document.querySelector('textarea[data-hcaptcha-response]');
            return ta ? 'found textarea' : 'no textarea';
        }""")
        print(f"hCaptcha textarea: {hc_textarea}")
        
        if hc:
            print("Waiting for hCaptcha solve (up to 60s)...")
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
                # Try clicking the hCaptcha checkbox
                hcaptcha_checkbox = page.locator('iframe[src*="hcaptcha"]').first
                print("hCaptcha still present — may need manual solve")
        else:
            print("No hCaptcha found — may already be past it")
        
        # Try to proceed after hCaptcha
        for btn_text in ["Next", "Continue", "Submit Application", "Submit"]:
            btn = page.locator(f'button:has-text("{btn_text}")').first
            if await btn.count() and await btn.is_visible():
                await btn.click()
                await page.wait_for_timeout(3000)
                print(f"Clicked {btn_text} — URL: {page.url}")
        
        print(f"\nFinal: {page.url}")
        print(f"Final body: {(await page.locator('body').inner_text())[:500]}")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

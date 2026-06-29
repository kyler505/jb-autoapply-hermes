#!/usr/bin/env python3
"""Run the queue with Simplify + NopeCHA + account store."""
import asyncio, os, shutil, json, sys
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-run"
RESUME = "/home/kyler/.hermes/.playwright-mcp/uploads/resume_har.pdf"

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accounts
from jb_autoapply.selector import build_queue


async def apply_workday(page, job, acct):
    """Apply to a Workday job using stored credentials."""
    url = job["url"]
    domain = _accounts.tenant_domain(url)
    company = job["company"]
    role = job["role"]
    
    print(f"\n{'='*60}")
    print(f"Applying: {company} — {role}")
    print(f"  URL: {url}")
    print(f"  Account: {acct['email']} ({domain})")
    
    # Navigate to apply page
    apply_url = url.rstrip("/") + "/apply/applyManually"
    await page.goto(apply_url, timeout=30000)
    await page.wait_for_timeout(3000)
    
    body = await page.inner_text("body")
    
    if "Sign In" in body and "Email" in body:
        print("  → Signing in with stored credentials...")
        try:
            await page.locator('input[data-automation-id="email"]').fill(acct["email"])
            await page.locator('input[data-automation-id="password"]').fill(acct["password"])
            await page.wait_for_timeout(500)
            # Click Sign In
            await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (b.innerText.trim() === 'Sign In' && b.offsetParent !== null) {
                            b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                            return;
                        }
                    }
                }
            """)
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  ⚠ Sign-in failed: {e}")
    elif "Create Account" in body:
        print("  → No stored account. Creating...")
        pwd = _accounts.generate_password()
        try:
            await page.locator('input[data-automation-id="email"]').fill(acct["email"])
            await page.locator('input[data-automation-id="password"]').fill(pwd)
            await page.locator('input[data-automation-id="verifyPassword"]').fill(pwd)
            await page.locator('input[data-automation-id="createAccountCheckbox"]').check()
            await page.wait_for_timeout(500)
            await page.evaluate("""
                () => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (b.innerText.includes('Create Account')) {
                            b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                            return;
                        }
                    }
                }
            """)
            await page.wait_for_timeout(5000)
            # Save account
            if domain:
                _accounts.save_account(domain, acct["email"], pwd)
            print(f"  ✅ Account created and saved")
        except Exception as e:
            print(f"  ⚠ Account creation error: {e}")
    
    # Wait for Simplify to detect and fill
    print("  → Waiting for Simplify autofill...")
    await page.wait_for_timeout(8000)
    
    body2 = await page.inner_text("body")
    
    if "Submit" in body2:
        print("  → Submit button found!")
        await page.evaluate("""
            () => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.innerText.includes('Submit') && b.offsetParent !== null) {
                        b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                        return;
                    }
                }
            }
        """)
        await page.wait_for_timeout(5000)
        body3 = await page.inner_text("body")
        if "thank you" in body3.lower() or "submitted" in body3.lower():
            return "SUBMITTED"
        else:
            return f"CLICKED_SUBMIT: {page.url}"
    else:
        return f"NO_SUBMIT_BUTTON: {body2[:200]}"


async def main():
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    # Load queue
    queue = build_queue()
    print(f"Queue has {len(queue)} jobs")
    
    # Filter to Workday jobs with stored accounts
    targets = []
    for job in queue:
        url = job.get("url", "")
        if _accounts.tenant_domain(url) and _accounts.has_account(url):
            domain = _accounts.tenant_domain(url)
            if not domain:
                continue
            acct = _accounts.get_account(domain)
            targets.append((job, acct))
    
    print(f"Jobs with stored accounts: {len(targets)}")
    for job, acct in targets:
        print(f"  • {job['company']:25s} — {acct['email']} ({_accounts.tenant_domain(job['url'])})")
    
    if not targets:
        print("No jobs with stored accounts. Nothing to apply to.")
        return
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
            slow_mo=200,
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Login to Simplify
        print("\n1. Syncing Simplify profile...")
        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except: pass
        await page.wait_for_timeout(500)
        await page.locator('#email, input[placeholder="Email Address"]').first.fill("kylercao18@gmail.com")
        await page.locator('#password, input[placeholder="Password"]').first.fill("Monkeytype1511")
        await page.wait_for_timeout(500)
        await page.locator('button[type="submit"]').first.click()
        await page.wait_for_timeout(5000)
        print(f"   Simplify logged in: {'dashboard' in page.url}")
        
        # Apply to each target
        results = []
        for job, acct in targets:
            result = await apply_workday(page, job, acct)
            results.append((job["company"], result))
            print(f"  Result: {result}")
        
        # Summary
        print(f"\n{'='*60}")
        print("RESULTS:")
        for company, result in results:
            print(f"  {company:25s}: {result}")
        
        await context.close()


asyncio.run(main())

#!/usr/bin/env python3
"""Complete the remaining password resets."""
import asyncio, os, shutil, sys
from pathlib import Path
from playwright.async_api import async_playwright
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64, re, time

sys.path.insert(0, "src")
from jb_autoapply import accounts as _a

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
creds = Credentials.from_authorized_user_file(str(Path.home() / ".hermes" / "google_token_work.json"))
gmail = build("gmail", "v1", credentials=creds)


def find_latest_reset(domain_filter):
    """Find the most recent unused reset link for a domain."""
    results = gmail.users().messages().list(userId="me", q="from:otp.workday.com reset newer_than:1d", maxResults=10).execute()
    for msg in results.get("messages", []):
        data = gmail.users().messages().get(userId="me", id=msg["id"]).execute()
        hdrs = {h["name"]: h["value"] for h in data["payload"]["headers"]}
        sender = hdrs.get("From", "")
        if domain_filter not in sender:
            continue
        
        def extract(p):
            m = p.get("mimeType", "")
            if m in ("text/plain", "text/html"):
                b64 = p.get("body", {}).get("data", "")
                if b64:
                    return base64.urlsafe_b64decode(b64).decode("utf-8", errors="replace")
            if p.get("parts"):
                return "".join(extract(s) for s in p["parts"])
            return ""
        
        body = extract(data["payload"])
        urls = re.findall(r'https?://[^\s"<>]+', body)
        for u in urls:
            if "passwordreset" in u.lower():
                return u
    return None


async def reset_password(page, name, link, domain):
    """Open a reset link and set a new password."""
    print(f"\n=== {name} ===")
    await page.goto(link, timeout=30000)
    await page.wait_for_timeout(3000)
    print(f"  URL: {page.url[:80]}")
    
    new_pwd = _a.generate_password()
    pwds = page.locator('input[type="password"]')
    c = await pwds.count()
    print(f"  Password fields: {c}")
    
    if c >= 2:
        await pwds.nth(0).fill(new_pwd)
        await pwds.nth(1).fill(new_pwd)
        await page.wait_for_timeout(500)
        
        # Click Submit via click_filter
        btn = page.get_by_role("button", name="Submit")
        if await btn.count() > 0:
            await btn.first.click()
            await page.wait_for_timeout(5000)
            print(f"  After: {page.url[:80]}")
            _a.save_account(domain, "kcao@tamu.edu", new_pwd)
            print(f"  ✅ Password saved!")
            return True
        else:
            print("  ❌ No Submit button")
    else:
        print(f"  Page state: {(await page.inner_text('body'))[:200]}")
    
    return False


async def trigger_reset(page, url):
    """Trigger a forgot-password email."""
    await page.goto(url, timeout=30000)
    await page.wait_for_timeout(3000)
    
    fp = page.locator('[data-automation-id="forgotPasswordLink"]')
    if await fp.is_visible(timeout=3000):
        await fp.click()
        await page.wait_for_timeout(2000)
    
    ei = page.locator('[data-automation-id="email"]')
    if await ei.is_visible(timeout=3000):
        await ei.fill("kcao@tamu.edu")
        await page.wait_for_timeout(500)
    
    rp = page.get_by_role("button", name="Reset Password")
    if await rp.count() > 0:
        await rp.first.click()
        await page.wait_for_timeout(3000)
        return True
    return False


async def main():
    p = "/tmp/wd-reset-final"
    if os.path.exists(p): shutil.rmtree(p)
    
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(user_data_dir=p, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        # 1. Try Sentry - existing link might still work
        sentry_link = find_latest_reset("sentryinsurance")
        print(f"Sentry link found: {bool(sentry_link)}")
        if sentry_link:
            await reset_password(page, "Sentry", sentry_link, "sentryinsurance.wd1.myworkdayjobs.com")
        else:
            # Trigger new reset for Sentry
            sentry_url = "https://sentryinsurance.wd1.myworkdayjobs.com/en-US/SentryCareers/job/Stevens-Point-WI/Software-Developer--Hybrid-Work-Model-_JR-142351/apply/applyManually"
            print("Triggering new Sentry reset email...")
            if await trigger_reset(page, sentry_url):
                print("  Waiting for email...")
                time.sleep(15)
                sentry_link = find_latest_reset("sentryinsurance")
                if sentry_link:
                    await reset_password(page, "Sentry", sentry_link, "sentryinsurance.wd1.myworkdayjobs.com")
        
        # 2. Try the other Cox link
        cox_link = find_latest_reset("cox")
        print(f"\nCox link found: {bool(cox_link)}")
        if cox_link:
            await reset_password(page, "Cox", cox_link, "cox.wd1.myworkdayjobs.com")
        
        await ctx.close()
    
    print(f"\n{'='*60}")
    print("Accounts:")
    for d, i in _a.list_accounts().items():
        print(f"  {d:40s} {i['email']:25s} {i['password']}")
    
    # Now test the pipeline
    print(f"\n{'='*60}")
    print("Testing queue with new accounts...")
    os.system("DISPLAY=:99 timeout 60 .venv/bin/python run_queue.py 2>&1 | head -30")

asyncio.run(main())

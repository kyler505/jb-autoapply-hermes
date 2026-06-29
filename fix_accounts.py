#!/usr/bin/env python3
"""Fix Workday accounts: forgot password -> poll Gmail -> set new password -> save."""
import asyncio, os, sys, re, base64, json, time
from pathlib import Path
from playwright.async_api import async_playwright
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _a

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/wd-fix"
TOKEN_PATH = Path.home() / ".hermes" / "google_token_work.json"


def get_gmail():
    """Get Gmail API client using stored OAuth token."""
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    return build("gmail", "v1", credentials=creds)


def wait_for_reset_email(gmail, timeout=120):
    """Poll Gmail for a password reset email. Returns (reset_link, sender)."""
    query = "(password reset OR reset your password OR forgot password) newer_than:1d"
    deadline = time.time() + timeout
    while time.time() < deadline:
        results = gmail.users().messages().list(userId="me", q=query, maxResults=5).execute()
        for msg in results.get("messages", []):
            data = gmail.users().messages().get(userId="me", id=msg["id"]).execute()
            hdrs = {h["name"]: h["value"] for h in data["payload"]["headers"]}
            subject = hdrs.get("Subject", "")
            sender = hdrs.get("From", "")
            if "reset" not in subject.lower() and "password" not in subject.lower():
                continue
            
            # Get body
            body_text = ""
            parts = data["payload"].get("parts", [])
            for part in parts:
                b64 = part.get("body", {}).get("data", "")
                if b64:
                    body_text += base64.urlsafe_b64decode(b64).decode("utf-8", errors="replace")
            
            urls = re.findall(r'https?://[^\s"<>]+', body_text)
            for u in urls:
                if "reset" in u.lower() or "password" in u.lower():
                    return u, sender
        time.sleep(5)
    return None, None


async def fix_account(page, gmail, company, domain, url, email):
    """Fix a Workday account via forgot-password flow."""
    print(f"\n{'='*60}")
    print(f"Fixing: {company}")
    
    apply_url = url.rstrip("/") + "/apply/applyManually"
    await page.goto(apply_url, timeout=30000)
    await page.wait_for_timeout(3000)
    
    # Click Forgot Password
    fp = page.locator('[data-automation-id="forgotPasswordLink"]')
    if await fp.is_visible(timeout=3000):
        await fp.click()
        await page.wait_for_timeout(2000)
    
    # Fill email
    email_input = page.locator('[data-automation-id="email"]')
    if await email_input.is_visible(timeout=3000):
        await email_input.fill(email)
        await page.wait_for_timeout(500)
    
    # Click Reset Password
    rp = page.get_by_role("button", name="Reset Password")
    if await rp.count() > 0:
        await rp.first.click()
        print("  → Reset requested. Waiting for email...")
        await page.wait_for_timeout(3000)
    
    # Poll Gmail for reset link
    link, sender = wait_for_reset_email(gmail, timeout=90)
    if not link:
        print("  ❌ No reset email received")
        return False
    
    print(f"  → Got reset link: {link[:80]}...")
    
    # Navigate to reset link
    await page.goto(link, timeout=30000)
    await page.wait_for_timeout(3000)
    
    # Set new password
    new_pwd = _a.generate_password()
    try:
        await page.locator('#input-5').fill(new_pwd)  # New password
        await page.locator('#input-6').fill(new_pwd)  # Confirm
        await page.wait_for_timeout(500)
        reset_btn = page.get_by_role("button", name="Reset", exact=False)
        if await reset_btn.count() > 0:
            await reset_btn.first.click()
            await page.wait_for_timeout(5000)
            print("  → Password reset submitted")
    except Exception as e:
        print(f"  ⚠ Reset form fill error: {e}")
        return False
    
    # Save to accounts store
    _a.save_account(domain, email, new_pwd)
    print(f"  ✅ Password saved for {company}")
    return True


async def main():
    if os.path.exists(PROFILE):
        import shutil; shutil.rmtree(PROFILE)
    
    gmail = get_gmail()
    print("Gmail connected")
    
    targets = [
        ("Cox", "cox.wd1.myworkdayjobs.com",
         "https://cox.wd1.myworkdayjobs.com/Cox_External_Career_Site_1/job/Atlanta-GA/Software-Engineer-I_R202679352"),
        ("KLA", "kla.wd1.myworkdayjobs.com",
         "https://kla.wd1.myworkdayjobs.com/Search/job/Milpitas-CA/Sr-Software-Engineer_2638120"),
        ("Sentry Insurance", "sentryinsurance.wd1.myworkdayjobs.com",
         "https://sentryinsurance.wd1.myworkdayjobs.com/en-US/SentryCareers/job/Stevens-Point-WI/Software-Developer--Hybrid-Work-Model-_JR-142351"),
    ]
    
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        for company, domain, url in targets:
            await fix_account(page, gmail, company, domain, url, "kcao@tamu.edu")
        
        await ctx.close()
    
    print(f"\n{'='*60}")
    print("Updated accounts:")
    for d, i in _a.list_accounts().items():
        print(f"  {d:40s} {i['email']:25s} {i['password']}")


if __name__ == "__main__":
    asyncio.run(main())

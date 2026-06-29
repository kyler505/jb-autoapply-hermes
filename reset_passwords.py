#!/usr/bin/env python3
"""Step 2: Poll Gmail for reset links and set new passwords."""
import asyncio, base64, re, time, sys
from pathlib import Path
from playwright.async_api import async_playwright
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _a

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")

creds = Credentials.from_authorized_user_file(str(Path.home() / ".hermes" / "google_token_work.json"))
gmail = build("gmail", "v1", credentials=creds)

# Find reset links in Gmail
print("Polling Gmail for reset links...")
results = gmail.users().messages().list(userId="me", q="reset password newer_than:1d", maxResults=10).execute()
print(f"Messages found: {len(results.get('messages', []))}")

reset_links = {}
for msg in results.get("messages", []):
    data = gmail.users().messages().get(userId="me", id=msg["id"]).execute()
    hdrs = {h["name"]: h["value"] for h in data["payload"]["headers"]}
    subject = hdrs.get("Subject", "")
    sender = hdrs.get("From", "")
    print(f"\n  Subject: {subject}")
    print(f"  From: {sender}")
    
    # Get body - handle different MIME structures
    body = ""
    def extract_text(part):
        mime = part.get("mimeType", "")
        if mime == "text/plain" or mime == "text/html":
            b64 = part.get("body", {}).get("data", "")
            if b64:
                return base64.urlsafe_b64decode(b64).decode("utf-8", errors="replace")
        if part.get("parts"):
            result = ""
            for sub in part["parts"]:
                result += extract_text(sub)
            return result
        return ""
    
    body = extract_text(data["payload"])
    print(f"  Body length: {len(body)} chars")
    
    urls = re.findall(r'https?://[^\s"<>]+', body)
    print(f"  URLs found: {len(urls)}")
    for u in urls[:5]:
        print(f"    {u[:100]}")
    for u in urls:
        if "reset" in u.lower() or "password" in u.lower():
            print(f"  Reset link: {u[:100]}")
            if "cox" in sender.lower():
                reset_links["Cox"] = u
            elif "sentry" in sender.lower():
                reset_links["Sentry"] = u
            else:
                reset_links[sender.split("@")[0].title()] = u

print(f"\nFound {len(reset_links)} reset links")
for k, v in reset_links.items():
    print(f"  {k}: {v[:80]}")

if not reset_links:
    print("No reset links found yet. They may take a moment to arrive.")
    sys.exit(1)

# Now open each link and set new password
async def main():
    import shutil, os
    p = "/tmp/wd-reset-pwd"
    if os.path.exists(p): shutil.rmtree(p)
    
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(user_data_dir=p, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        domains = {
            "Cox": "cox.wd1.myworkdayjobs.com",
            "Sentry": "sentryinsurance.wd1.myworkdayjobs.com",
        }
        
        for name, link in reset_links.items():
            domain = domains.get(name)
            if not domain:
                print(f"\n⚠ Unknown domain for {name}")
                continue
            
            print(f"\n=== {name} ===")
            await page.goto(link, timeout=30000)
            await page.wait_for_timeout(3000)
            print(f"  URL: {page.url[:80]}")
            
            new_pwd = _a.generate_password()
            
            # Fill new password fields
            try:
                pwds = page.locator('input[type="password"]')
                c = await pwds.count()
                if c >= 2:
                    await pwds.nth(0).fill(new_pwd)
                    await pwds.nth(1).fill(new_pwd)
                    await page.wait_for_timeout(500)
                    print(f"  Password fields filled ({c} found)")
                    
                    # Click submit/reset button (Workday uses "Submit" text)
                    btn = page.get_by_role("button", name="Submit")
                    if await btn.count() > 0:
                        await btn.first.click()
                        await page.wait_for_timeout(5000)
                        print(f"  After reset: {page.url[:80]}")
                        
                        _a.save_account(domain, "kcao@tamu.edu", new_pwd)
                        print(f"  ✅ Password saved for {name}")
                    else:
                        print("  ❌ No Reset button found")
                else:
                    print(f"  ⚠ Only {c} password fields found")
                    body = await page.inner_text("body")
                    print(f"  Body: {body[:300]}")
            except Exception as e:
                print(f"  ❌ Error: {e}")
        
        await ctx.close()

asyncio.run(main())

print(f"\n{'='*60}")
print("Updated accounts:")
for d, i in _a.list_accounts().items():
    print(f"  {d:40s} {i['password']}")

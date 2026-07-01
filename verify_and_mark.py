#!/usr/bin/env python3
"""Verify which jobs were actually submitted by checking their pages."""
import asyncio, os, shutil, sys
from pathlib import Path
from datetime import datetime

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-verify"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accounts
from jb_autoapply.selector import build_queue
from jb_autoapply.vault import update_fields
from playwright.async_api import async_playwright

SUBMITTED_JOBS = [
    ("Mindsmith", "https://app.dover.com/apply/mindsmith/e0ca8149-6811-4de9-ba38-65a0244a2b7e"),
    ("Rivian/VW", "https://jobs.ashbyhq.com/rivianvw.tech/89feb2fe-c28c-4dad-846f-09594632ba55"),
    ("Sandhills Global", "https://www.sandhills.com/careers-and-internships/details/careers/sandhills/1196/software-development-intern"),
    ("Muru", "https://www.murumed.com/job-listings/web-software-engineer-intern"),
    ("Kinaxis (DF)", "https://careers-kinaxis.icims.com/jobs/34832/job?mobile=true&needsRedirect=false"),
    ("Corning", "https://corningjobs.corning.com/job/Corning-Software-Engineer-(CMMS-Systems)-NY-14831/1403127800/?ats=successfactors"),
    ("Four Hands", "https://job-boards.greenhouse.io/fourhands/jobs/4297618009"),
    ("Delta Air Lines", "https://delta.avature.net/en_US/careers/JobDetail?jobId=32774"),
    ("Microsoft", "https://apply.careers.microsoft.com/careers/job/1970393556899565"),
    ("SpaceX", "https://boards.greenhouse.io/spacex/jobs/8603667002"),
    ("1Password", "https://jobs.ashbyhq.com/1password/b6b8c8ed-ff1c-4bc2-9dbe-5122207ea3a2/application"),
    ("Kinaxis (CA)", "https://careers-kinaxis.icims.com/jobs/34962/job?mobile=true&needsRedirect=false"),
    ("DAT Freight", "https://careers.dat.com/jobs/6099144004?gh_jid=6099144004"),
    # Workday
    ("Boeing", "https://boeing.wd1.myworkdayjobs.com/external_subsidiary/job/USA---Hazelwood-MO/Software-Engineer-Simulation--Simulation-_JR2026510876-1"),
]

async def check_submitted(page, name, url):
    print(f"\n{'='*60}\n{name}")
    print(f"  {url[:80]}")
    
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)
        
        body = await page.inner_text("body")
        body_lower = body.lower()
        
        # Confirmation keywords
        confirmed = any(w in body_lower for w in [
            "thank you", "submitted", "application has been submitted",
            "your application", "application received", "we've received",
            "successfully submitted", "application complete"
        ])
        
        # Also check for "Applied" button text (Greenhouse, etc.)
        applied_btn = False
        try:
            btn = page.get_by_role("button", name="Applied", exact=False)
            if await btn.count() > 0:
                applied_btn = True
        except: pass
        
        # Check URL for confirmation patterns
        url_confirmed = any(p in page.url.lower() for p in [
            "submitted", "confirmation", "thank-you", "application-complete"
        ])
        
        is_submitted = confirmed or applied_btn or url_confirmed
        
        if is_submitted:
            print(f"  ✅ CONFIRMED SUBMITTED")
            if confirmed: print(f"     (confirmation text on page)")
            if applied_btn: print(f"     (button shows 'Applied')")
            if url_confirmed: print(f"     (URL: {page.url[:60]})")
        else:
            # Show what's on the page
            print(f"  ❌ NOT CONFIRMED")
            print(f"  URL: {page.url[:80]}")
            # Show relevant text snippets
            for snippet in ["apply", "submit", "sign in", "welcome", "job", "position"]:
                if snippet in body_lower:
                    lines = [l.strip() for l in body.split('\n') if snippet in l.lower()]
                    for l in lines[:2]:
                        if l: print(f"     ...{l[:80]}...")
                    break
        
        return is_submitted
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        results = []
        for name, url in SUBMITTED_JOBS:
            result = await check_submitted(page, name, url)
            results.append((name, result))
        
        print(f"\n{'='*60}")
        print("VERIFICATION RESULTS:")
        confirmed = [n for n, r in results if r]
        not_confirmed = [n for n, r in results if not r]
        
        for n, r in results:
            icon = "✅" if r else "❌"
            print(f"  {icon} {n:25s}: {'CONFIRMED' if r else 'NOT CONFIRMED'}")
        
        print(f"\nConfirmed: {len(confirmed)}/{len(results)}")
        
        # Mark confirmed jobs in vault
        if confirmed:
            print(f"\nMarking confirmed jobs as 'applied' in vault...")
            
            # Build lookup from queue
            queue = build_queue(write_priority=False)
            for job in queue:
                company = job.get("company", "")
                for name in confirmed:
                    if company.lower() in name.lower() or name.lower() in company.lower():
                        path = Path(job["path"])
                        update_fields(path, {"status": "applied", "date_applied": datetime.now().strftime("%Y-%m-%d")})
                        print(f"  ✅ Marked {company} as applied")
                        break
        
        await ctx.close()

asyncio.run(main())

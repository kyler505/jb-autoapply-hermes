#!/usr/bin/env python3
"""Run Workday pipeline with form filler for fields Simplify misses."""
import asyncio, os, shutil, sys
from pathlib import Path
SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/autoapply-run"
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import accounts as _accounts
from jb_autoapply.selector import build_queue

# Profile data for filling fields Simplify misses
APP_PROFILE = {
    "first_name": "Kyler", "last_name": "Cao",
    "email": "kcao@tamu.edu", "phone": "18329664150",
    "street": "9810 Orchid Cove Court",
    "city": "Cypress", "state": "TX", "zip": "77433",
    "how_heard": "LinkedIn",
}

# Workday field ID → profile value mappings
FIELD_MAP = {
    "source--source": "LinkedIn",
    "name--legalName--firstName": "Kyler",
    "name--legalName--lastName": "Cao",
    "address--addressLine1": "9810 Orchid Cove Court",
    "address--city": "Cypress",
    "address--state": "TX",
    "address--postalCode": "77433",
    "phoneNumber--phoneNumber": "18329664150",
    "phoneNumber--countryPhoneCode": "United States of America (+1)",
}


async def click_wd(page, text):
    aids = {"Create Account": "createAccountSubmitButton", "Sign In": "signInSubmitButton"}
    if text in aids:
        try:
            b = page.locator(f'[data-automation-id="{aids[text]}"]')
            if await b.is_visible(timeout=1000): await b.click(force=True); return True
        except: pass
    try:
        btn = page.get_by_role("button", name=text)
        if await btn.count() > 0: await btn.first.click(); return True
    except: pass
    return False


async def has_wd(page, text):
    try: return await page.get_by_role("button", name=text).count() > 0
    except: return False


async def fill_missing(page):
    """Fill unfilled Workday fields from FIELD_MAP."""
    filled = 0
    for field_id, value in FIELD_MAP.items():
        try:
            el = page.locator(f'#{field_id}')
            if await el.is_visible(timeout=200):
                tag = await el.evaluate("el => el.tagName")
                placeholder = (await el.get_attribute("placeholder")) or ""
                current = await el.input_value()
                if current and current.strip(): continue

                if "Search" in placeholder:
                    # Workday autocomplete - type and select
                    await el.fill(value)
                    await page.wait_for_timeout(700)
                    opt = page.locator('[role="option"]').first
                    if await opt.is_visible(timeout=1500):
                        await opt.click()
                        await page.wait_for_timeout(400)
                        filled += 1
                elif tag == "SELECT":
                    try:
                        await el.select_option(value)
                    except:
                        opts = await el.evaluate("el => Array.from(el.options).map(o => o.text)")
                        for opt in opts:
                            if value.lower() in opt.lower():
                                await el.select_option(label=opt); break
                    filled += 1
                elif tag == "INPUT":
                    await el.fill(value)
                    filled += 1
        except: pass
    return filled


async def apply_job(page, job, acct):
    url = job["url"]
    domain = _accounts.tenant_domain(url)
    company = job["company"]
    job_url = url.rstrip("/")
    apply_url = job_url + "/apply/applyManually"
    email, pwd = acct["email"], acct["password"]

    print(f"\n{'='*60}\n{company} ({domain})")

    # Sign in
    await page.goto(apply_url, timeout=30000)
    await page.wait_for_timeout(3000)
    sl = page.locator('[data-automation-id="signInLink"]')
    if await sl.is_visible(timeout=3000):
        await sl.click(); await page.wait_for_timeout(2000)
        await page.locator('[data-automation-id="email"]').fill(email)
        await page.locator('[data-automation-id="password"]').fill(pwd)
        await page.wait_for_timeout(500)
        await click_wd(page, "Sign In"); await page.wait_for_timeout(5000)

    # Apply
    await page.goto(job_url, timeout=30000)
    await page.wait_for_timeout(3000)
    ab = page.locator('[data-automation-id="adventureButton"]')
    if await ab.is_visible(timeout=3000):
        await ab.click(); await page.wait_for_timeout(3000)
        am = page.locator('[data-automation-id="applyManually"]')
        if await am.is_visible(timeout=5000):
            await am.click(); await page.wait_for_timeout(5000)

            # Step 1 or direct to form
            if not await page.locator('[data-automation-id="email"]').is_visible(timeout=1000):
                f = await fill_missing(page)
                if f: print(f"  Filled {f} fields")
            else:
                await page.locator('[data-automation-id="email"]').fill(email)
                await page.locator('[data-automation-id="password"]').fill(pwd)
                cb = page.locator('[data-automation-id="createAccountCheckbox"]')
                if await cb.is_visible(timeout=1000): await cb.check()
                await page.wait_for_timeout(500)
                await click_wd(page, "Create Account")
                await page.wait_for_timeout(8000)

    print("  Simplify...")
    await page.wait_for_timeout(10000)
    f = await fill_missing(page)
    if f: print(f"  Filled {f} more")

    # Wizard - up to 500 steps for long forms
    last_state = ""
    for step in range(500):
        f = await fill_missing(page)
        if f and step < 5: print(f"  Filled {f}")

        for fn in ["Submit", "Submit Application", "Review and Submit", "Finish", "Done", "Review"]:
            if await has_wd(page, fn) and await click_wd(page, fn):
                await page.wait_for_timeout(8000)
                b = await page.inner_text("body")
                for w in ["thank you", "submitted", "Your application"]:
                    if w in b.lower():
                        print(f"  ✅ SUBMITTED!"); return "SUBMITTED"
                return "REVIEW"

        for name in ["Save and Continue", "Continue", "Next", "Save & Continue", "Save"]:
            if await has_wd(page, name) and await click_wd(page, name):
                await page.wait_for_timeout(3000)
                # Check if page actually changed - if not, we're stuck
                new_body = await page.inner_text("body")
                if new_body == last_state:
                    print(f"  → Stuck at step {step+1}")
                    break
                last_state = new_body
                if step < 5 or step % 20 == 19: print(f"  → {name} (step {step+1})")
                break
        else:
            break

    return "WIZARD_END"


targets = []
for job in build_queue():
    d = _accounts.tenant_domain(job.get("url", ""))
    if d:
        acct = _accounts.get_account(d)
        if acct: targets.append((job, acct))
print(f"Targets: {len(targets)}")


async def main():
    if os.path.exists(PROFILE): shutil.rmtree(PROFILE)
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox", "--disable-blink-features=AutomationControlled"])
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        results = [(j["company"], await apply_job(page, j, a)) for j, a in targets]
        print(f"\n{'='*60}\nRESULTS:")
        for c, r in results: print(f"  {c:25s}: {r}")
        await ctx.close()


asyncio.run(main())

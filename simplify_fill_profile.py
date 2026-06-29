#!/usr/bin/env python3
"""Fill Simplify profile with Kyler's data from vault."""
import asyncio, os, shutil
from pathlib import Path
from playwright.async_api import async_playwright

SDIR = str(Path.home() / ".simplify" / "chromium")
NDIR = str(Path.home() / ".nopecha" / "chromium")
PROFILE = "/tmp/simplify-filled-v2"


async def click_tab(page, name):
    """Click a section tab by its text."""
    tabs = page.locator('a, button, nav a, div[class*="tab"]')
    count = await tabs.count()
    for i in range(count):
        try:
            text = await tabs.nth(i).inner_text()
            if text.strip() == name:
                await tabs.nth(i).click()
                await page.wait_for_timeout(1500)
                return True
        except: pass
    return False


async def main():
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE, headless=False,
            args=[f"--load-extension={SDIR},{NDIR}", "--no-sandbox",
                  "--disable-blink-features=AutomationControlled"],
            slow_mo=200,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # Login
        await page.goto("https://simplify.jobs/auth/login", timeout=30000)
        await page.wait_for_timeout(2000)
        try:
            await page.locator('button:has-text("Accept All")').click(timeout=3000)
        except: pass
        await page.locator('input[placeholder="Email Address"]').fill("kylercao18@gmail.com")
        await page.locator('input[placeholder="Password"]').fill("Monkeytype1511")
        await page.wait_for_timeout(1500)
        await page.locator('button[type="submit"]').click()
        await page.wait_for_timeout(5000)
        print("✅ Logged in")

        # Go to first onboarding section
        await page.goto("https://simplify.jobs/onboarding", timeout=30000)
        await page.wait_for_timeout(3000)

        # === Section: Roles (First Name, Last Name + resume) ===
        print("\n=== Roles ===")
        # The page already shows First Name / Last Name
        fn = page.locator('input[placeholder="First Name"]')
        if await fn.is_visible(timeout=3000):
            await fn.fill("Kyler")
            await page.wait_for_timeout(200)

        ln = page.locator('input[placeholder="Last Name"]')
        if await ln.is_visible(timeout=2000):
            await ln.fill("Cao")
            await page.wait_for_timeout(200)

        # Click "Get Started" (uses resume data)
        gs = page.locator('button:has-text("Get Started")')
        if await gs.is_visible(timeout=3000):
            await gs.click()
            await page.wait_for_timeout(3000)
            print("  Get Started clicked")
        else:
            # Try "Save and Continue"
            sc = page.locator('button:has-text("Save and Continue")')
            if await sc.is_visible(timeout=2000):
                await sc.click()
                await page.wait_for_timeout(3000)
                print("  Save and Continue clicked")

        # === Section: Education ===
        print("\n=== Education ===")
        await click_tab(page, "Education")
        await page.wait_for_timeout(1000)

        school = page.locator('input[placeholder="School Name"], input:below(:text("School Name"))')
        if await school.is_visible(timeout=3000):
            await school.fill("Texas A&M University")
            await page.wait_for_timeout(200)

        major = page.locator('input[placeholder="Major"], input:below(:text("Major"))')
        if await major.is_visible(timeout=2000):
            await major.fill("Computer Science")
            await page.wait_for_timeout(200)

        # Try degree type dropdown
        degree_select = page.locator('select:below(:text("Degree Type"))')
        if await degree_select.is_visible(timeout=2000):
            await degree_select.select_option("Bachelor")
            await page.wait_for_timeout(200)

        gpa = page.locator('input[placeholder="GPA"], input:below(:text("GPA"))')
        if await gpa.is_visible(timeout=2000):
            await gpa.fill("3.59")
            await page.wait_for_timeout(200)

        # Add Education button
        add_edu = page.locator('button:has-text("Add Education")')
        if await add_edu.is_visible(timeout=2000):
            await add_edu.click()
            await page.wait_for_timeout(2000)

        sc = page.locator('button:has-text("Save and Continue")')
        if await sc.is_visible(timeout=2000):
            await sc.click()
            await page.wait_for_timeout(3000)
            print("  Education saved")

        # === Section: Experience ===
        print("\n=== Experience ===")
        await click_tab(page, "Experience")
        await page.wait_for_timeout(1000)

        # Check if first-job checkbox exists
        first_job = page.locator('text=I\'m looking for my first job')
        if await first_job.is_visible(timeout=2000):
            # Uncheck if checked
            cb = first_job.locator('..').locator('input[type="checkbox"]')
            if await cb.is_checked():
                await cb.click()
                await page.wait_for_timeout(500)

        # Add Global Shop Solutions experience
        pos = page.locator('input[placeholder="Position Title"], input:below(:text("Position Title"))').first
        if await pos.is_visible(timeout=3000):
            await pos.fill("Product & Engineering Intern")
            await page.wait_for_timeout(200)

        company = page.locator('input[placeholder="Company"], input:below(:text("Company"))').first
        if await company.is_visible(timeout=2000):
            await company.fill("Global Shop Solutions")
            await page.wait_for_timeout(200)

        loc = page.locator('input[placeholder="Location"], input:below(:text("Location"))').first
        if await loc.is_visible(timeout=2000):
            await loc.fill("The Woodlands, TX")
            await page.wait_for_timeout(200)

        # Experience Type
        exp_type = page.locator('select:below(:text("Experience Type"))')
        if await exp_type.is_visible(timeout=2000):
            await exp_type.select_option("Internship")
            await page.wait_for_timeout(200)

        # Start date
        start_month = page.locator('select:below(:text("Start Month"))')
        if await start_month.is_visible(timeout=2000):
            await start_month.select_option("May")
            await page.wait_for_timeout(100)
        start_year = page.locator('input[placeholder="Start Year"], select:below(:text("Start Year"))').first
        if await start_year.is_visible(timeout=2000):
            await start_year.fill("2026")
            await page.wait_for_timeout(100)

        # Currently work here
        cur_work = page.locator('text=I currently work here')
        if await cur_work.is_visible(timeout=2000):
            cb = cur_work.locator('..').locator('input[type="checkbox"]')
            if not await cb.is_checked():
                await cb.click()
                await page.wait_for_timeout(200)

        desc = page.locator('textarea:below(:text("Description"))').first
        if await desc.is_visible(timeout=2000):
            await desc.fill("Built AI-assisted test failure analysis pipeline using Python + LLM. Developed internal React + .NET tooling for manufacturing test data analysis.")
            await page.wait_for_timeout(200)

        add_exp = page.locator('button:has-text("Add Experience")')
        if await add_exp.is_visible(timeout=2000):
            await add_exp.click()
            await page.wait_for_timeout(2000)

        # Add TechHub experience
        pos2 = page.locator('input[placeholder="Position Title"]').first
        if await pos2.is_visible(timeout=2000):
            await pos2.fill("Student Technician III")
            await page.wait_for_timeout(200)
        company2 = page.locator('input[placeholder="Company"]').first
        if await company2.is_visible(timeout=2000):
            await company2.fill("Texas A&M University TechHub")
            await page.wait_for_timeout(200)
        loc2 = page.locator('input[placeholder="Location"]').first
        if await loc2.is_visible(timeout=2000):
            await loc2.fill("College Station, TX")
            await page.wait_for_timeout(200)

        # Uncheck current work for this one
        cur_work2 = page.locator('text=I currently work here')
        if await cur_work2.is_visible(timeout=2000):
            cb2 = cur_work2.locator('..').locator('input[type="checkbox"]')
            if await cb2.is_checked():
                await cb2.click()
                await page.wait_for_timeout(200)

        desc2 = page.locator('textarea').first
        if await desc2.is_visible(timeout=2000):
            await desc2.fill("Built full-stack Delivery Management System (Flask, React, MySQL): 150+ orders/month at 99.8% uptime. Collaborated on feature design and bug fixes.")
            await page.wait_for_timeout(200)

        add_exp2 = page.locator('button:has-text("Add Experience")')
        if await add_exp2.is_visible(timeout=2000):
            await add_exp2.click()
            await page.wait_for_timeout(2000)

        sc2 = page.locator('button:has-text("Save and Continue")')
        if await sc2.is_visible(timeout=2000):
            await sc2.click()
            await page.wait_for_timeout(3000)
            print("  Experience saved")

        # === Section: EEO ===
        print("\n=== EEO ===")
        await click_tab(page, "EEO")
        await page.wait_for_timeout(1000)

        # Ethnicity
        asian_opt = page.locator('text=Asian').first
        if await asian_opt.is_visible(timeout=2000):
            await asian_opt.click()
            await page.wait_for_timeout(200)

        # Gender: Male
        male_opt = page.locator('text=Male').first
        if await male_opt.is_visible(timeout=2000):
            await male_opt.click()
            await page.wait_for_timeout(200)

        sc3 = page.locator('button:has-text("Save and Continue")')
        if await sc3.is_visible(timeout=2000):
            await sc3.click()
            await page.wait_for_timeout(3000)
            print("  EEO saved")

        # === Section: Skills ===
        print("\n=== Skills ===")
        await click_tab(page, "Skills")
        await page.wait_for_timeout(1000)

        # Select skills
        skills_list = ["Python", "JavaScript", "TypeScript", "React", "Flask", "Git", "Docker", 
                       "Machine Learning", "Java", "C", "SQL", "FastAPI", "HTML/CSS", "Data Analysis",
                       "Full-stack development", "Documentation"]
        for skill in skills_list:
            try:
                opt = page.locator(f'text={skill}').first
                if await opt.is_visible(timeout=1000):
                    await opt.click()
                    await page.wait_for_timeout(100)
            except: pass

        sc4 = page.locator('button:has-text("Save and Continue")')
        if await sc4.is_visible(timeout=2000):
            await sc4.click()
            await page.wait_for_timeout(3000)
            print("  Skills saved")

        # === Section: Personal ===
        print("\n=== Personal ===")
        await click_tab(page, "Personal")
        await page.wait_for_timeout(1000)

        dob = page.locator('input[placeholder*="Date of Birth"], input[type="date"]')
        if await dob.is_visible(timeout=2000):
            await dob.fill("2000-01-15")
            await page.wait_for_timeout(200)

        phone = page.locator('input[placeholder*="Phone"], input[type="tel"]')
        if await phone.is_visible(timeout=2000):
            await phone.fill("(832) 966-4150")
            await page.wait_for_timeout(200)

        sc5 = page.locator('button:has-text("Save and Continue")')
        if await sc5.is_visible(timeout=2000):
            await sc5.click()
            await page.wait_for_timeout(3000)
            print("  Personal saved")

        # === Section: Links ===
        print("\n=== Links ===")
        await click_tab(page, "Links")
        await page.wait_for_timeout(1000)

        linkedin = page.locator('input[placeholder*="linkedin"], input[placeholder*="LinkedIn"], input:below(:text("LinkedIn"))').first
        if await linkedin.is_visible(timeout=2000):
            await linkedin.fill("https://linkedin.com/in/kylercao")
            await page.wait_for_timeout(200)

        github = page.locator('input[placeholder*="github"], input[placeholder*="GitHub"]').first
        if await github.is_visible(timeout=2000):
            await github.fill("https://github.com/kyler505")
            await page.wait_for_timeout(200)

        portfolio = page.locator('input[placeholder*="portfolio"], input[placeholder*="website"]').first
        if await portfolio.is_visible(timeout=2000):
            await portfolio.fill("https://people.tamu.edu/~kcao")
            await page.wait_for_timeout(200)

        sc6 = page.locator('button:has-text("Save and Continue"), button:has-text("Finish")')
        if await sc6.is_visible(timeout=2000):
            await sc6.click()
            await page.wait_for_timeout(3000)
            print("  Links saved")

        await page.screenshot(path="/tmp/simplify-filled-final.png")
        print("\n✅ Profile filled! Screenshot saved to /tmp/simplify-filled-final.png")

        # Check final URL
        print(f"Final URL: {page.url}")
        body = await page.inner_text("body")
        print(f"Final page: {body[:500]}")

        await context.close()


asyncio.run(main())

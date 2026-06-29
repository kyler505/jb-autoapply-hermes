#!/usr/bin/env python3
"""Apply to HARMAN Intern – Software Engineering via Playwright + NopeCHA."""

import asyncio
import json
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

RESUME = "/home/kyler/.hermes/.playwright-mcp/uploads/resume_har.pdf"
JOB_URL = "https://jobsearch.harman.com/en_US/careers/JobDetail/Intern-Software-Engineering/31931"
NOPECHA_DIR = os.path.expanduser("~/.nopecha/chromium")

async def main():
    async with async_playwright() as p:
        # Launch with NopeCHA extension loaded
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/tmp/harman-apply-profile",
            headless=False,
            args=[
                f"--disable-extensions-except={NOPECHA_DIR}",
                f"--load-extension={NOPECHA_DIR}",
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
            slow_mo=500,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        print("1. Navigating to job posting...")
        await page.goto(JOB_URL, timeout=60000, wait_until="domcontentloaded")

        print("2. Clicking Apply...")
        apply_links = page.locator('a:has-text("Apply")')
        await apply_links.first.wait_for(timeout=10000)
        await apply_links.first.click()
        await page.wait_for_timeout(2000)

        # Step 1: Upload resume
        print("3. Uploading resume...")
        # The file input is hidden, use page-level set_input_files
        async with page.expect_file_chooser() as fc_info:
            upload_btn = page.locator('button:has-text("Upload From Computer")')
            await upload_btn.click()
        file_chooser = await fc_info.value
        await file_chooser.set_files(RESUME)
        await page.wait_for_timeout(3000)

        # Click Continue
        continue_btn = page.locator('button:has-text("Continue")')
        await continue_btn.wait_for(timeout=5000)
        await page.wait_for_timeout(1000)
        await continue_btn.click()
        await page.wait_for_timeout(3000)

        # See what step we're on now
        print(f"Current URL: {page.url}")
        html = await page.content()
        # Save the page for debugging
        with open("/tmp/harman_step1.html", "w") as f:
            f.write(html)
        print(f"Saved page to /tmp/harman_step1.html ({len(html)} chars)")

        # Try getting the page content
        title = await page.title()
        print(f"Page title: {title}")

        # Check for account creation or login
        body_text = await page.inner_text("body")
        print(f"Page text (first 2000): {body_text[:2000]}")

        await page.screenshot(path="/tmp/harman_step1.png")
        print("Screenshot saved to /tmp/harman_step1.png")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main())

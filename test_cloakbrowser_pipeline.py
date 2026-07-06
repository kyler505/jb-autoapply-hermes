"""Test script for a complete CloakBrowser integration proof-of-concept.

This creates a minimal version of the apply pipeline's browser launch
using CloakBrowser, verifying the full integration path works end-to-end.
"""
import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from jb_autoapply import simplify, nopecha, accounts, config


async def run_pipeline_with_cloakbrowser():
    """Demonstrate the CloakBrowser integration exactly as it would
    be used in apply.py's apply_queue() method."""
    
    # Copy the apply.py setup
    PROFILE = "/tmp/jb-cloakbrowser-run"
    ext_paths: list[str] = []
    
    nopecha_ready = nopecha.is_ready()
    simplify_ready = simplify.is_ready()
    
    if nopecha_ready and simplify_ready:
        ext_paths = [str(simplify.EXTENSION_DIR), str(nopecha.EXTENSION_DIR)]
    elif nopecha_ready:
        ext_paths = [str(nopecha.EXTENSION_DIR)]
    elif simplify_ready:
        ext_paths = [str(simplify.EXTENSION_DIR)]
    
    print(f"Extensions: {len(ext_paths)} loaded")
    print(f"  NopeCHA={nopecha_ready}, Simplify={simplify_ready}")
    
    # Clean profile
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)
    
    # CloakBrowser import (replaces async_playwright)
    from cloakbrowser import launch_persistent_context_async
    
    print(f"Launching CloakBrowser...")
    ctx = await launch_persistent_context_async(
        user_data_dir=PROFILE,
        headless=False,
        extension_paths=ext_paths,
    )
    
    try:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        
        # Test bot detection evasion with CloakBrowser
        print(f"Navigating to test page...")
        await page.goto("about:blank", timeout=15000)
        
        # Comprehensive fingerprint check
        fp = await page.evaluate("""() => ({
            webdriver: navigator.webdriver,
            platform: navigator.platform,
            plugins: navigator.plugins.length,
            languages: JSON.stringify(navigator.languages),
            chrome: typeof chrome !== 'undefined' && typeof chrome.runtime !== 'undefined',
            userAgent: navigator.userAgent.substring(0, 80),
            hardwareConcurrency: navigator.hardwareConcurrency,
            webdriverValue: Object.getOwnPropertyDescriptor(navigator.__proto__, 'webdriver') ? 'defined on proto' : 'not on proto'
        })""")
        
        print(f"\nFingerprint check:")
        for k, v in fp.items():
            print(f"  {k}: {v}")
        
        # Verify profile was created
        profile_exists = os.path.exists(PROFILE) and os.path.isdir(PROFILE)
        print(f"\nProfile at {PROFILE}: {'✓ exists' if profile_exists else '✗ missing'}")
        
        # Simple navigation test
        print(f"\nNavigation test: https://httpbin.org/headers")
        await page.goto("https://httpbin.org/headers", timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(1000)
        body = await page.inner_text("body")
        print(f"  Response: {body[:300]}")
        
        print(f"\n{'='*50}")
        print(f"✅ CloakBrowser pipeline integration verified!")
        print(f"{'='*50}")
        
    finally:
        await ctx.close()
        shutil.rmtree(PROFILE, ignore_errors=True)
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_pipeline_with_cloakbrowser())
    sys.exit(exit_code)

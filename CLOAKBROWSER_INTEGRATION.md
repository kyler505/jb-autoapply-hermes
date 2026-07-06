"""
CloakBrowser Integration Plan for jb-autoapply-hermes
====================================================

PREREQUISITES (already done):
    pip install cloakbrowser

The binary auto-downloads on first launch (free tier, Chromium 146).

WHAT CHANGES IN apply.py:
-------------------------

CURRENT CODE (lines 1516-1570):
    # Build Playwright args with both extensions
    ext_args: list[str] = []
    if nopecha_ready and simplify_ready:
        ext_args = _simplify.playwright_args_with_nopecha()
    elif nopecha_ready:
        ext_args = _nopecha.playwright_args()
    elif simplify_ready:
        ext_args = _simplify.playwright_args()
    ext_args.extend(["--no-sandbox", "--disable-blink-features=AutomationControlled"])

    # Clean profile from previous runs
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE,
            headless=False,
            args=ext_args,
        )
        ...
        # On crash recovery (line 1553):
        ctx = await p.chromium.launch_persistent_context(...)

REPLACEMENT:

    from cloakbrowser import launch_persistent_context_async

    # Build extension paths list
    ext_paths: list[str] = []
    if nopecha_ready and simplify_ready:
        ext_paths = [str(_simplify.EXTENSION_DIR), str(_nopecha.EXTENSION_DIR)]
    elif nopecha_ready:
        ext_paths = [str(_nopecha.EXTENSION_DIR)]
    elif simplify_ready:
        ext_paths = [str(_simplify.EXTENSION_DIR)]

    # Clean profile from previous runs
    if os.path.exists(PROFILE):
        shutil.rmtree(PROFILE)

    # CloakBrowser handles:
    #   - async_playwright() lifecycle internally
    #   - stealth args (no need for --no-sandbox or --disable-blink-features)
    #   - extension loading via extension_paths parameter
    #   - platform spoofing (Windows by default)
    #   - navigator.webdriver=false at C++ level
    #   - CDP leak prevention
    ctx = await launch_persistent_context_async(
        user_data_dir=PROFILE,
        headless=False,
        extension_paths=ext_paths,
    )
    ...
    # On crash recovery (same change):
    ctx = await launch_persistent_context_async(
        user_data_dir=PROFILE,
        headless=False,
        extension_paths=ext_paths,
    )

WHAT CLOAKBROWSER FIXES:
-------------------------
✅ navigator.webdriver → false (C++ level, not JS injection)
✅ navigator.platform → Win32 (spoofed)
✅ window.chrome → exists (not missing like stock headless Chromium)
✅ CDP detection → patched (no $cdp_cdp leaks, no document.$schema)
✅ TLS fingerprint → patched (Windows TLS stack emulation)
✅ Timing attacks → patched (C++ level timing randomisation)
✅ Cloudflare Turnstile → passes (30/30 bot detection tests)
✅ reCAPTCHA v3 → scores ~0.9 (human-like)

WHAT CLOAKBROWSER DOES NOT FIX:
--------------------------------
❌ Workday React synthetic event system (multiselect combobox clicks)
   - This is a React event dispatch issue, not a bot detection issue
   - Existing workarounds still needed: overlay removal, JS dispatchEvent,
     press_sequentially(), force=True
❌ CAPTCHA challenges themselves (still needs NopeCHA extension)
   - CloakBrowser helps AVOID challenges being shown (better fingerprint)
   - But if a challenge appears, NopeCHA still handles solving it

COST / LICENSING:
-----------------
Free tier: Chromium 146, all stealth patches included.
Pro tier: Chromium 148+, newest anti-bot patches (paid, ~$20-30/mo).
MIT license for the wrapper code; binary is separately licensed.

MIGRATION RISKS:
----------------
1. REGRESSION: CloakBrowser uses a different Chromium binary than Playwright's
   built-in one. If a site works with stock Chromium but not CloakBrowser's
   patched binary, fallback to stock Playwright would be needed.
2. EXTENSIONS: Verified that --load-extension works (confirmed via command line).
   Simplify + NopeCHA should function identically.
3. FONTS on Linux: CloakBrowser spoofs Windows platform; without Windows fonts
   installed, font fingerprinting could flag the mismatch.
   Fix: `sudo apt install ttf-mscorefonts-installer` or follow font setup guide.
4. HEADLESS: When headless=True with older binary, Playwright's default viewport
   is used. Newer binaries support headless_no_viewport. Free tier (v146)
   handles both cases.

RECOMMENDATION: Integrate CloakBrowser as the primary browser backend.
The migration is ~15 lines changed in apply.py (plus removing the
async_playwright() import). Zero behavioral API changes — the returned
ctx object is a standard Playwright BrowserContext.
"""

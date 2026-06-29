from __future__ import annotations

import shutil
import urllib.request
import zipfile
from pathlib import Path

SIMPLIFY_DIR = Path.home() / ".simplify"
EXTENSION_DIR = SIMPLIFY_DIR / "chromium"
CRX_PATH = SIMPLIFY_DIR / "chromium.crx"
ZIP_PATH = SIMPLIFY_DIR / "chromium.zip"

# Simplify Copilot extension ID on Chrome Web Store
EXTENSION_ID = "pbanhockgagggenencehbnadejlgchfc"
EXTENSION_VERSION = "2.6.3"

# Google CDN URL for Simplify Copilot CRX
_DOWNLOAD_URL = (
    "https://clients2.googleusercontent.com/crx/blobs/"
    "AcPRoeoAEavCLZ6Qksysx3h8B-Rwiwy7RNLZnPWv9mfxc_FN4ZiuZCfAusxh09FH-"
    "4Wstc5yHdaBlc3tVDcWF8oUxvPSK1z7tF7W2AwciudW0h06NQVNf2lVPggbsSd-"
    "tcd_AMZSmuUUva8C49rwsj9QBj694z36sTxqww/"
    "PBANHOCKGAGGGENENCEHBNADEJLGCHFC_2_6_3_0.crx"
)


def is_ready() -> bool:
    """True if the Simplify extension is downloaded and available."""
    return EXTENSION_DIR.exists() and (EXTENSION_DIR / "manifest.json").exists()


def ensure_extension(*, force_download: bool = False) -> Path:
    """Download and extract the Simplify Copilot extension if not already cached.

    Returns the path to the extracted extension directory.
    """
    SIMPLIFY_DIR.mkdir(parents=True, exist_ok=True)

    if not force_download and is_ready():
        return EXTENSION_DIR

    print(f"Downloading Simplify extension v{EXTENSION_VERSION} ...")
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.crx4chrome.com/",
    }
    req = urllib.request.Request(_DOWNLOAD_URL, headers=headers)
    resp = urllib.request.urlopen(req, timeout=120)
    data = resp.read()
    print(f"  got {len(data)} bytes")

    CRX_PATH.write_bytes(data)

    # CRX3 format: magic(4) + version(4) + header_len(4) + header + zip_data
    if data[:4] == b"Cr24":
        header_len = int.from_bytes(data[8:12], "little")
        zip_data = data[12 + header_len :]
    else:
        zip_data = data

    ZIP_PATH.write_bytes(zip_data)

    if EXTENSION_DIR.exists():
        shutil.rmtree(EXTENSION_DIR)

    with zipfile.ZipFile(ZIP_PATH) as zf:
        zf.extractall(str(EXTENSION_DIR))

    print(f"  extracted -> {EXTENSION_DIR}")
    return EXTENSION_DIR


def playwright_args() -> list[str]:
    """Return Chromium CLI flags to load the Simplify extension.

    Combine these with NopeCHA extension args.
    """
    return [
        f"--disable-extensions-except={EXTENSION_DIR}",
        f"--load-extension={EXTENSION_DIR}",
    ]


def playwright_args_with_nopecha(nopecha_dir: Path | None = None) -> list[str]:
    """Return args to load BOTH Simplify and NopeCHA extensions.

    Playwright's --disable-extensions-except only allows one extension
    to be active.  For multiple extensions, we use --load-extension with
    comma-separated paths and skip --disable-extensions-except.
    """
    from . import nopecha as _nopecha

    nopecha_dir = nopecha_dir or _nopecha.EXTENSION_DIR
    extensions = [str(EXTENSION_DIR)]
    if nopecha_dir.exists():
        extensions.append(str(nopecha_dir))

    return [
        f"--load-extension={','.join(extensions)}",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
    ]


def status_text() -> str:
    """Human-readable status."""
    if is_ready():
        return f"Simplify Copilot v{EXTENSION_VERSION}: installed at {EXTENSION_DIR}"
    return "Simplify Copilot: not installed (run ensure_extension)"

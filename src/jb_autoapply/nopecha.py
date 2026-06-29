from __future__ import annotations

import json
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

NOPECHA_KEY_ENV = "NOPECHA_KEY"
NOPECHA_DIR = Path.home() / ".nopecha"
EXTENSION_ZIP = NOPECHA_DIR / "chromium.zip"
EXTENSION_DIR = NOPECHA_DIR / "chromium"
SETTINGS_FILE = EXTENSION_DIR / "settings.json"

# Sources for the official NopeCHA Chrome extension.
_DOWNLOAD_URL = (
    "https://github.com/NopeCHALLC/"
    "nopecha-extension/releases/latest/download/chromium.zip"
)


def get_api_key() -> str | None:
    """Return the NopeCHA API key from $NOPECHA_KEY, or None."""
    key = os.environ.get(NOPECHA_KEY_ENV)
    return key.strip() if key else None


def is_ready() -> bool:
    """True if the extension is downloaded.

    The extension works out of the box for up to 100 solves/day
    (rate-limited by IP).  An API key is optional and only needed
    for higher quotas.
    """
    return EXTENSION_DIR.exists()


def ensure_extension(*, force_download: bool = False) -> Path:
    """Download and extract the NopeCHA extension if not already cached.

    Returns the path to the extracted extension directory.
    """
    NOPECHA_DIR.mkdir(parents=True, exist_ok=True)

    if not force_download and EXTENSION_DIR.exists():
        return EXTENSION_DIR

    print(f"Downloading NopeCHA extension from {_DOWNLOAD_URL} ...")
    resp = urllib.request.urlopen(urllib.request.Request(_DOWNLOAD_URL), timeout=120)
    data = resp.read()

    if EXTENSION_ZIP.exists():
        EXTENSION_ZIP.unlink()
    EXTENSION_ZIP.write_bytes(data)

    if EXTENSION_DIR.exists():
        shutil.rmtree(EXTENSION_DIR)

    with zipfile.ZipFile(EXTENSION_ZIP, "r") as z:
        z.extractall(EXTENSION_DIR)

    print(f"NopeCHA extension extracted to {EXTENSION_DIR}")
    return EXTENSION_DIR


def configure_key(key: str) -> None:
    """Write the API key and auto-solve settings into the extension.

    This modifies *settings.json* inside the extracted extension so it
    works with the *automation* build without needing a URL visit.
    """
    settings: dict = {}
    if SETTINGS_FILE.exists():
        settings = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    settings["key"] = key
    settings["auto_solve"] = True
    settings["auto_open"] = False
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"NopeCHA key configured in {SETTINGS_FILE}")


def playwright_args(ext_path: Path | None = None) -> list[str]:
    """Return Chromium launch arguments to load the NopeCHA extension.

    Pass these to ``playwright.chromium.launch_persistent_context(args=[...])``
    or ``browser_type.launch(args=[...])``.
    """
    if ext_path is None:
        ext_path = EXTENSION_DIR
    return [
        f"--disable-extensions-except={ext_path}",
        f"--load-extension={ext_path}",
        "--no-sandbox",
        "--disable-blink-features=AutomationControlled",
    ]


def status_text() -> str:
    """Return a human-readable status string."""
    parts: list[str] = []
    if EXTENSION_DIR.exists():
        parts.append("extension: installed")
    else:
        parts.append("extension: not installed")

    key = get_api_key()
    if key:
        masked = key[:4] + "…" + key[-4:] if len(key) > 8 else key[:4] + "…"
        parts.append(f"key: {masked}")
    else:
        parts.append("key: not set (free 100/day by IP)")

    if is_ready():
        parts.append("ready: yes")
    else:
        parts.append("ready: no — download extension first")

    return " |  ".join(parts)


def __getattr__(name: str):
    """Lazy re-export so callers can ``from jb_autoapply.nopecha import NopechaConfig`` if needed."""
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

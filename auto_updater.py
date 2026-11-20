"""Auto-updater that checks for updates on startup."""

import os
import json
import hashlib
import time
import urllib.request
from pathlib import Path

BUCKET_NAME = "mp3-player-updates"
S3_PREFIX = "mp3-player/"
BASE_URL = f"https://{BUCKET_NAME}.s3.amazonaws.com/{S3_PREFIX}"
LOCAL_DIR = Path(__file__).parent
# Remembers the S3 ETag of each file we last saw, so we can detect changes
# with a lightweight HEAD request instead of downloading the whole file.
ETAG_CACHE = LOCAL_DIR / ".update_etags.json"


def _fetch(url, dest):
    """Download a URL to dest with cache-busting and no-cache headers so we
    never get a stale copy from S3/CDN caches."""
    bust = f"{'&' if '?' in url else '?'}_cb={int(time.time()*1000)}"
    req = urllib.request.Request(
        url + bust,
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "AudioVaultTV-Updater",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def _get_remote_signature(url):
    """Return a lightweight change-signature (ETag or size) for a remote file
    using an HTTP HEAD request. Does NOT download the file body."""
    bust = f"{'&' if '?' in url else '?'}_cb={int(time.time()*1000)}"
    req = urllib.request.Request(
        url + bust,
        method="HEAD",
        headers={"Cache-Control": "no-cache", "User-Agent": "AudioVaultTV-Updater"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        etag = resp.headers.get("ETag")
        size = resp.headers.get("Content-Length")
        return (etag or "") + "|" + (size or "")


def _load_etag_cache():
    try:
        with open(ETAG_CACHE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_etag_cache(cache):
    try:
        with open(ETAG_CACHE, "w") as f:
            json.dump(cache, f)
    except Exception:
        pass

FILES_TO_SYNC = [
    "main.py",
    "audio_player.py",
    "playlist_manager.py",
    "channel_manager.py",
    "voice_control.py",
    "player_logger.py",
    "audiovault_client.py",
    "youtube_client.py",
    "livetv_client.py",
    "auto_updater.py",
    "sounds/startup.mp3",
    "sounds/outro.mp3",
    "sounds/start_of_request.wav",
    "sounds/end_of_request.wav",
    "sounds/remote.mp3",
    "tools/ffmpeg.exe",
    "tools/ffprobe.exe",
    "tools/ffplay.exe",
    "tools/deno.exe",
    "requirements.txt",
    "README.md",
]


def get_file_hash(filepath):
    if not os.path.exists(filepath):
        return None
    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()


def check_for_updates():
    """Check which files have updates available using lightweight HEAD requests
    (ETag/size). Returns list of filenames that need updating.

    IMPORTANT: this does NOT modify the ETag cache. The cache is only updated
    in apply_updates(), once a file has actually been downloaded and applied.
    (Previously the check wrote the new signature immediately, which meant a
    declined or failed update would be silently 'forgotten' and never offered
    again.)
    """
    available = []
    etag_cache = _load_etag_cache()

    for filename in FILES_TO_SYNC:
        local_path = LOCAL_DIR / filename
        file_url = f"{BASE_URL}{filename}"

        try:
            remote_sig = _get_remote_signature(file_url)
        except Exception:
            # If HEAD fails, skip this file rather than forcing a slow download
            continue

        cached_sig = etag_cache.get(filename)

        # A file needs updating if:
        #  - it doesn't exist locally, OR
        #  - we have no recorded signature for it (never applied), OR
        #  - the remote signature differs from the last APPLIED signature.
        if not local_path.exists():
            available.append(filename)
        elif cached_sig is None or cached_sig != remote_sig:
            available.append(filename)

    return available


def apply_updates(filenames):
    """Download and apply updates for the given filenames. Returns list of updated filenames."""
    updated = []
    etag_cache = _load_etag_cache()

    for filename in filenames:
        local_path = LOCAL_DIR / filename
        file_url = f"{BASE_URL}{filename}"
        temp_path = LOCAL_DIR / f"{filename}.tmp"

        try:
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            _fetch(file_url, str(temp_path))

            if local_path.exists():
                os.remove(str(local_path))
            os.rename(str(temp_path), str(local_path))
            updated.append(filename)

            # Record the new signature so we don't re-flag it next launch
            try:
                etag_cache[filename] = _get_remote_signature(file_url)
            except Exception:
                pass
        except Exception:
            if temp_path.exists():
                os.remove(str(temp_path))

    _save_etag_cache(etag_cache)
    return updated

"""Auto-updater that checks for updates on GitHub.

The program's files live in the public GitHub repo
ashleymorisseau-stack/audiovault-tv, branch master. There is no S3 bucket
and no AWS login needed any more.

How it decides a file needs updating:
  1. Ask GitHub for the repo's file list (the "tree"). Each file in the
     list has a git blob SHA - a fingerprint of its exact contents.
  2. Work out the same fingerprint for the file on this computer.
     Text files are compared with Windows line endings ignored,
     so a file that was just pulled does not look changed.
  3. If the fingerprints differ, or the file is missing here, it needs
     updating.

Downloads come from raw.githubusercontent.com, and the downloaded file's
fingerprint is checked against GitHub's before it replaces the local copy,
so a bad or half-finished download never overwrites a good file.

Some files in FILES_TO_SYNC are NOT in the GitHub repo (the sounds and the
tools programs - the repo's .gitignore leaves them out, and GitHub refuses
single files over 100 MB). Those files are simply skipped: the local copy
is left alone and the update never fails because of them.

If GitHub cannot be reached, check_for_updates() returns an empty list and
apply_updates() returns an empty list, so the program just carries on
playing normally. It never crashes the app.
"""

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

REPO = "ashleymorisseau-stack/audiovault-tv"
BRANCH = "master"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"
LOCAL_DIR = Path(__file__).parent

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


def _git_blob_sha(data):
    """Git fingerprint of file contents: sha1 of "blob <length>\\0" + data."""
    head = b"blob %d\0" % len(data)
    return hashlib.sha1(head + data).hexdigest()


def _local_blob_sha(path):
    """Git fingerprint of a local file, or None if it does not exist.

    Windows checkouts store text files with CRLF line endings while the
    repo stores LF, so the raw bytes differ even when the words are the
    same. Text files are normalised to LF before fingerprinting, so a
    freshly pulled file matches the repo. Binary files (sounds, tools)
    are fingerprinted exactly as they are.
    """
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        data = f.read()
    if b"\0" not in data:
        # Looks like text: ignore the CRLF/LF difference.
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _fetch_tree():
    """Return {path: git blob sha} for every file in the GitHub repo.

    Returns None if GitHub cannot be reached or the answer is unusable.
    """
    req = urllib.request.Request(
        TREE_URL,
        headers={
            "User-Agent": "AudioVaultTV-Updater",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            tree = json.load(resp)
    except Exception:
        return None
    if not isinstance(tree, dict) or tree.get("truncated"):
        # A truncated tree cannot be trusted to say which files changed.
        return None
    out = {}
    for entry in tree.get("tree", []):
        if entry.get("type") == "blob":
            out[entry["path"]] = entry["sha"]
    return out


def _fetch(url, dest):
    """Download a URL to dest with cache-busting and no-cache headers so we
    never get a stale copy from a cache."""
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


def get_file_hash(filepath):
    """MD5 hash of a file, or None if it does not exist.

    Kept for compatibility with older callers; the updater itself compares
    git blob fingerprints (see _local_blob_sha).
    """
    if not os.path.exists(filepath):
        return None
    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()


def files_not_in_repo():
    """Files from FILES_TO_SYNC that are not in the GitHub repo.

    These are left alone by the updater. Returns [] if GitHub cannot be
    reached (we simply do not know, so we claim nothing).
    """
    tree = _fetch_tree()
    if tree is None:
        return []
    return [name for name in FILES_TO_SYNC if name not in tree]


def check_for_updates():
    """Check which files have updates available on GitHub.

    Returns a list of filenames that need updating. Returns an empty list
    if GitHub cannot be reached, so the program just carries on normally.
    Files that are not in the GitHub repo are never listed.
    """
    tree = _fetch_tree()
    if tree is None:
        return []

    available = []
    for filename in FILES_TO_SYNC:
        remote_sha = tree.get(filename)
        if remote_sha is None:
            # Not in the GitHub repo (sounds, tools programs). Leave the
            # local copy alone and do not offer it as an update.
            continue
        local_path = LOCAL_DIR / filename
        if not local_path.exists() or _local_blob_sha(local_path) != remote_sha:
            available.append(filename)

    return available


def apply_updates(filenames):
    """Download and apply updates for the given filenames.

    Each download is checked against GitHub's fingerprint before it
    replaces the local file. Returns the list of filenames actually
    updated. Files not in the GitHub repo are skipped, never deleted.
    Returns an empty list if GitHub cannot be reached.
    """
    tree = _fetch_tree()
    if tree is None:
        return []

    updated = []
    for filename in filenames:
        remote_sha = tree.get(filename)
        if remote_sha is None:
            # Not in the GitHub repo - never touch or delete the local copy.
            continue
        local_path = LOCAL_DIR / filename
        temp_path = LOCAL_DIR / f"{filename}.tmp"

        try:
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            _fetch(RAW_BASE + filename, str(temp_path))

            # Only replace the local file if the download matches GitHub.
            if _local_blob_sha(temp_path) != remote_sha:
                raise ValueError("downloaded file does not match GitHub")

            if local_path.exists():
                os.remove(str(local_path))
            os.rename(str(temp_path), str(local_path))
            updated.append(filename)
        except Exception:
            if temp_path.exists():
                os.remove(str(temp_path))

    return updated

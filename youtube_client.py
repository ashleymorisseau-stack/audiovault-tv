"""
YouTube search and download client using yt-dlp Python library.
Place ffmpeg.exe, ffprobe.exe, and deno.exe in the tools/ folder.
deno.exe is the JavaScript runtime yt-dlp uses to solve YouTube's player
challenge; without it downloads can fail with HTTP 403 Forbidden.
"""

import os
import subprocess
import sys
from pathlib import Path
import yt_dlp

TOOLS_DIR = Path(__file__).parent / "tools"
DEFAULT_DOWNLOAD_DIR = Path(__file__).parent / "Downloads" / "YouTube"
CONFIG_FILE = Path(__file__).parent / "config.ini"


def _find_deno():
    """Locate the bundled Deno JS runtime. Returns path string or None."""
    exe = "deno.exe" if os.name == "nt" else "deno"
    candidate = TOOLS_DIR / exe
    if candidate.exists():
        return str(candidate)
    return None


def _apply_js_runtime(opts):
    """Configure yt-dlp to use the bundled Deno runtime if present.
    yt-dlp needs a JS runtime to solve YouTube's player challenge;
    without it, downloads can fail with HTTP 403 Forbidden."""
    deno = _find_deno()
    if deno:
        # Ensure the tools dir is on PATH so yt-dlp's runtime discovery finds deno
        tools_str = str(TOOLS_DIR)
        current_path = os.environ.get("PATH", "")
        if tools_str not in current_path:
            os.environ["PATH"] = tools_str + os.pathsep + current_path
        # YoutubeDL expects: {runtime_name: {'path': path_or_None}}
        opts["js_runtimes"] = {"deno": {"path": deno}}
    return opts


class VideoUnavailableError(Exception):
    """Raised when a video exists but YouTube refuses to serve it
    (removed, private, region-locked, age-restricted, etc.)."""
    pass


def _is_unavailable_error(error_msg):
    """Detect whether a yt-dlp error means the video simply cannot be obtained."""
    msg = str(error_msg).lower()
    markers = [
        "video is not available",
        "video unavailable",
        "private video",
        "removed by the uploader",
        "no longer available",
        "account associated with this video has been terminated",
        "video has been removed",
        "not available in your country",
        "sign in to confirm your age",
        "this video is unavailable",
        # DRM-protected videos have no downloadable audio formats
        "drm protected",
        "only images are available",
        "requested format is not available",
    ]
    return any(m in msg for m in markers)


def _normalize_version(v):
    """Normalize a version string like 2026.08.19 -> (2026, 8, 19) for comparison."""
    if not v:
        return ()
    parts = []
    for p in str(v).split("."):
        digits = "".join(c for c in p if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def versions_match(v1, v2):
    """Compare two version strings ignoring zero-padding differences."""
    return _normalize_version(v1) == _normalize_version(v2)


def get_ytdlp_version():
    """Return the installed yt-dlp version string."""
    return getattr(yt_dlp.version, "__version__", "unknown")


def get_latest_ytdlp_version():
    """Query PyPI for the latest available yt-dlp version. Returns version string or None."""
    try:
        import json
        import urllib.request
        req = urllib.request.Request(
            "https://pypi.org/pypi/yt-dlp/json",
            headers={"User-Agent": "AudioVaultTV"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        return data.get("info", {}).get("version")
    except Exception:
        return None


def update_ytdlp():
    """Update yt-dlp (and the yt-dlp-ejs challenge solver) to the latest version via pip.
    Returns (success: bool, message: str)."""
    old_version = get_ytdlp_version()
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir",
             "yt-dlp", "yt-dlp-ejs"],
            capture_output=True, text=True, timeout=180
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "Unknown error").strip()
            return False, f"Update failed: {err[:300]}"

        # Determine the version that got installed by parsing pip output
        out = (result.stdout or "")
        if "Requirement already satisfied" in out and "Successfully installed" not in out:
            return True, f"yt-dlp is already up to date (version {old_version})."

        return True, (
            f"yt-dlp updated from {old_version}. "
            f"Please close and reopen AudioVault TV for the update to take effect."
        )
    except subprocess.TimeoutExpired:
        return False, "Update timed out. Check your internet connection and try again."
    except FileNotFoundError:
        return False, (
            "Could not run pip. Python may not be on your PATH. "
            "Try updating manually: open Command Prompt and run "
            "'pip install --upgrade yt-dlp yt-dlp-ejs'."
        )
    except Exception as e:
        return False, f"Update error: {e}"


def save_download_dir(directory):
    import configparser
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if "youtube" not in config:
        config["youtube"] = {}
    config["youtube"]["download_dir"] = str(directory)
    with open(CONFIG_FILE, "w") as f:
        config.write(f)


def load_download_dir():
    import configparser
    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_FILE)
        return config["youtube"]["download_dir"]
    except (KeyError, FileNotFoundError):
        return str(DEFAULT_DOWNLOAD_DIR)


def search(query, max_results=40, min_duration_secs=0, full_episodes_only=False,
           sort_by="relevance"):
    """Search YouTube. Returns list of dicts with id, title, duration, url, channel.

    max_results: how many results to request.
    min_duration_secs: drop any video shorter than this (filters out clips).
    full_episodes_only: convenience flag -> keep only videos >= 15 minutes.
    sort_by: 'relevance' (YouTube order), 'longest', or 'shortest'.
    """
    if full_episodes_only and min_duration_secs < 900:
        min_duration_secs = 900  # 15 minutes (keeps ad-trimmed episodes)

    opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }
    _apply_js_runtime(opts)
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

    entries = result.get("entries", [])
    results = []
    for entry in entries:
        duration = entry.get("duration") or 0
        # Filter out clips when a minimum duration is requested. Entries with an
        # unknown duration (0/None) are kept so we don't hide valid results.
        if min_duration_secs and duration and duration < min_duration_secs:
            continue
        mins = int(duration // 60)
        secs = int(duration % 60)
        results.append({
            "id": entry.get("id", ""),
            "title": entry.get("title", "Unknown"),
            "duration": f"{mins}:{secs:02d}" if duration else "?:??",
            "duration_secs": duration,
            "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
            "channel": entry.get("channel") or entry.get("uploader") or "",
        })

    # Optional sorting. Unknown-duration items sort to the bottom either way.
    if sort_by == "longest":
        results.sort(key=lambda r: r["duration_secs"] or 0, reverse=True)
    elif sort_by == "shortest":
        results.sort(key=lambda r: r["duration_secs"] or 10**9)

    return results


def detect_url(url):
    """Check if a URL is a playlist or single video.
    Returns dict with 'is_playlist', 'title', 'count', and 'entries' (list of title/url dicts)."""
    opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }
    _apply_js_runtime(opts)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist" or "entries" in info:
        entries = info.get("entries", [])
        return {
            "is_playlist": True,
            "title": info.get("title", "Playlist"),
            "count": len(entries),
            "entries": [
                {
                    "title": e.get("title", "Unknown"),
                    "url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id', '')}",
                    "duration": e.get("duration") or 0,
                }
                for e in entries
            ],
        }
    return {
        "is_playlist": False,
        "title": info.get("title", "Unknown"),
        "count": 1,
        "entries": [{"title": info.get("title", "Unknown"), "url": url, "duration": info.get("duration") or 0}],
    }


def _find_ffmpeg():
    """Locate ffmpeg. Returns the tools dir path if the binaries exist there,
    otherwise None (let yt-dlp search PATH)."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidate = TOOLS_DIR / exe
    if candidate.exists():
        return str(TOOLS_DIR)
    # Also accept a bare 'ffmpeg' on PATH
    return None


def ffmpeg_available():
    """Return True if ffmpeg can be found either in tools/ or on PATH."""
    if _find_ffmpeg():
        return True
    import shutil
    return shutil.which("ffmpeg") is not None


def download(url, destination=None, progress_callback=None, allow_playlist=False):
    """Download audio as MP3. progress_callback(percent, filename) called during download.
    Returns final file path on success."""
    if not destination:
        destination = str(DEFAULT_DOWNLOAD_DIR)
    os.makedirs(destination, exist_ok=True)

    final_filename = [None]

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0 and progress_callback:
                percent = (downloaded / total) * 100
                progress_callback(percent, d.get("filename", ""))
        elif d["status"] == "finished":
            final_filename[0] = d.get("filename")

    opts = {
        # Prefer audio-only, but fall back through progressively looser options
        # so a missing "bestaudio" doesn't hard-fail with "Requested format is
        # not available". The last "/best" grabs whatever single stream exists.
        "format": "bestaudio/bestaudio*/best",
        "outtmpl": os.path.join(destination, "%(title)s.%(ext)s"),
        "noplaylist": not allow_playlist,
        "quiet": True,
        # If the exact requested format is missing, don't abort — take the
        # closest available instead of raising an error.
        "ignore_no_formats_error": False,
        # Skip anything we've already downloaded to this folder before. yt-dlp
        # records each video id here and won't re-download them next time.
        "download_archive": os.path.join(destination, ".downloaded.txt"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "progress_hooks": [progress_hook],
    }
    ffmpeg_dir = _find_ffmpeg()
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir
    elif not ffmpeg_available():
        raise RuntimeError(
            "ffmpeg/ffprobe not found. The 'tools' folder must contain ffmpeg.exe and "
            "ffprobe.exe, or ffmpeg must be installed on your system PATH. "
            "Downloads cannot be converted to MP3 without it."
        )

    _apply_js_runtime(opts)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        if _is_unavailable_error(e):
            raise VideoUnavailableError(str(e))
        raise

    # If the post-processed MP3 was produced, return its path.
    if final_filename[0]:
        mp3_path = Path(final_filename[0]).with_suffix(".mp3")
        if mp3_path.exists():
            return str(mp3_path)

    # Nothing was produced this run. This normally means the video was already
    # in the download archive (previously downloaded) and was skipped — which
    # is success, not failure. Signal that with the sentinel "ALREADY".
    return "ALREADY"

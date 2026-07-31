"""
YouTube search and download client using yt-dlp Python library.
Place ffmpeg.exe and ffprobe.exe in the tools/ folder.
"""

import os
from pathlib import Path
import yt_dlp

TOOLS_DIR = Path(__file__).parent / "tools"
DEFAULT_DOWNLOAD_DIR = Path(__file__).parent / "Downloads" / "YouTube"
CONFIG_FILE = Path(__file__).parent / "config.ini"


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


def search(query, max_results=15):
    """Search YouTube. Returns list of dicts with id, title, duration, url, channel."""
    opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)

    entries = result.get("entries", [])
    results = []
    for entry in entries:
        duration = entry.get("duration") or 0
        mins = int(duration // 60)
        secs = int(duration % 60)
        results.append({
            "id": entry.get("id", ""),
            "title": entry.get("title", "Unknown"),
            "duration": f"{mins}:{secs:02d}",
            "duration_secs": duration,
            "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id', '')}",
            "channel": entry.get("channel") or entry.get("uploader") or "",
        })
    return results


def detect_url(url):
    """Check if a URL is a playlist or single video.
    Returns dict with 'is_playlist', 'title', 'count', and 'entries' (list of title/url dicts)."""
    opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }
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
        "format": "bestaudio/best",
        "outtmpl": os.path.join(destination, "%(title)s.%(ext)s"),
        "noplaylist": not allow_playlist,
        "quiet": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "progress_hooks": [progress_hook],
    }
    if TOOLS_DIR.exists():
        opts["ffmpeg_location"] = str(TOOLS_DIR)

    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

    # The final file will be .mp3 (post-processed)
    if final_filename[0]:
        mp3_path = Path(final_filename[0]).with_suffix(".mp3")
        if mp3_path.exists():
            return str(mp3_path)

    # Fallback: find most recent mp3 in destination
    mp3s = sorted(Path(destination).glob("*.mp3"), key=os.path.getmtime, reverse=True)
    return str(mp3s[0]) if mp3s else None

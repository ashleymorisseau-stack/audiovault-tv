"""Auto-updater that checks for updates on startup."""

import os
import hashlib
import urllib.request
from pathlib import Path

BUCKET_NAME = "mp3-player-updates"
S3_PREFIX = "mp3-player/"
BASE_URL = f"https://{BUCKET_NAME}.s3.amazonaws.com/{S3_PREFIX}"
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
    "auto_updater.py",
    "sounds/startup.mp3",
    "sounds/outro.mp3",
    "sounds/start_of_request.wav",
    "sounds/end_of_request.wav",
    "sounds/remote.mp3",
    "tools/ffmpeg.exe",
    "tools/ffprobe.exe",
    "tools/ffplay.exe",
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
    """Check which files have updates available. Returns list of filenames that need updating."""
    available = []
    for filename in FILES_TO_SYNC:
        local_path = LOCAL_DIR / filename
        file_url = f"{BASE_URL}{filename}"
        temp_path = LOCAL_DIR / f"{filename}.tmp"
        
        try:
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(file_url, str(temp_path))
            
            new_hash = get_file_hash(str(temp_path))
            old_hash = get_file_hash(str(local_path))
            
            if old_hash is None or new_hash != old_hash:
                available.append(filename)
            
            os.remove(str(temp_path))
        except Exception:
            if temp_path.exists():
                os.remove(str(temp_path))
    
    return available


def apply_updates(filenames):
    """Download and apply updates for the given filenames. Returns list of updated filenames."""
    updated = []
    for filename in filenames:
        local_path = LOCAL_DIR / filename
        file_url = f"{BASE_URL}{filename}"
        temp_path = LOCAL_DIR / f"{filename}.tmp"
        
        try:
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(file_url, str(temp_path))
            
            if local_path.exists():
                os.remove(str(local_path))
            os.rename(str(temp_path), str(local_path))
            updated.append(filename)
        except Exception:
            if temp_path.exists():
                os.remove(str(temp_path))
    
    return updated

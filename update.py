import os
import hashlib
import json
import wx
import threading
import urllib.request
from pathlib import Path

# Configuration - updates now come from the public GitHub repo, not S3.
# No AWS login or bucket is needed any more.
REPO = "ashleymorisseau-stack/audiovault-tv"
BRANCH = "master"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
RAW_BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"
LOCAL_DIR = Path(__file__).parent

# Files to sync (exclude the channels JSON file and vosk model)
FILES_TO_SYNC = [
    "main.py",
    "audio_player.py",
    "playlist_manager.py",
    "channel_manager.py",
    "voice_control.py",
    "player_logger.py",
    "youtube_client.py",
    "livetv_client.py",
    "update.py",
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
    "SETUP.md",
    "IMPLEMENTATION_PLAN.md",
    "VOICE_COMMANDS.md"
]

def get_file_hash(filepath):
    """Calculate MD5 hash of a file"""
    if not os.path.exists(filepath):
        return None

    md5 = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5.update(chunk)
    return md5.hexdigest()

def _git_blob_sha(data):
    """Git fingerprint of file contents: sha1 of "blob <length>\\0" + data."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()

def _local_blob_sha(path):
    """Git fingerprint of a local file, or None if it does not exist."""
    if not os.path.exists(path):
        return None
    sha = hashlib.sha1()
    sha.update(b"blob %d\0" % os.path.getsize(path))
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()

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
        return None
    out = {}
    for entry in tree.get("tree", []):
        if entry.get("type") == "blob":
            out[entry["path"]] = entry["sha"]
    return out

def download_file(url, local_path):
    """Download file from URL"""
    req = urllib.request.Request(
        url,
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "User-Agent": "AudioVaultTV-Updater",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp, open(local_path, "wb") as f:
        f.write(resp.read())

class UpdateFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="AudioVault TV Updater", size=(500, 300))

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Title
        title = wx.StaticText(panel, label="AudioVault TV Update Manager")
        title_font = title.GetFont()
        title_font.PointSize += 2
        title_font = title_font.Bold()
        title.SetFont(title_font)
        sizer.Add(title, 0, wx.ALL | wx.CENTER, 10)

        # Status text
        self.status_text = wx.StaticText(panel, label="Ready to check for updates")
        sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 10)

        # Progress bar
        self.progress = wx.Gauge(panel, range=100)
        sizer.Add(self.progress, 0, wx.ALL | wx.EXPAND, 10)

        # Log text area
        sizer.Add(wx.StaticText(panel, label="Update Log:"), 0, wx.LEFT | wx.TOP, 10)
        self.log_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        sizer.Add(self.log_text, 1, wx.ALL | wx.EXPAND, 10)

        # Update button
        self.update_btn = wx.Button(panel, label="Check for Updates")
        self.update_btn.Bind(wx.EVT_BUTTON, self._on_update)
        sizer.Add(self.update_btn, 0, wx.ALL | wx.CENTER, 10)

        panel.SetSizer(sizer)
        self.Centre()

    def log(self, message):
        """Add message to log"""
        wx.CallAfter(self._append_log, message)

    def _append_log(self, message):
        """Append to log (must be called from main thread)"""
        self.log_text.AppendText(message + "\n")

    def set_status(self, message):
        """Update status label"""
        wx.CallAfter(self.status_text.SetLabel, message)

    def set_progress(self, value):
        """Update progress bar (0-100)"""
        wx.CallAfter(self.progress.SetValue, value)

    def _on_update(self, event):
        """Start update process"""
        self.update_btn.Enable(False)
        self.log_text.Clear()
        self.progress.SetValue(0)

        # Run update in background thread
        thread = threading.Thread(target=self._sync_from_github)
        thread.daemon = True
        thread.start()

    def _sync_from_github(self):
        """Download/update files from the GitHub repo"""
        try:
            self.log("Connecting to GitHub...")
            self.set_status("Connecting to GitHub...")
            self.set_progress(10)

            tree = _fetch_tree()
            if tree is None:
                self.log("Could not reach GitHub. Please check your internet "
                         "connection and try again.")
                self.set_status("Could not reach GitHub - try again later")
                self.set_progress(0)
                wx.CallAfter(self.update_btn.Enable, True)
                return

            updated_files = []
            new_files = []
            unchanged_files = []
            skipped_files = []

            total_files = len(FILES_TO_SYNC)

            for i, filename in enumerate(FILES_TO_SYNC):
                progress = 10 + int((i / total_files) * 80)
                self.set_progress(progress)
                self.set_status(f"Checking {filename}...")

                local_path = LOCAL_DIR / filename

                # Some files are not in the GitHub repo (the sounds and the
                # tools programs). Leave the local copy alone and say so.
                remote_sha = tree.get(filename)
                if remote_sha is None:
                    skipped_files.append(filename)
                    self.log(f"Not in the GitHub repo, left alone: {filename}")
                    continue

                try:
                    # Create parent directory if needed
                    local_path.parent.mkdir(parents=True, exist_ok=True)

                    # Download to temp file first
                    temp_path = LOCAL_DIR / f"{filename}.tmp"

                    self.log(f"Downloading {filename}...")
                    download_file(RAW_BASE + filename, temp_path)

                    # Only trust the download if it matches GitHub exactly
                    if _git_blob_sha(temp_path.read_bytes()) != remote_sha:
                        self.log(f"Download did not match GitHub, skipped: {filename}")
                        os.remove(temp_path)
                        continue

                    old_hash = get_file_hash(local_path)

                    if old_hash is None:
                        # New file
                        if local_path.exists():
                            os.remove(local_path)
                        os.rename(temp_path, local_path)
                        new_files.append(filename)
                        self.log(f"New file: {filename}")
                    elif _local_blob_sha(temp_path) != _local_blob_sha(local_path):
                        # Updated file - remove old one first
                        if local_path.exists():
                            os.remove(local_path)
                        os.rename(temp_path, local_path)
                        updated_files.append(filename)
                        self.log(f"Updated: {filename}")
                    else:
                        # Unchanged
                        os.remove(temp_path)
                        unchanged_files.append(filename)

                except Exception as e:
                    self.log(f"Error syncing {filename}: {e}")
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

            self.set_progress(100)

            # Summary
            self.log("\n=== Update Complete ===")
            if new_files:
                self.log(f"New files: {', '.join(new_files)}")
            if updated_files:
                self.log(f"Updated: {', '.join(updated_files)}")
            if unchanged_files:
                self.log(f"Unchanged: {len(unchanged_files)} files")
            if skipped_files:
                self.log(f"Not in the GitHub repo, left alone: {len(skipped_files)} files")

            if new_files or updated_files:
                self.set_status("Update complete! Program has been updated.")
                self.log("\nProgram updated! You can now run main.py")
            else:
                self.set_status("All files are up to date!")
                self.log("\nAll files are up to date!")

        except Exception as e:
            self.log(f"\nError: {e}")
            self.log("\nMake sure you have:")
            self.log("1. Internet connection")
            self.log("2. Write permissions in this folder")
            self.set_status("Update failed - see log for details")
            self.set_progress(0)

        wx.CallAfter(self.update_btn.Enable, True)

def main():
    app = wx.App()
    frame = UpdateFrame()
    frame.Show()
    app.MainLoop()

if __name__ == "__main__":
    main()

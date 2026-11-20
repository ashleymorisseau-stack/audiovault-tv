import os
import hashlib
import wx
import threading
import urllib.request
from pathlib import Path

# Configuration
BUCKET_NAME = "mp3-player-updates"
S3_PREFIX = "mp3-player/"
BASE_URL = f"https://{BUCKET_NAME}.s3.amazonaws.com/{S3_PREFIX}"
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

def download_file(url, local_path):
    """Download file from URL"""
    urllib.request.urlretrieve(url, local_path)

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
        thread = threading.Thread(target=self._sync_from_s3)
        thread.daemon = True
        thread.start()
    
    def _sync_from_s3(self):
        """Download/update files from S3"""
        try:
            self.log("Connecting to S3...")
            self.set_status("Connecting to S3...")
            self.set_progress(10)
            
            updated_files = []
            new_files = []
            unchanged_files = []
            
            total_files = len(FILES_TO_SYNC)
            
            for i, filename in enumerate(FILES_TO_SYNC):
                progress = 10 + int((i / total_files) * 80)
                self.set_progress(progress)
                self.set_status(f"Checking {filename}...")
                
                file_url = f"{BASE_URL}{filename}"
                local_path = LOCAL_DIR / filename
                
                try:
                    # Create parent directory if needed
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Download to temp file first
                    temp_path = LOCAL_DIR / f"{filename}.tmp"
                    
                    self.log(f"Downloading {filename}...")
                    download_file(file_url, temp_path)
                    
                    # Check if file changed
                    new_hash = get_file_hash(temp_path)
                    old_hash = get_file_hash(local_path)
                    
                    if old_hash is None:
                        # New file
                        if local_path.exists():
                            os.remove(local_path)
                        os.rename(temp_path, local_path)
                        new_files.append(filename)
                        self.log(f"✓ New file: {filename}")
                    elif new_hash != old_hash:
                        # Updated file - remove old one first
                        if local_path.exists():
                            os.remove(local_path)
                        os.rename(temp_path, local_path)
                        updated_files.append(filename)
                        self.log(f"✓ Updated: {filename}")
                    else:
                        # Unchanged
                        os.remove(temp_path)
                        unchanged_files.append(filename)
                        
                except urllib.error.HTTPError as e:
                    self.log(f"Error downloading {filename}: {e}")
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
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
            
            if new_files or updated_files:
                self.set_status("Update complete! Program has been updated.")
                self.log("\n✓ Program updated! You can now run main.py")
            else:
                self.set_status("All files are up to date!")
                self.log("\n✓ All files are up to date!")
                
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


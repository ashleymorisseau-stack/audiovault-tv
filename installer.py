"""
AudioVault TV Installer
Downloads and installs all program files with a GUI progress display.
Requires: pip install wxPython requests
"""

import os
import sys
import threading
import urllib.request
from pathlib import Path

try:
    import wx
except ImportError:
    print("Installing wxPython...")
    os.system(f"{sys.executable} -m pip install wxPython")
    import wx

INSTALL_DIR = Path.home() / "AudioVault TV"
BASE_URL = "https://mp3-player-updates.s3.amazonaws.com/mp3-player/"

FILES = [
    "main.py",
    "audio_player.py",
    "playlist_manager.py",
    "channel_manager.py",
    "voice_control.py",
    "player_logger.py",
    "audiovault_client.py",
    "youtube_client.py",
    "auto_updater.py",
    "requirements.txt",
    "README.md",
    "sounds/startup.mp3",
    "sounds/outro.mp3",
    "sounds/start_of_request.wav",
    "sounds/end_of_request.wav",
    "sounds/remote.mp3",
    "tools/ffmpeg.exe",
    "tools/ffprobe.exe",
]


class InstallerFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="AudioVault TV Installer", size=(500, 350))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(panel, label="AudioVault TV Installer")
        font = title.GetFont().Bold()
        font.SetPointSize(font.GetPointSize() + 4)
        title.SetFont(font)
        sizer.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 15)

        sizer.Add(wx.StaticText(panel, label=f"Install to: {INSTALL_DIR}"), 0, wx.LEFT | wx.RIGHT, 15)

        self.status = wx.StaticText(panel, label="Ready to install.")
        sizer.Add(self.status, 0, wx.ALL, 15)

        self.progress = wx.Gauge(panel, range=100)
        sizer.Add(self.progress, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, 15)

        self.log = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY)
        sizer.Add(self.log, 1, wx.ALL | wx.EXPAND, 15)

        self.install_btn = wx.Button(panel, label="Install")
        self.install_btn.Bind(wx.EVT_BUTTON, self._on_install)
        sizer.Add(self.install_btn, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        panel.SetSizer(sizer)
        self.Centre()

    def _log(self, msg):
        wx.CallAfter(self.log.AppendText, msg + "\n")

    def _set_status(self, msg):
        wx.CallAfter(self.status.SetLabel, msg)

    def _set_progress(self, value):
        wx.CallAfter(self.progress.SetValue, value)

    def _on_install(self, event):
        self.install_btn.Enable(False)
        threading.Thread(target=self._install_thread, daemon=True).start()

    def _install_thread(self):
        try:
            # Create directories
            self._set_status("Creating directories...")
            self._log(f"Install directory: {INSTALL_DIR}")
            INSTALL_DIR.mkdir(exist_ok=True)
            (INSTALL_DIR / "sounds").mkdir(exist_ok=True)
            (INSTALL_DIR / "tools").mkdir(exist_ok=True)
            (INSTALL_DIR / "Downloads").mkdir(exist_ok=True)

            # Download files
            total = len(FILES)
            for i, filename in enumerate(FILES):
                pct = int(((i) / total) * 90)
                self._set_progress(pct)
                self._set_status(f"Downloading: {filename}")
                self._log(f"Downloading {filename}...")

                url = BASE_URL + filename
                dest = INSTALL_DIR / filename
                dest.parent.mkdir(parents=True, exist_ok=True)

                try:
                    urllib.request.urlretrieve(url, str(dest))
                except Exception as e:
                    self._log(f"  WARNING: Failed to download {filename}: {e}")

            # Create desktop shortcut
            self._set_progress(95)
            self._set_status("Creating desktop shortcut...")
            shortcut = Path.home() / "Desktop" / "AudioVault TV.bat"
            shortcut.write_text(f'@echo off\ncd /d "{INSTALL_DIR}"\npython main.py\n')
            self._log(f"Desktop shortcut created: {shortcut}")

            # Done
            self._set_progress(100)
            self._set_status("Installation complete!")
            self._log("")
            self._log("=" * 40)
            self._log("Installation complete!")
            self._log(f"Program installed to: {INSTALL_DIR}")
            self._log("Double-click 'AudioVault TV' on your desktop to run.")
            self._log("")
            self._log("Note: For voice control, download the Vosk model:")
            self._log("  https://alphacephei.com/vosk/models")
            self._log("  Extract vosk-model-small-en-us-0.15 to the install folder.")

            wx.CallAfter(wx.MessageBox,
                         "Installation complete!\n\nDouble-click 'AudioVault TV' on your desktop to run.",
                         "Success", wx.OK | wx.ICON_INFORMATION)

        except Exception as e:
            self._set_status(f"Installation failed: {e}")
            self._log(f"\nERROR: {e}")

        wx.CallAfter(self.install_btn.Enable, True)


def main():
    app = wx.App()
    InstallerFrame().Show()
    app.MainLoop()


if __name__ == "__main__":
    main()

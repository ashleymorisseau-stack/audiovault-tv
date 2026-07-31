"""
Browse and download TV remote click sounds from FreeSound.org
"""

import os
import requests
import wx
import threading
from pathlib import Path

SOUNDS_DIR = Path(__file__).parent / "Sounds"
CONFIG_FILE = Path(__file__).parent / "config.ini"
API_BASE = "https://freesound.org/apiv2"


def load_api_key():
    import configparser
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    try:
        return config["freesound"]["api_key"]
    except KeyError:
        return None


def save_api_key(key):
    import configparser
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if "freesound" not in config:
        config["freesound"] = {}
    config["freesound"]["api_key"] = key
    with open(CONFIG_FILE, "w") as f:
        config.write(f)


def search_sounds(query, api_key, page=1):
    """Search FreeSound. Returns list of sound dicts."""
    r = requests.get(f"{API_BASE}/search/text/", params={
        "query": query,
        "token": api_key,
        "fields": "id,name,duration,license,previews,download",
        "page_size": 15,
        "page": page,
        "filter": "duration:[0 TO 5]",  # Keep clips short
    })
    r.raise_for_status()
    return r.json().get("results", [])


def download_sound(sound, api_key, dest_name):
    """Download a sound's HQ preview (no OAuth needed)."""
    preview_url = sound["previews"].get("preview-hq-mp3") or sound["previews"].get("preview-lq-mp3")
    if not preview_url:
        return None
    SOUNDS_DIR.mkdir(exist_ok=True)
    dest = SOUNDS_DIR / dest_name
    r = requests.get(f"{preview_url}?token={api_key}", stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    return dest


class FreesoundBrowser(wx.Frame):
    def __init__(self):
        super().__init__(None, title="FreeSound Remote Sound Browser", size=(600, 500))
        self.api_key = load_api_key()
        self.results = []
        self._build_ui()
        if not self.api_key:
            wx.CallAfter(self._prompt_api_key)

    def _build_ui(self):
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Search row
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.search_ctrl = wx.TextCtrl(panel, value="TV remote click", style=wx.TE_PROCESS_ENTER)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        row.Add(wx.StaticText(panel, label="Search:"), 0, wx.ALIGN_CENTER | wx.RIGHT, 5)
        row.Add(self.search_ctrl, 1, wx.EXPAND)
        btn = wx.Button(panel, label="Search")
        btn.Bind(wx.EVT_BUTTON, self._on_search)
        row.Add(btn, 0, wx.LEFT, 5)
        sizer.Add(row, 0, wx.ALL | wx.EXPAND, 8)

        # Results list
        self.list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list.AppendColumn("Name", width=300)
        self.list.AppendColumn("Duration", width=80)
        self.list.AppendColumn("License", width=150)
        sizer.Add(self.list, 1, wx.ALL | wx.EXPAND, 8)

        # Buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        preview_btn = wx.Button(panel, label="Preview")
        preview_btn.Bind(wx.EVT_BUTTON, self._on_preview)
        download_btn = wx.Button(panel, label="Download")
        download_btn.Bind(wx.EVT_BUTTON, self._on_download)
        btn_row.Add(preview_btn, 0, wx.RIGHT, 8)
        btn_row.Add(download_btn, 0)
        sizer.Add(btn_row, 0, wx.ALL | wx.ALIGN_CENTER, 8)

        self.status = wx.StaticText(panel, label="Enter a search term and press Search.")
        sizer.Add(self.status, 0, wx.ALL, 8)

        panel.SetSizer(sizer)
        self.Centre()

    def _prompt_api_key(self):
        dlg = wx.TextEntryDialog(self, "Enter your FreeSound API key:", "API Key")
        if dlg.ShowModal() == wx.ID_OK:
            self.api_key = dlg.GetValue().strip()
            save_api_key(self.api_key)
        dlg.Destroy()

    def _on_search(self, event):
        query = self.search_ctrl.GetValue().strip()
        if not query or not self.api_key:
            return
        self.status.SetLabel("Searching...")
        self.list.DeleteAllItems()
        threading.Thread(target=self._search_thread, args=(query,), daemon=True).start()

    def _search_thread(self, query):
        try:
            results = search_sounds(query, self.api_key)
            wx.CallAfter(self._show_results, results)
        except Exception as e:
            wx.CallAfter(self.status.SetLabel, f"Error: {e}")

    def _show_results(self, results):
        self.results = results
        self.list.DeleteAllItems()
        for s in results:
            idx = self.list.InsertItem(self.list.GetItemCount(), s["name"])
            self.list.SetItem(idx, 1, f"{s['duration']:.1f}s")
            self.list.SetItem(idx, 2, s["license"].split("/")[-2] if "/" in s["license"] else s["license"])
        self.status.SetLabel(f"Found {len(results)} results (max 5 seconds each).")

    def _selected_sound(self):
        idx = self.list.GetFirstSelected()
        if idx == -1:
            wx.MessageBox("Select a sound first.", "No Selection", wx.OK)
            return None
        return self.results[idx]

    def _on_preview(self, event):
        sound = self._selected_sound()
        if not sound:
            return
        url = sound["previews"].get("preview-hq-mp3") or sound["previews"].get("preview-lq-mp3")
        if not url:
            return
        self.status.SetLabel(f"Previewing: {sound['name']}...")
        threading.Thread(target=self._preview_thread, args=(f"{url}?token={self.api_key}",), daemon=True).start()

    def _preview_thread(self, url):
        try:
            import pygame
            import io
            r = requests.get(url)
            r.raise_for_status()
            pygame.mixer.init()
            pygame.mixer.music.load(io.BytesIO(r.content))
            pygame.mixer.music.play()
            wx.CallAfter(self.status.SetLabel, "Playing preview...")
        except Exception as e:
            wx.CallAfter(self.status.SetLabel, f"Preview error: {e}")

    def _on_download(self, event):
        sound = self._selected_sound()
        if not sound:
            return
        # Ask what to save it as
        safe_name = "".join(c for c in sound["name"] if c.isalnum() or c in " _-").strip()
        dlg = wx.TextEntryDialog(self, "Save as (filename):", "Download Sound", f"{safe_name}.mp3")
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dest_name = dlg.GetValue().strip()
        dlg.Destroy()
        if not dest_name:
            return
        self.status.SetLabel(f"Downloading {sound['name']}...")
        threading.Thread(target=self._download_thread, args=(sound, dest_name), daemon=True).start()

    def _download_thread(self, sound, dest_name):
        try:
            dest = download_sound(sound, self.api_key, dest_name)
            wx.CallAfter(self.status.SetLabel, f"Saved to: {dest}")
        except Exception as e:
            wx.CallAfter(self.status.SetLabel, f"Download error: {e}")


def main():
    app = wx.App()
    FreesoundBrowser().Show()
    app.MainLoop()


if __name__ == "__main__":
    main()

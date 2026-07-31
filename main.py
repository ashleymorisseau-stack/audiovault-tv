import time
print(f"[{time.strftime('%H:%M:%S')}] Starting AudioVault TV...")

print("Loading wx...", flush=True)
import wx
print("Loading standard libs...", flush=True)
import os
import json
import threading
from pathlib import Path

print("Loading audio player...", flush=True)
from audio_player import AudioPlayer
print("Loading playlist manager...", flush=True)
from playlist_manager import PlaylistManager
print("Loading channel manager...", flush=True)
from channel_manager import ChannelManager
print("Loading voice control...", flush=True)
from voice_control import VoiceControl
print("Loading logger...", flush=True)
from player_logger import PlayerLogger
print("Loading AudioVault client...", flush=True)
import audiovault_client as av
print("Loading YouTube client...", flush=True)
try:
    import youtube_client as yt
    YT_AVAILABLE = True
except ImportError:
    yt = None
    YT_AVAILABLE = False
    print("  YouTube client not available")

print(f"[{time.strftime('%H:%M:%S')}] All modules loaded.", flush=True)

# NVDA integration
nvda = None
NVDA_AVAILABLE = False
try:
    import ctypes
    nvda = ctypes.windll.LoadLibrary("./nvdaControllerClient.dll")
    res = nvda.nvdaController_testIfRunning()
    if res == 0:
        NVDA_AVAILABLE = True
except Exception:
    pass

def speak(text):
    """Speak text through NVDA if available"""
    if NVDA_AVAILABLE and nvda:
        try:
            nvda.nvdaController_speakText(text)
        except Exception:
            pass

class PlayerFrame(wx.Frame):
    def __init__(self):
        import time
        t0 = time.time()
        super().__init__(None, title="AudioVault TV", size=(600, 400))
        
        # Initialize logger
        self.logger = PlayerLogger(Path.home() / "mp3_player_log.txt")
        
        self.player = AudioPlayer()
        self.playlist = PlaylistManager()
        self.channels = ChannelManager(Path.home() / ".mp3_player_channels.json")
        
        t1 = time.time()
        self.logger.log_playback("STARTUP", f"Basic init: {t1-t0:.2f}s")
        
        # Initialize voice control
        try:
            self.voice = VoiceControl()
            self.voice_available = True
        except Exception as e:
            print(f"Voice control not available: {e}")
            self.voice = None
            self.voice_available = False
        
        t2 = time.time()
        self.logger.log_playback("STARTUP", f"Voice init: {t2-t1:.2f}s")
        
        self.is_voice_listening = False
        self.wake_word_mode = False
        self.wake_word_thread = None
        self.is_switching_channels = False  # Flag to prevent multiple channel switches
        self.vault_logged_in = False
        
        self._create_ui()
        self._bind_hotkeys()
        
        t3 = time.time()
        self.logger.log_playback("STARTUP", f"UI created: {t3-t2:.2f}s")
        
        self._load_current_channel()
        
        t4 = time.time()
        self.logger.log_playback("STARTUP", f"Channel loaded: {t4-t3:.2f}s")
        
        # Check for data corruption after startup
        wx.CallAfter(self._check_channel_integrity)
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer)
        self.timer.Start(100)  # Check every 100ms
        
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._update_title()
        
        # Play startup sound
        self._play_startup_sound()
        
        self.logger.log_playback("STARTUP", f"Total startup: {time.time()-t0:.2f}s")
        
        # Defer slow operations until after window shows
        wx.CallAfter(self._vault_auto_login)
        
        # Show greeting dialog after a short delay
        wx.CallLater(1000, self._show_greeting_dialog)
    
    def _create_ui(self):
        """Create accessible UI with menu bar"""
        # Create menu bar
        menubar = wx.MenuBar()
        
        # File menu
        file_menu = wx.Menu()
        select_item = file_menu.Append(wx.ID_ANY, "Select Folders\tCtrl+O", "Select folders to play")
        self.Bind(wx.EVT_MENU, self._on_select_folders, select_item)
        select_recursive_item = file_menu.Append(wx.ID_ANY, "Select Folder (with subfolders)\tCtrl+Shift+O", "Select folder and include all subfolders")
        self.Bind(wx.EVT_MENU, self._on_select_folder_recursive, select_recursive_item)
        file_menu.AppendSeparator()
        upload_log_item = file_menu.Append(wx.ID_ANY, "Upload Log\tCtrl+Shift+U", "Upload log file for troubleshooting")
        self.Bind(wx.EVT_MENU, self._on_upload_log, upload_log_item)
        file_menu.AppendSeparator()
        set_movies_dir = file_menu.Append(wx.ID_ANY, "Set Default Movies Folder", "Set default download folder for movies")
        self.Bind(wx.EVT_MENU, lambda e: self._on_set_default_folder("movies"), set_movies_dir)
        set_shows_dir = file_menu.Append(wx.ID_ANY, "Set Default TV Shows Folder", "Set default download folder for TV shows")
        self.Bind(wx.EVT_MENU, lambda e: self._on_set_default_folder("shows"), set_shows_dir)
        file_menu.AppendSeparator()
        restore_item = file_menu.Append(wx.ID_ANY, "Restore Channel Backup\tCtrl+Shift+R", "Restore channels from a backup")
        self.Bind(wx.EVT_MENU, self._on_restore_backup, restore_item)
        file_menu.AppendSeparator()
        quit_item = file_menu.Append(wx.ID_EXIT, "Quit\tCtrl+Q", "Quit without outro")
        self.Bind(wx.EVT_MENU, self._on_quick_quit, quit_item)
        menubar.Append(file_menu, "&File")
        
        # Channels menu
        channels_menu = wx.Menu()
        new_channel_item = channels_menu.Append(wx.ID_ANY, "New Channel\tCtrl+T", "Create a new channel")
        self.Bind(wx.EVT_MENU, self._on_new_channel, new_channel_item)
        rename_channel_item = channels_menu.Append(wx.ID_ANY, "Rename Channel\tCtrl+R", "Rename current channel")
        self.Bind(wx.EVT_MENU, self._on_rename_channel, rename_channel_item)
        delete_channel_item = channels_menu.Append(wx.ID_ANY, "Delete Channel\tCtrl+D", "Delete current channel")
        self.Bind(wx.EVT_MENU, self._on_delete_channel, delete_channel_item)
        channels_menu.AppendSeparator()
        list_channels_item = channels_menu.Append(wx.ID_ANY, "List Channels\tCtrl+L", "Show list of all channels")
        self.Bind(wx.EVT_MENU, self._on_list_channels, list_channels_item)
        channels_menu.AppendSeparator()
        channels_menu.Append(wx.ID_ANY, "Next Channel\tCtrl+Tab", "Switch to next channel")
        channels_menu.Append(wx.ID_ANY, "Previous Channel\tCtrl+Shift+Tab", "Switch to previous channel")
        menubar.Append(channels_menu, "&Channels")
        
        # Controls menu
        controls_menu = wx.Menu()
        controls_menu.Append(wx.ID_ANY, "Play/Pause\tSpace", "Toggle playback")
        controls_menu.Append(wx.ID_ANY, "Previous File\tLeft", "Go to previous file")
        controls_menu.Append(wx.ID_ANY, "Next File\tRight", "Go to next file")
        controls_menu.Append(wx.ID_ANY, "Previous Folder\tCtrl+Left", "Go to previous folder")
        controls_menu.Append(wx.ID_ANY, "Next Folder\tCtrl+Right", "Go to next folder")
        controls_menu.Append(wx.ID_ANY, "Rewind 10s\tShift+Left", "Rewind 10 seconds")
        controls_menu.Append(wx.ID_ANY, "Fast Forward 10s\tShift+Right", "Fast forward 10 seconds")
        controls_menu.AppendSeparator()
        set_bookmark_item = controls_menu.Append(wx.ID_ANY, "Set Bookmark\tCtrl+S", "Create bookmark at current position")
        self.Bind(wx.EVT_MENU, self._on_set_bookmark, set_bookmark_item)
        jump_bookmark_item = controls_menu.Append(wx.ID_ANY, "Jump to Bookmark\tCtrl+J", "Jump to a saved bookmark")
        self.Bind(wx.EVT_MENU, self._on_jump_bookmark, jump_bookmark_item)
        controls_menu.AppendSeparator()
        voice_listen_item = controls_menu.Append(wx.ID_ANY, "Voice Command (One-time)\tCtrl+Shift+B", "Listen for one voice command")
        self.Bind(wx.EVT_MENU, self._toggle_voice_listening, voice_listen_item)
        wake_word_item = controls_menu.Append(wx.ID_ANY, "Wake Word Mode\tCtrl+Shift+W", "Toggle continuous wake word listening")
        self.Bind(wx.EVT_MENU, self._toggle_wake_word_mode, wake_word_item)
        controls_menu.AppendSeparator()
        toggle_sounds_item = controls_menu.Append(wx.ID_ANY, "Toggle Sounds\tCtrl+Shift+S", "Turn startup/exit sounds on or off")
        self.Bind(wx.EVT_MENU, self._toggle_sounds, toggle_sounds_item)
        menubar.Append(controls_menu, "&Controls")
        
        # AudioVault menu
        vault_menu = wx.Menu()
        self.vault_login_item = vault_menu.Append(wx.ID_ANY, "Login\tCtrl+Shift+L", "Login to AudioVault")
        self.Bind(wx.EVT_MENU, self._on_vault_login_toggle, self.vault_login_item)
        vault_menu.AppendSeparator()
        search_movies_item = vault_menu.Append(wx.ID_ANY, "Search Movies\tCtrl+Shift+F", "Search AudioVault movies")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_search(e, "movies"), search_movies_item)
        search_shows_item = vault_menu.Append(wx.ID_ANY, "Search TV Shows\tCtrl+Shift+T", "Search AudioVault TV shows")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_search(e, "shows"), search_shows_item)
        vault_menu.AppendSeparator()
        recent_movies_item = vault_menu.Append(wx.ID_ANY, "Recent Movies\tCtrl+Shift+M", "View recently added movies")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_recents(e, "movies"), recent_movies_item)
        recent_shows_item = vault_menu.Append(wx.ID_ANY, "Recent TV Shows\tCtrl+Shift+N", "View recently added shows")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_recents(e, "shows"), recent_shows_item)
        menubar.Append(vault_menu, "&AudioVault")
        
        # YouTube menu
        if YT_AVAILABLE:
            yt_menu = wx.Menu()
            yt_search_item = yt_menu.Append(wx.ID_ANY, "Search YouTube\tCtrl+Y", "Search and download from YouTube")
            self.Bind(wx.EVT_MENU, self._on_yt_search, yt_search_item)
            yt_url_item = yt_menu.Append(wx.ID_ANY, "Download from URL\tCtrl+Shift+Y", "Download audio from a YouTube URL")
            self.Bind(wx.EVT_MENU, self._on_yt_url, yt_url_item)
            yt_folder_item = yt_menu.Append(wx.ID_ANY, "Set Download Folder", "Set default YouTube download folder")
            self.Bind(wx.EVT_MENU, self._on_yt_set_folder, yt_folder_item)
            menubar.Append(yt_menu, "&YouTube")
        
        self.SetMenuBar(menubar)
        
        # Main panel
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Channel display
        sizer.Add(wx.StaticText(panel, label="Current Channel:"), 0, wx.LEFT | wx.TOP, 10)
        self.channel_label = wx.StaticText(panel, label="No channel")
        sizer.Add(self.channel_label, 0, wx.ALL, 10)
        
        # Current folder display
        sizer.Add(wx.StaticText(panel, label="Current Folder:"), 0, wx.LEFT | wx.TOP, 10)
        self.folder_label = wx.StaticText(panel, label="No folder selected")
        sizer.Add(self.folder_label, 0, wx.ALL, 10)
        
        # Current file display
        sizer.Add(wx.StaticText(panel, label="Current File:"), 0, wx.LEFT | wx.TOP, 10)
        self.file_label = wx.StaticText(panel, label="No file loaded")
        sizer.Add(self.file_label, 0, wx.ALL, 10)
        
        # Position display
        sizer.Add(wx.StaticText(panel, label="Position:"), 0, wx.LEFT | wx.TOP, 10)
        self.position_label = wx.StaticText(panel, label="0:00")
        sizer.Add(self.position_label, 0, wx.ALL, 10)
        
        # Status display
        self.status_label = wx.StaticText(panel, label="Press Ctrl+T to create a channel")
        sizer.Add(self.status_label, 0, wx.ALL, 10)
        
        panel.SetSizer(sizer)
    
    def _bind_hotkeys(self):
        """Bind keyboard shortcuts"""
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
    
    def _on_key(self, event):
        """Handle keyboard events"""
        keycode = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        
        if keycode == wx.WXK_SPACE:
            self._toggle_play_pause()
        elif keycode == wx.WXK_TAB and ctrl:
            if shift:
                self._prev_channel()
            else:
                self._next_channel()
        elif keycode == ord('B') and ctrl and shift:
            self._toggle_voice_listening()
        elif keycode == ord('W') and ctrl and shift:
            self._toggle_wake_word_mode()
        elif keycode == ord('S') and ctrl and not shift:
            self._on_set_bookmark(None)
        elif keycode == ord('J') and ctrl:
            self._on_jump_bookmark(None)
        elif keycode == wx.WXK_LEFT:
            if ctrl:
                self._prev_folder()
            elif shift:
                self._rewind()
            else:
                self._prev_file()
        elif keycode == wx.WXK_RIGHT:
            if ctrl:
                self._next_folder()
            elif shift:
                self._fastforward()
            else:
                self._next_file()
        else:
            event.Skip()
    
    def _on_select_folders(self, event):
        """Open folder selection dialog"""
        if not self.channels.current_channel:
            wx.MessageBox("Please create a channel first (Ctrl+T)", "No Channel", wx.OK | wx.ICON_INFORMATION)
            return
        
        folders = []
        
        while True:
            dlg = wx.DirDialog(self, "Select a folder with MP3 files", style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            
            if dlg.ShowModal() == wx.ID_OK:
                folders.append(dlg.GetPath())
                dlg.Destroy()
                
                result = wx.MessageBox("Add another folder?", "Continue", wx.YES_NO | wx.ICON_QUESTION)
                if result != wx.YES:
                    break
            else:
                dlg.Destroy()
                break
        
        if folders:
            self.playlist.add_folders(folders)
            self._load_current_file()
            self._update_display()
            self.channels.update_current_channel(folders=folders)
            self.status_label.SetLabel(f"Loaded {len(folders)} folder(s) with {len(self.playlist.playlist)} files total")
            self._toggle_play_pause()
    
    def _on_select_folder_recursive(self, event):
        """Open folder selection dialog and include all subfolders"""
        if not self.channels.current_channel:
            wx.MessageBox("Please create a channel first (Ctrl+T)", "No Channel", wx.OK | wx.ICON_INFORMATION)
            return
        
        dlg = wx.DirDialog(self, "Select Folder (all subfolders will be included)", style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        
        if dlg.ShowModal() == wx.ID_OK:
            parent_folder = Path(dlg.GetPath())
            # Get all subfolders that contain MP3 files
            from playlist_manager import natural_sort_key
            subfolders = []
            for subfolder in sorted(parent_folder.rglob("*"), key=lambda x: natural_sort_key(str(x))):
                if subfolder.is_dir():
                    # Check if this folder has MP3 files
                    if any(f.suffix.lower() == '.mp3' for f in subfolder.iterdir() if f.is_file()):
                        subfolders.append(str(subfolder))
            
            if subfolders:
                self.playlist.add_folders(subfolders)
                self._load_current_file()
                self._update_display()
                self.channels.update_current_channel(folders=subfolders)
                self.status_label.SetLabel(f"Loaded {len(subfolders)} subfolder(s) with {len(self.playlist.playlist)} files total")
                self._toggle_play_pause()
            else:
                self.status_label.SetLabel("No subfolders with MP3 files found")
        
        dlg.Destroy()
    
    def _load_current_file(self):
        """Load current file from playlist"""
        current = self.playlist.get_current()
        if current:
            filepath = current[1]
            try:
                if self.player.load(str(filepath)):
                    self._update_display()
                    return True
            except Exception as e:
                self.status_label.SetLabel(f"Error loading file: {e}")
                return False
        return False
    
    def _toggle_play_pause(self):
        """Toggle play/pause"""
        if not self.playlist.get_current():
            msg = "No files loaded. Use Ctrl+O to select folders."
            self.status_label.SetLabel(msg)
            speak(msg)
            return
        
        if self.player.is_playing:
            self.player.pause()
            msg = f"Paused: {self.playlist.get_current_file_name()}"
            self.status_label.SetLabel(msg)
            speak(msg)
        else:
            # If no file loaded yet, load it first
            if not self.player.current_file:
                if self._load_current_file():
                    self.player.play()
                    msg = f"Playing: {self.playlist.get_current_file_name()}"
                    self.status_label.SetLabel(msg)
                    speak(msg)
            else:
                self.player.unpause()
                msg = f"Playing: {self.playlist.get_current_file_name()}"
                self.status_label.SetLabel(msg)
                speak(msg)
    
    def _next_file(self):
        """Go to next file"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.next_file():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("NEXT FILE", old_file, new_file)
            msg = f"Next file: {folder} - {file}"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _prev_file(self):
        """Go to previous file"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.prev_file():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("PREV FILE", old_file, new_file)
            msg = f"Previous file: {folder} - {file}"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _next_folder(self):
        """Go to next folder"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.next_folder():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("NEXT FOLDER", old_file, new_file)
            msg = f"Next folder: {folder} - {file}"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _prev_folder(self):
        """Go to previous folder"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.prev_folder():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("PREV FOLDER", old_file, new_file)
            msg = f"Previous folder: {folder} - {file}"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _rewind(self):
        """Rewind 10 seconds"""
        self.player.rewind(10)
        pos = self.player.get_position()
        minutes = int(pos // 60)
        seconds = int(pos % 60)
        msg = f"Rewind to {minutes}:{seconds:02d}"
        self.status_label.SetLabel(msg)
        speak(msg)
    
    def _fastforward(self):
        """Fast forward 10 seconds"""
        self.player.fastforward(10)
        pos = self.player.get_position()
        minutes = int(pos // 60)
        seconds = int(pos % 60)
        msg = f"Fast forward to {minutes}:{seconds:02d}"
        self.status_label.SetLabel(msg)
        speak(msg)
    
    def _on_clear_all(self, event):
        """Clear all folders and stop playback"""
        self.player.stop()
        self.playlist.folders = []
        self.playlist.playlist = []
        self.playlist.current_index = 0
        self.folder_label.SetLabel("No folder selected")
        self.file_label.SetLabel("No file loaded")
        self.position_label.SetLabel("0:00")
        self.SetTitle("AudioVault TV")
        self.status_label.SetLabel("Cleared. Press Ctrl+O to select folders.")
    
    def _update_display(self):
        """Update UI labels and title bar"""
        folder_name = self.playlist.get_current_folder_name()
        file_name = self.playlist.get_current_file_name()
        
        self.folder_label.SetLabel(folder_name if folder_name else "No folder selected")
        self.file_label.SetLabel(file_name if file_name else "No file loaded")
        self.channel_label.SetLabel(self.channels.current_channel or "No channel")
    
    def _update_title(self):
        """Update window title with current channel"""
        if self.channels.current_channel:
            self.SetTitle(f"AudioVault TV - {self.channels.current_channel}")
        else:
            self.SetTitle("AudioVault TV")
    
    def _save_current_channel_state(self):
        """Save current playback state to channel"""
        if self.channels.current_channel and self.playlist.get_current():
            current_position = self.player.get_position()
            self.channels.update_current_channel(
                current_index=self.playlist.current_index,
                position=current_position
            )
            # Log what we're saving
            minutes = int(current_position // 60)
            seconds = int(current_position % 60)
            file_name = self.playlist.get_current_file_name()
            self.logger.log_channel("SAVED", self.channels.current_channel, f"File: {file_name}, Position: {minutes}:{seconds:02d}")
    
    def _load_current_channel(self):
        """Load current channel data"""
        if not self.channels.has_channels():
            return
        
        channel_data = self.channels.get_current_channel_data()
        if channel_data and channel_data['folders']:
            # Use cached playlist if available, otherwise scan folders
            cached_playlist = channel_data.get('cached_playlist')
            if cached_playlist:
                self.playlist.load_from_cache(channel_data['folders'], cached_playlist)
            else:
                self.playlist.add_folders(channel_data['folders'])
                # Save cache for next time
                self.channels.update_current_channel(cached_playlist=self.playlist.get_cache_data())

            self.playlist.set_index(channel_data.get('current_index', 0))
            self._load_current_file()
            saved_position = channel_data.get('position', 0)
            self.player.paused_position = saved_position
            self._update_display()
            
            # Show position info
            minutes = int(saved_position // 60)
            seconds = int(saved_position % 60)
            file_name = self.playlist.get_current_file_name()
            msg = f"Loaded {self.channels.current_channel}: {file_name} at {minutes}:{seconds:02d}. Press Space to play."
            self.status_label.SetLabel(msg)
            self.logger.log_channel("LOADED", self.channels.current_channel, f"File: {file_name}, Position: {minutes}:{seconds:02d}")
    
    def _on_restore_backup(self, event):
        """Restore channels from a backup"""
        backups = self.channels.get_backups()
        if not backups:
            msg = "No backups available."
            wx.MessageBox(msg, "No Backups", wx.OK | wx.ICON_INFORMATION)
            speak(msg)
            return

        items = [display for _, display in backups]
        dlg = wx.SingleChoiceDialog(self, "Select a backup to restore:", "Restore Channel Backup", items)
        if dlg.ShowModal() == wx.ID_OK:
            idx = dlg.GetSelection()
            backup_path = backups[idx][0]
            dlg.Destroy()

            confirm = wx.MessageBox(
                f"Restore backup from {items[idx]}?\n\nThis will replace your current channel list.",
                "Confirm Restore",
                wx.YES_NO | wx.ICON_WARNING
            )
            if confirm == wx.YES:
                if self.channels.restore_backup(backup_path):
                    self.player.stop()
                    self.player.is_playing = False
                    self.playlist = PlaylistManager()
                    self._load_current_channel()
                    self._update_title()
                    self._update_display()
                    msg = "Backup restored successfully."
                    self.status_label.SetLabel(msg)
                    speak(msg)
                else:
                    msg = "Failed to restore backup."
                    wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)
                    speak(msg)
        else:
            dlg.Destroy()

    def _on_new_channel(self, event):
        """Create a new channel"""
        dlg = wx.TextEntryDialog(self, "Enter channel name:", "New Channel")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name:
                if self.channels.create_channel(name):
                    self._save_current_channel_state()
                    self.player.stop()
                    self.player.is_playing = False
                    self.playlist = PlaylistManager()
                    self._update_display()
                    self._update_title()
                    self.status_label.SetLabel(f"Created channel: {name}. Press Ctrl+O to add folders.")
                else:
                    wx.MessageBox("Channel already exists or invalid name", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()
    
    def _on_rename_channel(self, event):
        """Rename current channel"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        dlg = wx.TextEntryDialog(self, "Enter new name:", "Rename Channel", self.channels.current_channel)
        if dlg.ShowModal() == wx.ID_OK:
            new_name = dlg.GetValue().strip()
            if new_name:
                if self.channels.rename_channel(self.channels.current_channel, new_name):
                    self._update_display()
                    self._update_title()
                    self.status_label.SetLabel(f"Renamed to: {new_name}")
                else:
                    wx.MessageBox("Channel name already exists or invalid", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()
    
    def _on_delete_channel(self, event):
        """Delete current channel"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        result = wx.MessageBox(f"Delete channel '{self.channels.current_channel}'?", "Confirm Delete", wx.YES_NO | wx.ICON_QUESTION)
        if result == wx.YES:
            old_name = self.channels.current_channel
            if self.channels.delete_channel(old_name):
                self.player.stop()
                self.player.is_playing = False
                self.playlist = PlaylistManager()
                self._load_current_channel()
                self._update_display()
                self._update_title()
                self.status_label.SetLabel(f"Deleted channel: {old_name}")
    
    def _on_list_channels(self, event):
        """Show list of channels"""
        channels = self.channels.get_channel_list()
        if not channels:
            wx.MessageBox("No channels available. Press Ctrl+T to create one.", "No Channels", wx.OK | wx.ICON_INFORMATION)
            return
        
        dlg = wx.SingleChoiceDialog(self, "Select a channel:", "Channels", channels)
        if self.channels.current_channel and self.channels.current_channel in channels:
            dlg.SetSelection(channels.index(self.channels.current_channel))
        
        if dlg.ShowModal() == wx.ID_OK:
            selected = dlg.GetStringSelection()
            self._switch_to_channel(selected)
        dlg.Destroy()
    
    def _next_channel(self):
        """Switch to next channel"""
        self._save_current_channel_state()
        next_ch = self.channels.next_channel()
        if next_ch:
            self._switch_to_channel(next_ch)
        else:
            msg = "No channels available"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _prev_channel(self):
        """Switch to previous channel"""
        self._save_current_channel_state()
        prev_ch = self.channels.prev_channel()
        if prev_ch:
            self._switch_to_channel(prev_ch)
        else:
            msg = "No channels available"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _switch_to_channel(self, channel_name, start_from_beginning=False):
        """Switch to a specific channel"""
        self._play_sound_effect("remote.mp3")
        # Stop timer during switch to prevent saving wrong state
        self.timer.Stop()
        if self.channels.switch_channel(channel_name):
            self.player.stop()
            self.player.is_playing = False
            self.playlist = PlaylistManager()
            
            if start_from_beginning:
                # Load channel but start from index 0
                channel_data = self.channels.get_current_channel_data()
                if channel_data and channel_data['folders']:
                    self.playlist.add_folders(channel_data['folders'])
                    self.playlist.set_index(0)  # Start from beginning
                    if self._load_current_file():
                        self.player.paused_position = 0
                        self._update_display()
                        self.logger.log_channel("LOADED", channel_name, "from beginning (index 0)")
                    else:
                        self.logger.log_error(f"Failed to load first file in channel: {channel_name}")
                else:
                    self.logger.log_error(f"No folders in channel: {channel_name}")
            else:
                # Load channel from saved position
                self._load_current_channel()
            
            self._update_title()
            msg = f"Channel: {channel_name}"
            self.status_label.SetLabel(f"Switched to channel: {channel_name}")
            speak(msg)
        self.timer.Start(100)
    
    def _on_timer(self, event):
        """Timer callback for position updates and auto-advance"""
        try:
            if self.player.is_playing:
                pos = self.player.get_position()
                if pos >= 0:  # Valid position
                    minutes = int(pos // 60)
                    seconds = int(pos % 60)
                    self.position_label.SetLabel(f"{minutes}:{seconds:02d}")
                
                # Auto-advance to next file when current finishes
                if not self.player.is_busy() and self.player.is_playing:
                    current_file = self.playlist.get_current_file_name()
                    current_folder = self.playlist.get_current_folder_name()
                    
                    if self.playlist.next_file():
                        # Successfully moved to next file
                        next_file = self.playlist.get_current_file_name()
                        next_folder = self.playlist.get_current_folder_name()
                        
                        self.logger.log_auto_advance(
                            f"{current_folder}/{current_file}",
                            f"{next_folder}/{next_file}",
                            "File finished"
                        )
                        
                        self._load_current_file()
                        self.player.play()
                        self._save_current_channel_state()
                    else:
                        # No more files in current channel
                        # Prevent multiple simultaneous channel switches
                        if self.is_switching_channels:
                            return
                        
                        self.is_switching_channels = True
                        self.player.is_playing = False
                        
                        self.logger.log_auto_advance(
                            f"{current_folder}/{current_file}",
                            "End of channel",
                            "Channel finished, attempting next channel"
                        )
                        
                        # Peek at next channel name
                        channel_list = sorted(self.channels.channels.keys())
                        current_idx = channel_list.index(self.channels.current_channel) if self.channels.current_channel in channel_list else -1
                        next_idx = (current_idx + 1) % len(channel_list)
                        next_name = channel_list[next_idx]
                        msg = f"Channel finished. Coming up next: {next_name}"
                        self.status_label.SetLabel(msg)
                        speak(msg)
                        
                        # Save current channel state, then switch
                        self._save_current_channel_state()
                        
                        # Use delayed call to switch and play
                        wx.CallLater(500, self._auto_advance_to_next_channel)
        except Exception as e:
            self.logger.log_error(f"Timer error: {e}")
            self.status_label.SetLabel(f"Playback error: {e}")
    
    def _on_set_bookmark(self, event):
        """Set a bookmark at current position"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        if not self.playlist.get_current():
            wx.MessageBox("No file is loaded", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        # Check if at bookmark limit
        bookmarks = self.channels.get_bookmarks()
        if len(bookmarks) >= 20:
            # Ask if they want to overwrite
            dlg = wx.SingleChoiceDialog(
                self, 
                "Bookmark limit reached (20). Select a bookmark to overwrite or cancel:", 
                "Overwrite Bookmark", 
                sorted(bookmarks.keys())
            )
            if dlg.ShowModal() == wx.ID_OK:
                bookmark_name = dlg.GetStringSelection()
                dlg.Destroy()
            else:
                dlg.Destroy()
                return
        else:
            # Ask for new bookmark name
            dlg = wx.TextEntryDialog(self, "Enter bookmark name:", "Set Bookmark")
            if dlg.ShowModal() == wx.ID_OK:
                bookmark_name = dlg.GetValue().strip()
                dlg.Destroy()
                
                if not bookmark_name:
                    return
                
                # Check if bookmark exists, ask to overwrite
                if bookmark_name in bookmarks:
                    result = wx.MessageBox(
                        f"Bookmark '{bookmark_name}' already exists. Overwrite?", 
                        "Confirm Overwrite", 
                        wx.YES_NO | wx.ICON_QUESTION
                    )
                    if result != wx.YES:
                        return
            else:
                dlg.Destroy()
                return
        
        # Save bookmark
        current_index = self.playlist.current_index
        current_position = self.player.get_position()
        
        if self.channels.add_bookmark(bookmark_name, current_index, current_position):
            file_name = self.playlist.get_current_file_name()
            folder_name = self.playlist.get_current_folder_name()
            self.logger.log_bookmark("SET", bookmark_name, f"{folder_name}/{file_name} at {current_position:.1f}s")
            msg = f"Bookmark '{bookmark_name}' saved"
            self.status_label.SetLabel(msg)
            speak(msg)
        else:
            wx.MessageBox("Failed to save bookmark", "Error", wx.OK | wx.ICON_ERROR)
    
    def _on_jump_bookmark(self, event):
        """Jump to a saved bookmark"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        bookmarks = self.channels.get_bookmarks()
        if not bookmarks:
            msg = "No bookmarks in this channel"
            wx.MessageBox(msg, "No Bookmarks", wx.OK | wx.ICON_INFORMATION)
            speak(msg)
            return
        
        # Create list with bookmark info
        bookmark_list = []
        for name in sorted(bookmarks.keys()):
            bm = bookmarks[name]
            # Get file name if possible
            if bm['index'] < len(self.playlist.playlist):
                file_path = self.playlist.playlist[bm['index']][1]
                file_name = Path(file_path).name
                minutes = int(bm['position'] // 60)
                seconds = int(bm['position'] % 60)
                bookmark_list.append(f"{name} - {file_name} ({minutes}:{seconds:02d})")
            else:
                bookmark_list.append(f"{name} - (file not found)")
        
        # Show dialog with delete option
        dlg = wx.SingleChoiceDialog(self, "Select bookmark to jump to:", "Bookmarks", bookmark_list)
        
        if dlg.ShowModal() == wx.ID_OK:
            selection_index = dlg.GetSelection()
            selected_name = sorted(bookmarks.keys())[selection_index]
            dlg.Destroy()
            
            # Ask if they want to jump or delete
            result = wx.MessageBox(
                f"Jump to '{selected_name}'?\n\nClick 'No' to delete this bookmark instead.", 
                "Jump to Bookmark", 
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
            )
            
            if result == wx.YES:
                # Jump to bookmark
                bookmark = self.channels.get_bookmark(selected_name)
                if bookmark:
                    was_playing = self.player.is_playing
                    self.player.stop()
                    self.player.is_playing = False
                    
                    if self.playlist.set_index(bookmark['index']):
                        self._load_current_file()
                        self.player.paused_position = bookmark['position']
                        self._update_display()
                        
                        if was_playing:
                            self.player.unpause()
                        
                        file_name = self.playlist.get_current_file_name()
                        folder_name = self.playlist.get_current_folder_name()
                        self.logger.log_bookmark("JUMP", selected_name, f"to {folder_name}/{file_name}")
                        
                        msg = f"Jumped to bookmark: {selected_name}"
                        self.status_label.SetLabel(msg)
                        speak(msg)
                    else:
                        wx.MessageBox("Bookmark file no longer exists", "Error", wx.OK | wx.ICON_ERROR)
            elif result == wx.NO:
                # Delete bookmark
                if self.channels.delete_bookmark(selected_name):
                    self.logger.log_bookmark("DELETE", selected_name)
                    msg = f"Deleted bookmark: {selected_name}"
                    self.status_label.SetLabel(msg)
                    speak(msg)
        else:
            dlg.Destroy()
    
    def _toggle_voice_listening(self):
        """Toggle voice control listening"""
        if not self.voice_available:
            msg = "Voice control not available. Check if Vosk model is installed."
            self.status_label.SetLabel(msg)
            speak(msg)
            return
        
        if self.is_voice_listening:
            # Stop listening
            self.voice.stop_listening()
            self.is_voice_listening = False
            self._play_sound_effect("end_of_request.wav")
            msg = "Voice control stopped"
            self.status_label.SetLabel(msg)
            speak(msg)
        else:
            # Start listening in a separate thread
            self.is_voice_listening = True
            self._play_sound_effect("start_of_request.wav")
            msg = "Listening for command..."
            self.status_label.SetLabel(msg)
            speak(msg)
            
            thread = threading.Thread(target=self._voice_listen_thread, daemon=True)
            thread.start()
    
    def _voice_listen_thread(self):
        """Thread for voice listening"""
        try:
            # Listen for 5 seconds
            text = self.voice.listen(duration=5)
            
            # Play end sound
            wx.CallAfter(self._play_sound_effect, "end_of_request.wav")
            
            if text:
                # Parse command
                command = self.voice.parse_command(text)
                
                # Execute command on main thread
                wx.CallAfter(self._execute_voice_command, command, text)
            else:
                wx.CallAfter(self._voice_no_command)
        except Exception as e:
            wx.CallAfter(self._voice_error, str(e))
        finally:
            self.is_voice_listening = False
    
    def _execute_voice_command(self, command, text):
        """Execute a voice command"""
        # Handle tuple commands (command, argument)
        query = None
        if isinstance(command, tuple):
            command, query = command

        if command == 'play_pause':
            self._toggle_play_pause()
            msg = f"Command recognized: {text}"
        elif command == 'next_file':
            self._next_file()
            msg = f"Command recognized: {text}"
        elif command == 'prev_file':
            self._prev_file()
            msg = f"Command recognized: {text}"
        elif command == 'next_folder':
            self._next_folder()
            msg = f"Command recognized: {text}"
        elif command == 'prev_folder':
            self._prev_folder()
            msg = f"Command recognized: {text}"
        elif command == 'next_channel':
            self._next_channel()
            msg = f"Command recognized: {text}"
        elif command == 'prev_channel':
            self._prev_channel()
            msg = f"Command recognized: {text}"
        elif command == 'rewind':
            self._rewind()
            msg = f"Command recognized: {text}"
        elif command == 'fastforward':
            self._fastforward()
            msg = f"Command recognized: {text}"
        elif command == 'search_movies':
            if query:
                self._vault_voice_search(query, "movies")
            else:
                self._on_vault_search(None, kind="movies")
            msg = f"Command recognized: {text}"
        elif command == 'search_shows':
            if query:
                self._vault_voice_search(query, "shows")
            else:
                self._on_vault_search(None, kind="shows")
            msg = f"Command recognized: {text}"
        elif command == 'download':
            self._on_vault_recents(None, kind="movies")
            msg = f"Command recognized: {text}"
        else:
            msg = f"Unknown command: {text}"
        
        self.status_label.SetLabel(msg)
        speak(msg)
    
    def _voice_no_command(self):
        """Handle no command recognized"""
        msg = "No command recognized"
        self.status_label.SetLabel(msg)
        speak(msg)
    
    def _voice_error(self, error):
        """Handle voice recognition error"""
        msg = f"Voice error: {error}"
        self.status_label.SetLabel(msg)
        speak(msg)
    
    def _toggle_wake_word_mode(self, event=None):
        """Toggle wake word listening mode"""
        if not self.voice_available:
            msg = "Voice control not available. Check if Vosk model is installed."
            self.status_label.SetLabel(msg)
            speak(msg)
            return
        
        if self.wake_word_mode:
            # Stop wake word mode
            self.wake_word_mode = False
            self.voice.stop_listening()
            msg = "Wake word mode stopped"
            self.status_label.SetLabel(msg)
            speak(msg)
        else:
            # Start wake word mode
            self.wake_word_mode = True
            msg = "Wake word mode active. Say 'Sam' followed by a command."
            self.status_label.SetLabel(msg)
            speak(msg)
            
            self.wake_word_thread = threading.Thread(target=self._wake_word_listen_thread, daemon=True)
            self.wake_word_thread.start()
    
    def _wake_word_listen_thread(self):
        """Thread for continuous wake word listening"""
        def callback(event_type, data=None):
            if event_type == 'wake_word_detected':
                wx.CallAfter(self._wake_word_detected)
            elif event_type == 'command':
                wx.CallAfter(self._wake_word_command, data)
            elif event_type == 'no_command':
                wx.CallAfter(self._wake_word_no_command)
            elif event_type == 'error':
                wx.CallAfter(self._voice_error, data)
        
        try:
            self.voice.listen_for_wake_word(callback)
        except Exception as e:
            wx.CallAfter(self._voice_error, str(e))
    
    def _wake_word_detected(self):
        """Handle wake word detection"""
        self._play_sound_effect("start_of_request.wav")
        msg = "Listening..."
        self.status_label.SetLabel(msg)
        speak(msg)
    
    def _wake_word_command(self, text):
        """Handle command after wake word"""
        self._play_sound_effect("end_of_request.wav")
        command = self.voice.parse_command(text)
        self._execute_voice_command(command, text)
    
    def _wake_word_no_command(self):
        """Handle no command after wake word"""
        self._play_sound_effect("end_of_request.wav")
        msg = "No command heard"
        self.status_label.SetLabel(msg)
        # Don't speak this, just show in status
    
    def _check_channel_integrity(self):
        """Check channels for corrupted data on startup (lightweight check)"""
        if not self.channels.has_channels():
            return

        corrupted = []
        for name, data in self.channels.channels.items():
            folders = data.get('folders', [])
            if not folders:
                continue

            current_index = data.get('current_index', 0)
            cached_playlist = data.get('cached_playlist')

            if cached_playlist:
                # Use cache for fast check - no filesystem scan
                if current_index >= len(cached_playlist):
                    corrupted.append(name)
                elif cached_playlist:
                    # Check if the file belongs to one of the channel's folders
                    _, file_path = cached_playlist[current_index]
                    in_channel = any(file_path.startswith(f) for f in folders)
                    if not in_channel:
                        corrupted.append(name)
            # If no cache, skip - it'll get built on next load

        if corrupted:
            self.logger.log_error(f"CORRUPTION DETECTED in channels: {', '.join(corrupted)}")
            names = ", ".join(corrupted)
            msg = (f"Ashley, your channel data appears corrupted. "
                   f"Affected channels: {names}. "
                   f"You may need to start your channel list fresh.")
            speak(msg)
            result = wx.MessageBox(
                f"{msg}\n\nWould you like to delete the corrupted channel file and start over?",
                "Data Corruption Detected",
                wx.YES_NO | wx.ICON_WARNING
            )
            if result == wx.YES:
                channels_file = self.channels.channels_file
                if channels_file.exists():
                    channels_file.unlink()
                    self.channels = ChannelManager(channels_file)
                    self.playlist = PlaylistManager()
                    self._update_display()
                    self._update_title()
                    msg = "Channel file deleted. Please recreate your channels."
                    self.status_label.SetLabel(msg)
                    speak(msg)

    def _sounds_enabled(self):
        """Check if startup/outro sounds are enabled"""
        import configparser
        config = configparser.ConfigParser()
        config_path = Path(__file__).parent / "config.ini"
        try:
            config.read(config_path)
            return config.getboolean("settings", "sounds_enabled", fallback=True)
        except Exception:
            return True

    def _toggle_sounds(self, event=None):
        """Toggle startup/outro sounds on or off"""
        import configparser
        config_path = Path(__file__).parent / "config.ini"
        config = configparser.ConfigParser()
        config.read(config_path)
        if "settings" not in config:
            config["settings"] = {}
        currently_enabled = config.getboolean("settings", "sounds_enabled", fallback=True)
        new_value = not currently_enabled
        config["settings"]["sounds_enabled"] = str(new_value)
        with open(config_path, "w") as f:
            config.write(f)
        state = "on" if new_value else "off"
        msg = f"Startup and exit sounds turned {state}"
        self.status_label.SetLabel(msg)
        speak(msg)

    def _play_startup_sound(self):
        """Play startup sound if available and enabled"""
        if not self._sounds_enabled():
            return
        startup_file = Path(__file__).parent / "sounds" / "startup.mp3"
        if startup_file.exists():
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(str(startup_file))
                pygame.mixer.music.play()
            except Exception as e:
                print(f"Could not play startup sound: {e}")
    
    def _play_sound_effect(self, filename):
        """Play a sound effect from the sounds folder"""
        sound_file = Path(__file__).parent / "sounds" / filename
        if sound_file.exists():
            try:
                import pygame
                # Initialize a separate channel for sound effects
                pygame.mixer.init()
                sound = pygame.mixer.Sound(str(sound_file))
                sound.play()
            except Exception as e:
                print(f"Could not play sound effect {filename}: {e}")
    
    def _show_greeting_dialog(self):
        """Show friendly greeting dialog"""
        # First question: How are you doing?
        dlg = wx.TextEntryDialog(
            self,
            "How are you doing, sweetie? (Reminder: make sure your external drive is plugged in!)",
            "Greeting",
            ""
        )
        
        result = dlg.ShowModal()
        response = dlg.GetValue().strip().lower()
        dlg.Destroy()
        
        if result == wx.ID_CANCEL:
            return
        
        # Check response - check for negative words first
        negative_words = ['not', 'bad', 'terrible', 'awful', 'sad', 'depressed', 'angry', 'upset', 'horrible', 'poor', 'sick']
        positive_words = ['good', 'great', 'fine', 'well', 'excellent', 'wonderful', 'fantastic', 'amazing', 'happy', 'ok', 'okay']
        
        has_negative = any(word in response for word in negative_words)
        has_positive = any(word in response for word in positive_words)
        
        # If has negative words, treat as negative even if positive words present
        if has_negative:
            message = "I'm sorry to hear that. I hope you have a better day. What shows would you like to watch?"
        elif has_positive:
            message = "Good! Fantastic! What shows would you like to watch?"
        else:
            message = "What shows would you like to watch?"
        
        # Show response and ask for channel in one dialog
        self._ask_channel_to_play(message)
    
    def _ask_channel_to_play(self, prompt_message):
        """Ask which channel to play"""
        channels = self.channels.get_channel_list()
        
        if not channels:
            msg = "No channels available. Press Ctrl+T to create one."
            wx.MessageBox(msg, "No Channels", wx.OK | wx.ICON_INFORMATION)
            speak(msg)
            return
        
        # Show available channels
        channel_list = ", ".join(channels)
        full_prompt = f"{prompt_message}\n\nAvailable channels: {channel_list}"
        
        dlg = wx.TextEntryDialog(
            self,
            full_prompt,
            "Channel Selection",
            ""
        )
        
        result = dlg.ShowModal()
        channel_name = dlg.GetValue().strip()
        dlg.Destroy()
        
        if result == wx.ID_CANCEL:
            return
        
        if channel_name:
            # Find matching channel (case insensitive)
            matching_channel = None
            for ch in channels:
                if ch.lower() == channel_name.lower():
                    matching_channel = ch
                    break
            
            if matching_channel:
                # Switch to channel and start playing
                self._switch_to_channel(matching_channel)
                if self.playlist.get_current():
                    self.player.play()
                    msg = f"Now playing: {matching_channel}"
                    self.status_label.SetLabel(msg)
                    speak(msg)
            else:
                msg = f"Channel '{channel_name}' not found. Available channels: {channel_list}"
                wx.MessageBox(msg, "Channel Not Found", wx.OK | wx.ICON_WARNING)
                speak(f"Channel {channel_name} not found")
    
    def _auto_advance_to_next_channel(self):
        """Auto-advance to next channel after current finishes"""
        self.logger.log_playback("AUTO-ADVANCE", "Executing auto-advance to next channel")
        
        # Track how many empty channels we've skipped to avoid infinite loop
        if not hasattr(self, '_advance_attempts'):
            self._advance_attempts = 0
        
        total_channels = len(self.channels.get_channel_list())
        if self._advance_attempts >= total_channels:
            self._advance_attempts = 0
            self.player.is_playing = False
            self.is_switching_channels = False
            self.logger.log_error("All channels empty or drive disconnected")
            msg = "No channels with files found. Check if your external drive is connected."
            self.status_label.SetLabel(msg)
            speak(msg)
            return
        
        old_channel = self.channels.current_channel
        next_ch = self.channels.next_channel()
        
        if next_ch and next_ch != old_channel:
            self.logger.log_channel("AUTO-SWITCH", next_ch, f"from {old_channel}")
            self._play_sound_effect("remote.mp3")
            msg = f"Switching to: {next_ch}"
            self.status_label.SetLabel(msg)
            speak(msg)
            
            # Load the new channel
            self.player.stop()
            self.player.is_playing = False
            self.playlist = PlaylistManager()
            self._load_current_channel()
            self._update_title()
            
            # Wait for channel to load, then start playing
            wx.CallLater(1000, self._auto_start_playback)
        else:
            self.player.is_playing = False
            self.is_switching_channels = False
            self.logger.log_playback("FINISHED", "All channels completed")
            msg = "All channels finished"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _auto_start_playback(self):
        """Start playback after auto-advancing to next channel"""
        if self.playlist.get_current():
            self.logger.log_playback("AUTO-PLAY", "Starting playback after channel switch")
            self._advance_attempts = 0
            self._toggle_play_pause()
            msg = f"Now playing: {self.channels.current_channel}"
            speak(msg)
            self.is_switching_channels = False
        else:
            self.logger.log_error("No files in channel after auto-advance")
            self._advance_attempts += 1
            msg = f"Channel {self.channels.current_channel} is empty, trying next..."
            self.status_label.SetLabel(msg)
            speak(msg)
            self.is_switching_channels = False
            # Try next channel
            wx.CallLater(500, self._auto_advance_to_next_channel)
    
    # ---- AudioVault Methods ----
    
    def _on_set_default_folder(self, kind):
        """Set default download folder for movies or shows"""
        current = av.load_download_dir(kind=kind)
        dlg = wx.DirDialog(self, f"Set default folder for {kind}", current)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            av.save_download_dir(path, kind=kind)
            msg = f"Default {kind} folder set to: {path}"
            self.status_label.SetLabel(msg)
            speak(msg)
        dlg.Destroy()
    
    def _on_upload_log(self, event):
        """Manually upload log file to S3"""
        msg = "Uploading log..."
        self.status_label.SetLabel(msg)
        speak(msg)
        
        try:
            self.logger.upload_log()
            msg = "Log uploaded successfully"
            self.status_label.SetLabel(msg)
            speak(msg)
            wx.MessageBox(msg, "Upload Complete", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            msg = f"Log upload failed: {e}"
            self.status_label.SetLabel(msg)
            speak("Log upload failed")
            wx.MessageBox(msg, "Upload Failed", wx.OK | wx.ICON_ERROR)
    
    def _vault_auto_login(self):
        """Try auto-login with saved credentials in background"""
        email, password = av.load_credentials()
        if email and password:
            threading.Thread(target=self._vault_auto_login_thread, args=(email, password), daemon=True).start()

    def _vault_auto_login_thread(self, email, password):
        """Background thread for auto-login"""
        try:
            if av.login(email, password, log_file=str(self.logger.log_file)):
                wx.CallAfter(self._vault_login_success)
        except Exception as e:
            self.logger.log_error(f"VAULT AUTO-LOGIN ERROR: {e}")

    def _vault_login_success(self):
        """Called on main thread after successful auto-login"""
        self.vault_logged_in = True
        try:
            self.vault_login_item.SetItemLabel("Logout\tCtrl+Shift+L")
        except Exception:
            pass
    
    def _on_vault_login_toggle(self, event):
        """Toggle between login and logout"""
        if self.vault_logged_in:
            self.vault_logged_in = False
            self.vault_login_item.SetItemLabel("Login\tCtrl+Shift+L")
            msg = "Logged out of AudioVault"
            self.status_label.SetLabel(msg)
            speak(msg)
        else:
            self._on_vault_login(None)
    
    def _on_vault_login(self, event):
        """Show login dialog"""
        dlg = wx.Dialog(self, title="AudioVault Login", size=(350, 200))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(panel, label="Email:"), 0, wx.ALL, 5)
        email_ctrl = wx.TextCtrl(panel)
        sizer.Add(email_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        sizer.Add(wx.StaticText(panel, label="Password:"), 0, wx.ALL, 5)
        pass_ctrl = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        sizer.Add(pass_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        remember_cb = wx.CheckBox(panel, label="Remember me")
        remember_cb.SetValue(True)
        sizer.Add(remember_cb, 0, wx.ALL, 5)
        
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Login")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        panel.SetSizer(sizer)
        
        # Pre-fill saved credentials
        email, password = av.load_credentials()
        if email:
            email_ctrl.SetValue(email)
        if password:
            pass_ctrl.SetValue(password)
        
        if dlg.ShowModal() == wx.ID_OK:
            email = email_ctrl.GetValue().strip()
            password = pass_ctrl.GetValue().strip()
            
            if email and password:
                msg = "Logging in..."
                self.status_label.SetLabel(msg)
                speak(msg)
                
                try:
                    self.logger.log_channel("VAULT", "LOGIN", f"Attempting login for {email}")
                    if av.login(email, password, log_file=str(self.logger.log_file)):
                        self.vault_logged_in = True
                        self.vault_login_item.SetItemLabel("Logout\tCtrl+Shift+L")
                        if remember_cb.GetValue():
                            av.save_credentials(email, password)
                        msg = "AudioVault login successful"
                        self.logger.log_channel("VAULT", "LOGIN", "Success")
                        self.status_label.SetLabel(msg)
                        speak(msg)
                    else:
                        msg = "Login failed. Check email and password."
                        self.logger.log_error(f"VAULT LOGIN FAILED for {email}")
                        wx.MessageBox(msg, "Login Failed", wx.OK | wx.ICON_ERROR)
                        speak(msg)
                except Exception as e:
                    msg = f"Login error: {e}"
                    self.logger.log_error(f"VAULT LOGIN ERROR: {e}")
                    wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)
                    speak("Login error")
        
        dlg.Destroy()
    
    def _vault_ensure_login(self):
        """Ensure user is logged in. Returns True if logged in."""
        if self.vault_logged_in:
            return True
        self._on_vault_login(None)
        return self.vault_logged_in
    
    def _on_vault_search(self, event, kind):
        """Search AudioVault"""
        if not self._vault_ensure_login():
            return
        
        dlg = wx.TextEntryDialog(self, f"Search {kind}:", f"Search AudioVault {kind.capitalize()}")
        if dlg.ShowModal() == wx.ID_OK:
            query = dlg.GetValue().strip()
            dlg.Destroy()
            if query:
                msg = f"Searching for {query}..."
                self.status_label.SetLabel(msg)
                speak(msg)
                
                # Search in background thread
                thread = threading.Thread(target=self._vault_search_thread, args=(query, kind), daemon=True)
                thread.start()
        else:
            dlg.Destroy()
    
    def _vault_voice_search(self, query, kind):
        """Search AudioVault directly from voice command with extracted query"""
        if not self._vault_ensure_login():
            return
        msg = f"Searching for {query}..."
        self.status_label.SetLabel(msg)
        speak(msg)
        thread = threading.Thread(target=self._vault_search_thread, args=(query, kind), daemon=True)
        thread.start()

    def _vault_search_thread(self, query, kind):
        """Background thread for search"""
        try:
            results = av.search(query, kind=kind)
            wx.CallAfter(self._vault_show_results, results, kind)
        except Exception as e:
            wx.CallAfter(self._vault_error, f"Search error: {e}")
    
    def _on_vault_recents(self, event, kind):
        """View recent additions"""
        if not self._vault_ensure_login():
            return
        
        msg = f"Loading recent {kind}..."
        self.status_label.SetLabel(msg)
        speak(msg)
        
        thread = threading.Thread(target=self._vault_recents_thread, args=(kind,), daemon=True)
        thread.start()
    
    def _vault_recents_thread(self, kind):
        """Background thread for recents"""
        try:
            results = av.get_recents(kind)
            wx.CallAfter(self._vault_show_results, results, kind)
        except Exception as e:
            wx.CallAfter(self._vault_error, f"Error loading recents: {e}")
    
    def _vault_show_results(self, results, kind):
        """Show search/recent results and allow multiple downloads"""
        if not results:
            msg = "No results found"
            self.status_label.SetLabel(msg)
            speak(msg)
            return
        
        items = [f"{name} ({av_id})" for av_id, name, link in results]
        msg = f"Found {len(items)} results"
        speak(msg)
        
        # Custom dialog with CheckListBox for NVDA accessibility
        dlg = wx.Dialog(self, title="AudioVault Results", size=(500, 400))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(panel, label=f"Check items to download ({len(items)} results):"), 0, wx.ALL, 5)
        
        checklist = wx.CheckListBox(panel, choices=items)
        sizer.Add(checklist, 1, wx.ALL | wx.EXPAND, 5)
        
        # Select All / Deselect All buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        select_all_btn = wx.Button(panel, label="Select All")
        deselect_all_btn = wx.Button(panel, label="Deselect All")
        select_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, True) for i in range(len(items))])
        deselect_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, False) for i in range(len(items))])
        btn_row.Add(select_all_btn, 0, wx.ALL, 5)
        btn_row.Add(deselect_all_btn, 0, wx.ALL, 5)
        sizer.Add(btn_row, 0, wx.ALIGN_CENTER)
        
        # OK / Cancel
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Download")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        panel.SetSizer(sizer)
        checklist.SetFocus()
        
        if dlg.ShowModal() == wx.ID_OK:
            selections = [i for i in range(len(items)) if checklist.IsChecked(i)]
            dlg.Destroy()
            if not selections:
                return
            
            # Use kind-specific default folder
            dest = av.load_download_dir(kind=kind)
            os.makedirs(dest, exist_ok=True)
            
            self.download_queue = [(results[i][1], results[i][2]) for i in selections]
            self.download_create_channel = False
            self.download_subfolder = None
            
            # If multiple items, offer subfolder grouping
            if len(selections) > 1:
                result = wx.MessageBox(
                    "Put all selected items into their own subfolder?",
                    "Group Downloads",
                    wx.YES_NO | wx.ICON_QUESTION
                )
                if result == wx.YES:
                    name_dlg = wx.TextEntryDialog(self, "Name for the subfolder:", "Subfolder Name")
                    if name_dlg.ShowModal() == wx.ID_OK:
                        subfolder = name_dlg.GetValue().strip()
                        name_dlg.Destroy()
                        if subfolder:
                            dest = os.path.join(dest, subfolder)
                            os.makedirs(dest, exist_ok=True)
                            self.download_subfolder = subfolder
                    else:
                        name_dlg.Destroy()
            
            self.download_dest = dest
            self.download_queue_index = 0
            speak(f"Queued {len(self.download_queue)} downloads")
            self._vault_download_next()
        else:
            dlg.Destroy()
    
    def _vault_start_download(self, name, download_url):
        """Start downloading a single file"""
        default_dir = av.load_download_dir()
        os.makedirs(default_dir, exist_ok=True)
        dlg = wx.DirDialog(self, "Choose download folder", default_dir)
        if dlg.ShowModal() == wx.ID_OK:
            dest = dlg.GetPath()
            dlg.Destroy()
            av.save_download_dir(dest)
            self.download_queue = [(name, download_url)]
            self.download_dest = dest
            self.download_queue_index = 0
            self._vault_download_next()
        else:
            dlg.Destroy()
    
    def _vault_download_next(self):
        """Download next item in queue"""
        if self.download_queue_index >= len(self.download_queue):
            total = len(self.download_queue)
            msg = f"All {total} download(s) complete"
            self.status_label.SetLabel(msg)
            speak(msg)
            
            # Offer channel creation if downloaded to subfolder
            if self.download_subfolder:
                self._vault_offer_channel_creation()
            else:
                wx.MessageBox(msg, "Downloads Complete", wx.OK | wx.ICON_INFORMATION)
            return
        
        name, url = self.download_queue[self.download_queue_index]
        current = self.download_queue_index + 1
        total = len(self.download_queue)
        
        self.download_progress = wx.ProgressDialog(
            f"Downloading ({current}/{total})",
            f"Starting: {name}...",
            maximum=100,
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME | wx.PD_REMAINING_TIME
        )
        
        speak(f"Downloading {current} of {total}: {name}")
        
        thread = threading.Thread(
            target=self._vault_download_thread,
            args=(name, url, self.download_dest),
            daemon=True
        )
        thread.start()
    
    def _vault_download_thread(self, name, download_url, destination):
        """Background thread for download"""
        try:
            self.logger.log_channel("VAULT", "DOWNLOAD", f"Starting download: {name} from {download_url} to {destination}")
            
            def progress(percent, total_size, filename):
                wx.CallAfter(self._vault_update_progress, percent, total_size, filename)
            
            filepath = av.download(download_url, destination=destination, progress_callback=progress)
            
            if filepath:
                self.logger.log_channel("VAULT", "DOWNLOAD", f"Complete: {filepath}")
                wx.CallAfter(self._vault_download_complete, name, filepath)
            else:
                self.logger.log_error(f"VAULT DOWNLOAD FAILED: {name} - returned None")
                self.vault_logged_in = False
                wx.CallAfter(self._vault_download_failed, f"Download failed for {name}. Session may have expired.")
        except Exception as e:
            self.logger.log_error(f"VAULT DOWNLOAD ERROR: {name} - {e}")
            wx.CallAfter(self._vault_download_failed, f"Download error for {name}: {e}")
    
    def _vault_update_progress(self, percent, total_size, filename):
        """Update download progress dialog"""
        if hasattr(self, 'download_progress') and self.download_progress:
            current = self.download_queue_index + 1
            total = len(self.download_queue)
            msg = f"({current}/{total}) {filename}: {percent:.0f}% of {av.bytes2human(total_size)}"
            keep_going, _ = self.download_progress.Update(int(percent), msg)
            if not keep_going:
                self.download_progress.Destroy()
                self.download_progress = None
                self.status_label.SetLabel("Download cancelled")
                speak("Download cancelled")
    
    def _vault_download_complete(self, name, filepath):
        """Handle completed download, extract if ZIP, move to next in queue"""
        if hasattr(self, 'download_progress') and self.download_progress:
            self.download_progress.Destroy()
            self.download_progress = None
        
        # Check if ZIP and extract
        if filepath and filepath.lower().endswith('.zip'):
            extracted = self._vault_extract_zip(name, filepath)
            if extracted:
                msg = f"Extracted: {name}"
            else:
                msg = f"Downloaded (extraction failed): {name}"
        else:
            msg = f"Downloaded: {name}"
        
        self.status_label.SetLabel(msg)
        self.download_queue_index += 1
        
        # Download next in queue
        self._vault_download_next()
    
    def _vault_extract_zip(self, name, zip_path):
        """Extract ZIP file, flatten duplicate folders, and clean up"""
        import zipfile
        import shutil
        
        try:
            if not zipfile.is_zipfile(zip_path):
                self.logger.log_error(f"VAULT: Not a valid ZIP: {zip_path}")
                return False
            
            # Extract to folder named after the show
            extract_dir = os.path.join(os.path.dirname(zip_path), name)
            os.makedirs(extract_dir, exist_ok=True)
            
            speak(f"Extracting {name}")
            self.status_label.SetLabel(f"Extracting: {name}...")
            self.logger.log_channel("VAULT", "EXTRACT", f"Extracting {zip_path} to {extract_dir}")
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
            
            # Handle nested ZIPs
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    nested_path = os.path.join(root, f)
                    if f.lower().endswith('.zip') and zipfile.is_zipfile(nested_path):
                        nested_dir = os.path.splitext(nested_path)[0]
                        os.makedirs(nested_dir, exist_ok=True)
                        with zipfile.ZipFile(nested_path, 'r') as nzf:
                            nzf.extractall(nested_dir)
                        os.remove(nested_path)
            
            # Flatten duplicate nested folders (e.g., Season 1/Season 1/ -> Season 1/)
            for root, dirs, files in os.walk(extract_dir, topdown=False):
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    contents = os.listdir(dir_path)
                    if len(contents) == 1:
                        inner = os.path.join(dir_path, contents[0])
                        if os.path.isdir(inner):
                            # Flatten if same name OR inner folder name contains parent name
                            if contents[0] == d or contents[0].lower().startswith(d.lower()) or d.lower().startswith(contents[0].lower()):
                                for item in os.listdir(inner):
                                    shutil.move(os.path.join(inner, item), dir_path)
                                os.rmdir(inner)
                                self.logger.log_channel("VAULT", "EXTRACT", f"Flattened: {d}/{contents[0]}")
            
            # Delete original ZIP
            os.remove(zip_path)
            
            self.logger.log_channel("VAULT", "EXTRACT", f"Extraction complete: {extract_dir}")
            speak(f"Extracted {name}")
            return True
            
        except Exception as e:
            self.logger.log_error(f"VAULT EXTRACT ERROR: {name} - {e}")
            speak("Extraction failed")
            return False
    
    def _vault_offer_channel_creation(self):
        """Offer to create a channel from downloaded content"""
        result = wx.MessageBox(
            f"Create a channel '{self.download_subfolder}' from the downloaded files?",
            "Create Channel",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result != wx.YES:
            return
        
        channel_name = self.download_subfolder
        dest = self.download_dest
        
        # Flatten any double-nested folders before scanning
        import shutil
        for root, dirs, files in os.walk(dest, topdown=False):
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    contents = os.listdir(dir_path)
                    if len(contents) == 1:
                        inner = os.path.join(dir_path, contents[0])
                        if os.path.isdir(inner):
                            if contents[0] == d or contents[0].lower().startswith(d.lower()) or d.lower().startswith(contents[0].lower()):
                                for item in os.listdir(inner):
                                    shutil.move(os.path.join(inner, item), dir_path)
                                os.rmdir(inner)
                except Exception:
                    pass
        
        # Find all folders with MP3 files at any depth, sorted naturally
        from playlist_manager import natural_sort_key
        folders = []
        
        for root, dirs, files in os.walk(dest):
            dirs.sort(key=natural_sort_key)
            mp3s = [f for f in files if f.lower().endswith('.mp3')]
            if mp3s:
                folders.append(root)
        
        if not folders:
            wx.MessageBox("No MP3 files found in downloaded content.", "No Files", wx.OK | wx.ICON_WARNING)
            return
        
        # Handle existing channel
        if channel_name in self.channels.channels:
            choice = wx.MessageBox(
                f"Channel '{channel_name}' already exists.\n\nYes = Replace it\nNo = Add folders to it",
                "Channel Exists",
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
            )
            if choice == wx.CANCEL:
                return
            elif choice == wx.YES:
                # Replace - delete and recreate
                self.channels.delete_channel(channel_name)
                self.channels.create_channel(channel_name)
                self.channels.update_current_channel(folders=folders)
            else:
                # Add to existing
                existing = self.channels.channels[channel_name].get('folders', [])
                combined = existing + [f for f in folders if f not in existing]
                self.channels.switch_channel(channel_name)
                self.channels.update_current_channel(folders=combined)
        else:
            # Create new channel
            self.channels.create_channel(channel_name)
            self.channels.update_current_channel(folders=folders)
        
        # Load the channel
        self.playlist = PlaylistManager()
        self._load_current_channel()
        self._update_title()
        self._update_display()
        
        msg = f"Channel '{channel_name}' created with {len(folders)} folder(s)"
        self.status_label.SetLabel(msg)
        speak(msg)
        self.logger.log_channel("VAULT", "CHANNEL-CREATE", f"{channel_name} with {len(folders)} folders")
        self._toggle_play_pause()
    
    def _vault_download_failed(self, message):
        """Handle failed download with error dialog"""
        if hasattr(self, 'download_progress') and self.download_progress:
            self.download_progress.Destroy()
            self.download_progress = None
        
        self.status_label.SetLabel("Download failed")
        speak("Download failed")
        wx.MessageBox(message, "Download Failed", wx.OK | wx.ICON_ERROR)
    
    def _vault_error(self, message):
        """Handle AudioVault errors"""
        self.status_label.SetLabel(message)
        speak(message)
    
    # ---- YouTube Methods ----

    def _on_yt_set_folder(self, event):
        """Set default YouTube download folder"""
        current = yt.load_download_dir()
        dlg = wx.DirDialog(self, "Set YouTube download folder", current)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            yt.save_download_dir(path)
            msg = f"YouTube download folder set to: {path}"
            self.status_label.SetLabel(msg)
            speak(msg)
        dlg.Destroy()

    def _on_yt_url(self, event):
        """Download from a YouTube URL"""
        dlg = wx.TextEntryDialog(self, "Paste YouTube URL:", "Download from URL")
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            dlg.Destroy()
            if url:
                msg = "Checking URL..."
                self.status_label.SetLabel(msg)
                speak(msg)
                threading.Thread(target=self._yt_detect_url_thread, args=(url,), daemon=True).start()
        else:
            dlg.Destroy()

    def _yt_detect_url_thread(self, url):
        try:
            info = yt.detect_url(url)
            wx.CallAfter(self._yt_handle_detected_url, url, info)
        except Exception as e:
            wx.CallAfter(self._yt_error, f"URL detection error: {e}")

    def _yt_handle_detected_url(self, url, info):
        dest = yt.load_download_dir()

        if info["is_playlist"]:
            count = info["count"]
            title = info["title"]
            result = wx.MessageBox(
                f"This is a playlist: \"{title}\" ({count} items).\n\nDownload all {count} items?",
                "Playlist Detected",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if result != wx.YES:
                return

            # Use playlist title as subfolder
            subfolder = "".join(c for c in title if c.isalnum() or c in " _-").strip()
            if subfolder:
                dest = os.path.join(dest, subfolder)
                os.makedirs(dest, exist_ok=True)

            self._yt_download_queue = [(e["title"], e["url"]) for e in info["entries"]]
        else:
            self._yt_download_queue = [(info["title"], url)]

        self._yt_download_dest = dest
        self._yt_download_idx = 0
        speak(f"Queued {len(self._yt_download_queue)} download{'s' if len(self._yt_download_queue) > 1 else ''}")
        self._yt_download_next()

    def _on_yt_search(self, event):
        """Search YouTube"""
        dlg = wx.TextEntryDialog(self, "Search YouTube:", "YouTube Search")
        if dlg.ShowModal() == wx.ID_OK:
            query = dlg.GetValue().strip()
            dlg.Destroy()
            if query:
                msg = f"Searching YouTube for {query}..."
                self.status_label.SetLabel(msg)
                speak(msg)
                threading.Thread(target=self._yt_search_thread, args=(query,), daemon=True).start()
        else:
            dlg.Destroy()

    def _yt_search_thread(self, query):
        try:
            results = yt.search(query)
            wx.CallAfter(self._yt_show_results, results)
        except Exception as e:
            wx.CallAfter(self._yt_error, f"YouTube search error: {e}")

    def _yt_show_results(self, results):
        if not results:
            msg = "No results found"
            self.status_label.SetLabel(msg)
            speak(msg)
            return

        items = [f"{r['title']} [{r['duration']}] - {r['channel']}" for r in results]
        speak(f"Found {len(items)} results")

        dlg = wx.Dialog(self, title="YouTube Results", size=(600, 400))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(panel, label=f"Check items to download ({len(items)} results):"), 0, wx.ALL, 5)
        checklist = wx.CheckListBox(panel, choices=items)
        sizer.Add(checklist, 1, wx.ALL | wx.EXPAND, 5)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        select_all_btn = wx.Button(panel, label="Select All")
        deselect_all_btn = wx.Button(panel, label="Deselect All")
        select_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, True) for i in range(len(items))])
        deselect_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, False) for i in range(len(items))])
        btn_row.Add(select_all_btn, 0, wx.ALL, 5)
        btn_row.Add(deselect_all_btn, 0, wx.ALL, 5)
        sizer.Add(btn_row, 0, wx.ALIGN_CENTER)

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Download")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        panel.SetSizer(sizer)
        checklist.SetFocus()

        if dlg.ShowModal() == wx.ID_OK:
            selections = [i for i in range(len(items)) if checklist.IsChecked(i)]
            dlg.Destroy()
            if not selections:
                return

            dest = yt.load_download_dir()

            # Offer subfolder grouping for multiple items
            if len(selections) > 1:
                result = wx.MessageBox("Put all downloads into a subfolder?", "Group Downloads", wx.YES_NO | wx.ICON_QUESTION)
                if result == wx.YES:
                    name_dlg = wx.TextEntryDialog(self, "Subfolder name:", "Subfolder")
                    if name_dlg.ShowModal() == wx.ID_OK:
                        subfolder = name_dlg.GetValue().strip()
                        name_dlg.Destroy()
                        if subfolder:
                            dest = os.path.join(dest, subfolder)
                            os.makedirs(dest, exist_ok=True)
                    else:
                        name_dlg.Destroy()

            self._yt_download_queue = [(results[i]["title"], results[i]["url"]) for i in selections]
            self._yt_download_dest = dest
            self._yt_download_idx = 0
            speak(f"Queued {len(self._yt_download_queue)} downloads")
            self._yt_download_next()
        else:
            dlg.Destroy()

    def _yt_download_next(self):
        """Download next item in YouTube queue"""
        if self._yt_download_idx >= len(self._yt_download_queue):
            total = len(self._yt_download_queue)
            msg = f"All {total} YouTube download(s) complete"
            self.status_label.SetLabel(msg)
            speak(msg)
            wx.MessageBox(msg, "Downloads Complete", wx.OK | wx.ICON_INFORMATION)
            return

        title, url = self._yt_download_queue[self._yt_download_idx]
        current = self._yt_download_idx + 1
        total = len(self._yt_download_queue)

        self._yt_progress = wx.ProgressDialog(
            f"Downloading ({current}/{total})",
            f"Starting: {title}...",
            maximum=100,
            parent=self,
            style=wx.PD_APP_MODAL | wx.PD_AUTO_HIDE | wx.PD_CAN_ABORT | wx.PD_ELAPSED_TIME
        )
        speak(f"Downloading {current} of {total}: {title}")
        threading.Thread(target=self._yt_download_thread, args=(title, url), daemon=True).start()

    def _yt_download_thread(self, title, url):
        try:
            def progress(percent, filename):
                wx.CallAfter(self._yt_update_progress, percent, title)

            filepath = yt.download(url, destination=self._yt_download_dest, progress_callback=progress)
            if filepath:
                wx.CallAfter(self._yt_download_complete, title, filepath)
            else:
                wx.CallAfter(self._yt_error, f"Download failed: {title}")
        except Exception as e:
            wx.CallAfter(self._yt_error, f"Download error for {title}: {e}")

    def _yt_update_progress(self, percent, title):
        if hasattr(self, '_yt_progress') and self._yt_progress:
            current = self._yt_download_idx + 1
            total = len(self._yt_download_queue)
            msg = f"({current}/{total}) {title}: {percent:.0f}%"
            keep_going, _ = self._yt_progress.Update(int(min(percent, 99)), msg)
            if not keep_going:
                self._yt_progress.Destroy()
                self._yt_progress = None
                self.status_label.SetLabel("Download cancelled")
                speak("Download cancelled")

    def _yt_download_complete(self, title, filepath):
        if hasattr(self, '_yt_progress') and self._yt_progress:
            self._yt_progress.Destroy()
            self._yt_progress = None
        self.status_label.SetLabel(f"Downloaded: {title}")
        self._yt_download_idx += 1
        self._yt_download_next()

    def _yt_error(self, message):
        if hasattr(self, '_yt_progress') and self._yt_progress:
            self._yt_progress.Destroy()
            self._yt_progress = None
        self.status_label.SetLabel(message)
        speak(message)
        self.logger.log_error(f"YOUTUBE: {message}")

    def _on_quick_quit(self, event):
        """Quit immediately without outro sound"""
        try:
            self._save_current_channel_state()
        except Exception:
            pass
        
        if self.voice_available:
            if self.is_voice_listening or self.wake_word_mode:
                self.voice.stop_listening()
                self.wake_word_mode = False
        
        self.player.stop()
        self.timer.Stop()
        self.Destroy()
    
    def _on_close(self, event):
        """Handle window close"""
        try:
            self._save_current_channel_state()
        except Exception as e:
            print(f"Error saving channel state: {e}")
        
        # Stop voice control if running
        if self.voice_available:
            if self.is_voice_listening or self.wake_word_mode:
                self.voice.stop_listening()
                self.wake_word_mode = False
        
        self.player.stop()
        self.timer.Stop()
        
        # Play outro sound and wait for it to finish
        if self._play_outro_sound():
            # Check every 100ms if outro is still playing
            self._check_outro_finished()
        else:
            # No outro or failed to play, close immediately
            self.Destroy()
    
    def _play_outro_sound(self):
        """Play outro sound on exit if enabled"""
        if not self._sounds_enabled():
            return False
        outro_file = Path(__file__).parent / "sounds" / "outro.mp3"
        if outro_file.exists():
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(str(outro_file))
                pygame.mixer.music.play()
                return True
            except Exception as e:
                print(f"Could not play outro sound: {e}")
                return False
        return False
    
    def _check_outro_finished(self):
        """Check if outro is still playing, close when done"""
        import pygame
        if pygame.mixer.music.get_busy():
            # Still playing, check again in 100ms
            wx.CallLater(100, self._check_outro_finished)
        else:
            # Outro finished, close now
            self.Destroy()

def main():
    app = wx.App()
    frame = PlayerFrame()
    frame.Show()

    # Check for updates in background after window is visible
    def _background_update_check():
        try:
            from auto_updater import check_for_updates
            available = check_for_updates()
            if available:
                wx.CallAfter(_offer_updates, available)
        except Exception as e:
            print(f"Update check failed: {e}")

    def _offer_updates(available):
        result = wx.MessageBox(
            f"{len(available)} update(s) available:\n" + "\n".join(available) + "\n\nUpdate now?",
            "Updates Available",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            from auto_updater import apply_updates
            updated = apply_updates(available)
            if "main.py" in updated:
                wx.MessageBox("Main program updated. Please restart the app.", "Update Complete", wx.OK)

    threading.Thread(target=_background_update_check, daemon=True).start()

    app.MainLoop()

if __name__ == "__main__":
    main()

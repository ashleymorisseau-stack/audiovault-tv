import json
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

MAX_BACKUPS = 10

class ChannelManager:
    def __init__(self, channels_file, logger=None):
        self.channels_file = Path(channels_file)
        self.backup_dir = self.channels_file.parent / ".channel_backups"
        self.logger = logger
        self.channels = {}  # {channel_name: {folders: [], current_index: 0, position: 0}}
        self.current_channel = None
        self._load_ok = True   # False if the last load failed (corrupt/unreadable file)
        self._had_channels = False  # True if we successfully loaded channels this session
        self.load_channels()
        # Snapshot the good file at startup, before anything can modify it
        if self._load_ok and self.channels:
            self._create_backup()
        self._log(f"INIT - loaded {len(self.channels)} channels, load_ok={self._load_ok}")

    def _log(self, message):
        """Log a channel-manager event if a logger is available."""
        if self.logger:
            try:
                self.logger.log_channel("MANAGER", "", message)
            except Exception:
                pass
    
    def _create_backup(self):
        """Create a backup of the current channels file"""
        if not self.channels_file.exists():
            return
        self.backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"channels_{timestamp}.json"
        shutil.copy2(self.channels_file, backup_path)
        self._cleanup_old_backups()

    def _cleanup_old_backups(self):
        """Keep only the most recent backups"""
        backups = sorted(self.backup_dir.glob("channels_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[MAX_BACKUPS:]:
            old.unlink()

    def get_backups(self):
        """Get list of available backups, newest first. Returns list of (path, display_name) tuples."""
        if not self.backup_dir.exists():
            return []
        backups = sorted(self.backup_dir.glob("channels_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        result = []
        for b in backups:
            # Parse timestamp from filename
            stem = b.stem.replace("channels_", "")
            try:
                dt = datetime.strptime(stem, "%Y%m%d_%H%M%S")
                display = dt.strftime("%B %d, %Y at %I:%M:%S %p")
            except ValueError:
                display = b.name
            result.append((b, display))
        return result

    def restore_backup(self, backup_path):
        """Restore channels from a backup file. Returns True on success."""
        backup_path = Path(backup_path)
        if not backup_path.exists():
            return False
        try:
            # Verify backup is valid JSON
            with open(backup_path, 'r') as f:
                data = json.load(f)
            if 'channels' not in data:
                return False
            # Load the recovered data, then write it back safely
            self.channels = data.get('channels', {})
            self.current_channel = data.get('current_channel')
            self._load_ok = True
            self._had_channels = bool(self.channels)
            self._write_atomic()
            return True
        except Exception:
            return False
    
    def load_channels(self):
        """Load all channels from file. If the file is corrupt, attempt to
        recover from the most recent valid backup instead of starting empty."""
        if not self.channels_file.exists():
            # No file yet — this is a genuinely fresh start, empty is correct.
            self._load_ok = True
            self._had_channels = False
            return

        try:
            with open(self.channels_file, 'r') as f:
                data = json.load(f)
            self.channels = data.get('channels', {})
            self.current_channel = data.get('current_channel')
            self._load_ok = True
            self._had_channels = bool(self.channels)
        except Exception as e:
            # The file exists but is corrupt/unreadable. DO NOT start empty and
            # let auto-save overwrite it — try to recover from a backup first.
            print(f"Error loading channels (file may be corrupt): {e}")
            self._log(f"LOAD FAILED - file may be corrupt: {e}")
            self._load_ok = False
            if self._recover_from_backup():
                self._load_ok = True
                self._had_channels = bool(self.channels)
                self._log(f"RECOVERED {len(self.channels)} channels from backup")
            else:
                # Could not recover. Keep channels empty but mark load as failed
                # so save_channels() refuses to overwrite the existing file.
                self.channels = {}
                self.current_channel = None
                self._had_channels = False
                self._log("RECOVERY FAILED - no valid backup found; save is locked to protect file")

    def _recover_from_backup(self):
        """Try to load the newest valid backup. Returns True on success."""
        for backup_path, _ in self.get_backups():
            try:
                with open(backup_path, 'r') as f:
                    data = json.load(f)
                if 'channels' in data and data['channels']:
                    self.channels = data['channels']
                    self.current_channel = data.get('current_channel')
                    print(f"Recovered channels from backup: {backup_path.name}")
                    # Write the recovered data back safely
                    self._write_atomic()
                    return True
            except Exception:
                continue
        return False

    def _write_atomic(self):
        """Write the channels file atomically (temp file + replace) so the real
        file is never left truncated or half-written."""
        data = {
            'channels': self.channels,
            'current_channel': self.current_channel,
        }
        self.channels_file.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temp file in the same directory (required for atomic replace)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.channels_file.parent),
            prefix=".channels_tmp_", suffix=".json"
        )
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # Atomic on the same filesystem — the real file is only ever the
            # complete old copy or the complete new copy, never a partial write.
            os.replace(tmp_path, str(self.channels_file))
        except Exception as e:
            print(f"Error writing channels: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            raise

    def save_channels(self):
        """Save all channels to file, with guards against destroying data."""
        # Guard 1: if the last load failed, never overwrite the existing file —
        # it may still contain the user's real data that we just couldn't parse.
        if not self._load_ok:
            print("Skipping save: previous load failed, refusing to overwrite channels file.")
            self._log("SAVE BLOCKED - previous load failed, protecting existing file")
            return

        # Guard 2: never write an empty channel set over a file that previously
        # had channels. This is the failure mode that wiped everything before.
        if not self.channels and self._had_channels:
            print("Skipping save: refusing to overwrite existing channels with an empty set.")
            self._log("SAVE BLOCKED - refusing to overwrite channels with empty set")
            return

        try:
            self._write_atomic()
            if self.channels:
                self._had_channels = True
        except Exception as e:
            print(f"Error saving channels: {e}")
    
    def create_channel(self, name):
        """Create a new channel"""
        if name and name not in self.channels:
            self._create_backup()
            self.channels[name] = {
                'folders': [],
                'current_index': 0,
                'position': 0,
                'bookmarks': {}  # {bookmark_name: {index: int, position: float}}
            }
            self.current_channel = name
            self.save_channels()
            return True
        return False
    
    def delete_channel(self, name):
        """Delete a channel"""
        if name in self.channels:
            self._create_backup()
            del self.channels[name]
            if self.current_channel == name:
                # Switch to first available channel or None
                self.current_channel = next(iter(self.channels.keys())) if self.channels else None
            # Intentional deletion: allow saving even if this empties the list.
            if not self.channels:
                self._had_channels = False
            self.save_channels()
            return True
        return False
    
    def rename_channel(self, old_name, new_name):
        """Rename a channel"""
        if old_name in self.channels and new_name and new_name not in self.channels:
            self._create_backup()
            self.channels[new_name] = self.channels.pop(old_name)
            if self.current_channel == old_name:
                self.current_channel = new_name
            self.save_channels()
            return True
        return False
    
    def switch_channel(self, name):
        """Switch to a different channel"""
        if name in self.channels:
            self.current_channel = name
            self.save_channels()
            return True
        return False
    
    def next_channel(self):
        """Switch to next channel"""
        if not self.channels:
            return None
        
        channel_list = sorted(self.channels.keys())
        if not self.current_channel or self.current_channel not in channel_list:
            self.current_channel = channel_list[0]
        else:
            current_idx = channel_list.index(self.current_channel)
            next_idx = (current_idx + 1) % len(channel_list)
            self.current_channel = channel_list[next_idx]
        
        self.save_channels()
        return self.current_channel
    
    def prev_channel(self):
        """Switch to previous channel"""
        if not self.channels:
            return None
        
        channel_list = sorted(self.channels.keys())
        if not self.current_channel or self.current_channel not in channel_list:
            self.current_channel = channel_list[-1]
        else:
            current_idx = channel_list.index(self.current_channel)
            prev_idx = (current_idx - 1) % len(channel_list)
            self.current_channel = channel_list[prev_idx]
        
        self.save_channels()
        return self.current_channel
    
    def get_current_channel_data(self):
        """Get data for current channel"""
        if self.current_channel and self.current_channel in self.channels:
            return self.channels[self.current_channel]
        return None
    
    def update_current_channel(self, folders=None, current_index=None, position=None, cached_playlist=None):
        """Update current channel data"""
        if self.current_channel and self.current_channel in self.channels:
            if folders is not None:
                self._create_backup()
                self.channels[self.current_channel]['folders'] = folders
                # Invalidate cache when folders change
                self.channels[self.current_channel].pop('cached_playlist', None)
            if current_index is not None:
                self.channels[self.current_channel]['current_index'] = current_index
            if position is not None:
                self.channels[self.current_channel]['position'] = position
            if cached_playlist is not None:
                self.channels[self.current_channel]['cached_playlist'] = cached_playlist
            self.save_channels()
    
    def get_channel_list(self):
        """Get sorted list of channel names"""
        return sorted(self.channels.keys())
    
    def has_channels(self):
        """Check if any channels exist"""
        return len(self.channels) > 0
    
    def add_bookmark(self, bookmark_name, file_index, position):
        """Add a bookmark to current channel"""
        if self.current_channel and self.current_channel in self.channels:
            if 'bookmarks' not in self.channels[self.current_channel]:
                self.channels[self.current_channel]['bookmarks'] = {}
            
            # Limit to 20 bookmarks
            if len(self.channels[self.current_channel]['bookmarks']) >= 20 and bookmark_name not in self.channels[self.current_channel]['bookmarks']:
                return False
            
            self.channels[self.current_channel]['bookmarks'][bookmark_name] = {
                'index': file_index,
                'position': position
            }
            self.save_channels()
            return True
        return False
    
    def delete_bookmark(self, bookmark_name):
        """Delete a bookmark from current channel"""
        if self.current_channel and self.current_channel in self.channels:
            if 'bookmarks' in self.channels[self.current_channel] and bookmark_name in self.channels[self.current_channel]['bookmarks']:
                del self.channels[self.current_channel]['bookmarks'][bookmark_name]
                self.save_channels()
                return True
        return False
    
    def get_bookmarks(self):
        """Get all bookmarks for current channel"""
        if self.current_channel and self.current_channel in self.channels:
            if 'bookmarks' not in self.channels[self.current_channel]:
                self.channels[self.current_channel]['bookmarks'] = {}
            return self.channels[self.current_channel]['bookmarks']
        return {}
    
    def get_bookmark(self, bookmark_name):
        """Get a specific bookmark"""
        bookmarks = self.get_bookmarks()
        return bookmarks.get(bookmark_name)

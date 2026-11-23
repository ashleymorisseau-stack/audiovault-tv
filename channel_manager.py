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

    @staticmethod
    def _normalise_path(path):
        """Return a Path for comparison, case-insensitive on Windows."""
        p = Path(str(path))
        if os.name == "nt":
            return Path(os.path.normcase(str(p)))
        return p

    @classmethod
    def _is_under_folder(cls, file_path, folders):
        """True if file_path is inside one of folders (not a raw startswith).

        A raw string startswith would wrongly match a sibling folder such as
        "Show 2" for folder "Show", and would miss the same folder written
        with different separators or letter case on Windows.
        """
        try:
            file_p = cls._normalise_path(file_path)
        except Exception:
            return False
        for folder in folders:
            try:
                folder_p = cls._normalise_path(folder)
            except Exception:
                continue
            try:
                # Python 3.9+: Path.is_relative_to
                if file_p.is_relative_to(folder_p):
                    return True
            except AttributeError:
                try:
                    file_p.relative_to(folder_p)
                    return True
                except ValueError:
                    continue
            except Exception:
                continue
        return False

    def _repair_channels_in_memory(self):
        """Validate and repair every loaded channel in place.

        A stale cache or an out-of-range index is NOT corruption of the
        channels file itself, so it is repaired, never used as a reason
        to wipe anything:
        - folders must be a list of non-empty strings
        - cached entries must be [folder_index, path] pairs whose file
          still exists and is still under one of the channel's folders;
          stale entries are dropped, and an empty/stale cache is cleared
          so the next load rebuilds it by scanning the folders
        - current_index is coerced to int and clamped to a valid range
        - position is coerced to a non-negative number
        - bookmarks must be a dict; bookmarks pointing past the end of
          the cached playlist are dropped
        - current_channel must name an existing channel

        Returns the list of channel names that were changed.
        """
        repaired = []
        if not isinstance(self.channels, dict):
            self.channels = {}
        for name in list(self.channels.keys()):
            data = self.channels[name]
            changed = False
            if not isinstance(data, dict):
                data = {"folders": [], "current_index": 0, "position": 0,
                        "bookmarks": {}}
                self.channels[name] = data
                changed = True

            folders = data.get("folders")
            if not isinstance(folders, list):
                folders = []
                data["folders"] = folders
                changed = True
            else:
                clean_folders = [f for f in folders
                                 if isinstance(f, str) and f.strip()]
                if clean_folders != folders:
                    data["folders"] = clean_folders
                    folders = clean_folders
                    changed = True

            cached = data.get("cached_playlist")
            if cached is not None:
                if not isinstance(cached, list):
                    data.pop("cached_playlist", None)
                    cached = None
                    changed = True
                else:
                    clean_cache = []
                    for entry in cached:
                        try:
                            _idx, file_path = entry
                            if not isinstance(file_path, str) or not file_path:
                                continue
                            file_p = Path(file_path)
                        except Exception:
                            continue
                        if folders and not self._is_under_folder(file_p, folders):
                            continue
                        if not file_p.exists():
                            continue
                        clean_cache.append(entry)
                    if clean_cache != list(cached):
                        changed = True
                    if clean_cache:
                        data["cached_playlist"] = clean_cache
                        cached = clean_cache
                    else:
                        # Nothing playable left in the cache: clear it so
                        # the next load rebuilds it by scanning the folders.
                        data.pop("cached_playlist", None)
                        cached = None

            try:
                index = int(data.get("current_index", 0))
            except Exception:
                index = 0
                changed = True
            if cached:
                index = max(0, min(index, len(cached) - 1))
            else:
                index = 0
            if data.get("current_index") != index:
                data["current_index"] = index
                changed = True

            try:
                position = float(data.get("position", 0) or 0)
                if position < 0:
                    position = 0.0
            except Exception:
                position = 0.0
                changed = True
            if data.get("position") != position:
                data["position"] = position
                changed = True

            bookmarks = data.get("bookmarks")
            if bookmarks is None:
                data["bookmarks"] = {}
                changed = True
            elif not isinstance(bookmarks, dict):
                data["bookmarks"] = {}
                changed = True
            else:
                for bm_name in list(bookmarks.keys()):
                    bm = bookmarks[bm_name]
                    try:
                        bm_index = int(bm.get("index"))
                    except Exception:
                        del bookmarks[bm_name]
                        changed = True
                        continue
                    if cached and not (0 <= bm_index < len(cached)):
                        del bookmarks[bm_name]
                        changed = True

            if changed:
                repaired.append(name)

        if self.current_channel is not None and \
                self.current_channel not in self.channels:
            self.current_channel = (next(iter(self.channels.keys()))
                                    if self.channels else None)
            repaired.append("(current channel)")
        return repaired

    @staticmethod
    def _words(text):
        """Lowercase words in a name, without a leading a/the."""
        import re
        words = re.findall(r"[a-z0-9]+", str(text or "").lower())
        if words and words[0] in ("a", "the"):
            words = words[1:]
        return words

    @classmethod
    def _name_matches_file(cls, channel_name, file_path):
        """True if a file belongs to a channel named channel_name.

        The file's own title must be that show: "Friends - Season
        01.mp3" belongs to Friends, "Doctor Who - S01E01.mp3"
        belongs to Doctor Who. The folder it sits in does NOT
        decide it on its own - an Odd Squad file sitting in the
        Doctor Who folder is exactly the mix-up, and "A Killer
        Among Friends" is not Friends just because the word
        "Friends" is in it. Only a file with a generic name,
        like "S01E01.mp3" with no show in the name at all, is
        judged by its folder.
        """
        import re
        words = cls._words(channel_name)
        if not words:
            return True
        wanted = " ".join(words)
        try:
            fp = Path(str(file_path))
            base = re.split(r"\s+-\s+|\s*\(", fp.name, 1)[0].strip().lower()
            base = re.sub(r"^(?:a|the)\s+", "", base)
        except Exception:
            return False
        if base == wanted or base.startswith(wanted + " "):
            return True
        # Generic file name with no show in it: the folder decides.
        generic = re.sub(r"[^a-z]", "", base)
        if base and (re.fullmatch(r"(?:s\d+e\d+|season\s*\d+|episode\s*\d+|part\s*\d+|\d+)", base)
                     or generic in ("", "s", "e")):
            try:
                return fp.parent.name.lower().strip() == wanted
            except Exception:
                return False
        return False

    def unmix_channels(self):
        """Move files out of channels they do not belong to.

        Honey, 2026-11-23: some shows she already has are still
        mixed up with other shows - Odd Squad playing on the
        Doctor Who channel, and the wrong Friends download. This
        scans every channel's cached playlist: a file whose name
        does not match its channel is taken out of that channel.
        If another channel's name does match it, the file is
        moved to that channel instead (and that channel gains
        the file's folder, so the move survives a reload). If no
        channel matches it, it is just taken out of the wrong
        channel - the file itself is never deleted from disk.
        Returns a report: {channel_name: [file names moved out]}.
        The names of files taken out are remembered on the channel
        as "mixed_files_removed", so a later rescan of its folders
        does not put them straight back in.
        """
        report = {}
        # Work on a snapshot of names, because channels gain folders
        # while we move files around.
        for name in list(self.channels.keys()):
            data = self.channels.get(name)
            if not isinstance(data, dict):
                continue
            cached = data.get("cached_playlist")
            if not cached:
                continue
            kept = []
            removed = []
            for entry in list(cached):
                try:
                    _idx, file_path = entry
                except Exception:
                    continue
                if self._name_matches_file(name, file_path):
                    kept.append(entry)
                    continue
                # Does it belong to another channel instead?
                moved_to = None
                for other in list(self.channels.keys()):
                    if other == name:
                        continue
                    if self._name_matches_file(other, file_path):
                        moved_to = other
                        break
                if moved_to:
                    other_data = self.channels[moved_to]
                    other_cached = other_data.get("cached_playlist") or []
                    if entry not in other_cached:
                        other_cached.append(entry)
                        other_data["cached_playlist"] = other_cached
                    try:
                        parent = str(Path(str(file_path)).parent)
                        folders = other_data.get("folders") or []
                        if parent not in folders:
                            folders.append(parent)
                            other_data["folders"] = folders
                    except Exception:
                        pass
                removed.append(Path(str(file_path)).name)
                if removed:
                    data["mixed_files_removed"] = sorted(set(
                        (data.get("mixed_files_removed") or []) + removed))
            if removed:
                data["cached_playlist"] = kept
                # Keep an empty cache (not no cache) so a later load
                # does not rescan the folders and put the mixed
                # files straight back in.
                report[name] = removed
        if report:
            self.save_channels()
        return report

    def repair_channels(self):
        """Repair all loaded channels in place and save atomically.

        Returns the list of channel names that were repaired (empty if
        nothing needed fixing). Never deletes channels or the file.
        """
        if not self._load_ok:
            # The file itself could not be read; do not touch it. The
            # load already tried a backup restore, and save_channels()
            # is locked in that state to protect the original file.
            return []
        repaired = self._repair_channels_in_memory()
        if repaired:
            self._log(f"REPAIRED channels: {', '.join(repaired)}")
            self.save_channels()
        return repaired

    def _create_backup(self):
        """Create a backup of the current channels file"""
        if not self.channels_file.exists():
            return
        self.backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"channels_{timestamp}.json"
        # Two saves in the same second must not overwrite each other's backup.
        suffix = 1
        while backup_path.exists():
            backup_path = self.backup_dir / f"channels_{timestamp}_{suffix}.json"
            suffix += 1
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
            if not isinstance(data, dict) or not isinstance(data.get('channels'), dict):
                return False
            # Load the recovered data, repair any stale entries in it,
            # then write it back safely
            self.channels = data.get('channels', {})
            self.current_channel = data.get('current_channel')
            self._load_ok = True
            self._had_channels = bool(self.channels)
            self._repair_channels_in_memory()
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
            if not isinstance(data, dict) or not isinstance(data.get('channels'), dict):
                raise ValueError("channels file is missing the 'channels' section")
            self.channels = data.get('channels', {})
            self.current_channel = data.get('current_channel')
            self._load_ok = True
            self._had_channels = bool(self.channels)
            # A stale cache or out-of-range index is repairable, not a
            # reason to lose channels: fix it in place and save atomically.
            repaired = self._repair_channels_in_memory()
            if repaired:
                self._log(f"REPAIRED on load: {', '.join(repaired)}")
                self.save_channels()
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
                if isinstance(data, dict) and isinstance(data.get('channels'), dict) and data['channels']:
                    self.channels = data['channels']
                    self.current_channel = data.get('current_channel')
                    print(f"Recovered channels from backup: {backup_path.name}")
                    # Repair any stale entries in the recovered data,
                    # then write it back safely
                    self._repair_channels_in_memory()
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
    
    def peek_next_channel(self):
        """Name of the channel after the current one, without
        switching. For the TV guide: what comes up after this
        channel finishes."""
        channel_list = sorted(self.channels.keys())
        if not channel_list:
            return None
        if not self.current_channel or self.current_channel not in channel_list:
            return channel_list[0]
        idx = channel_list.index(self.current_channel)
        return channel_list[(idx + 1) % len(channel_list)]

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

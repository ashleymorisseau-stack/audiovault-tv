import os
import re
from pathlib import Path

def natural_sort_key(text):
    """Convert text to a key for natural sorting (handles numbers correctly)"""
    def atoi(text):
        return int(text) if text.isdigit() else text.lower()
    return [atoi(c) for c in re.split(r'(\d+)', str(text))]

class PlaylistManager:
    def __init__(self):
        self.folders = []
        self.playlist = []  # List of tuples: (folder_index, filepath)
        self.current_index = 0
        
    def add_folders(self, folder_paths):
        """Add folders and build playlist"""
        self.folders = sorted(folder_paths, key=natural_sort_key)
        self._build_playlist()

    def load_from_cache(self, folder_paths, cached_playlist):
        """Load playlist from cached data instead of scanning filesystem"""
        self.folders = sorted(folder_paths, key=natural_sort_key)
        self.playlist = [(idx, Path(fp)) for idx, fp in cached_playlist]
        self.current_index = 0

    def get_cache_data(self):
        """Get playlist data suitable for caching"""
        return [(idx, str(fp)) for idx, fp in self.playlist]
    
    def _build_playlist(self):
        """Build ordered playlist from all folders"""
        self.playlist = []
        for folder_idx, folder in enumerate(self.folders):
            mp3_files = self._get_mp3_files(folder)
            for filepath in mp3_files:
                self.playlist.append((folder_idx, filepath))
        self.current_index = 0
    
    def _get_mp3_files(self, folder):
        """Get all MP3 files from folder, sorted naturally"""
        folder_path = Path(folder)
        if not folder_path.exists():
            return []
        
        mp3_files = [f for f in folder_path.iterdir() if f.suffix.lower() == '.mp3']
        return sorted(mp3_files, key=lambda x: natural_sort_key(x.name))
    
    def get_current(self):
        """Get current file info"""
        if not self.playlist or self.current_index >= len(self.playlist):
            return None
        return self.playlist[self.current_index]
    
    def next_file(self):
        """Move to next file"""
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            return True
        return False
    
    def prev_file(self):
        """Move to previous file"""
        if self.current_index > 0:
            self.current_index -= 1
            return True
        return False
    
    def next_folder(self):
        """Jump to first file of next folder"""
        if not self.playlist:
            return False
        
        current_folder_idx = self.playlist[self.current_index][0]
        for i in range(self.current_index + 1, len(self.playlist)):
            if self.playlist[i][0] > current_folder_idx:
                self.current_index = i
                return True
        return False
    
    def prev_folder(self):
        """Jump to first file of previous folder"""
        if not self.playlist:
            return False
        
        current_folder_idx = self.playlist[self.current_index][0]
        
        # Find start of current folder
        for i in range(self.current_index, -1, -1):
            if self.playlist[i][0] < current_folder_idx:
                self.current_index = i
                return True
        
        # If already at first folder, go to its beginning
        if current_folder_idx > 0:
            self.current_index = 0
            return True
        
        return False
    
    def get_current_folder_name(self):
        """Get name of current folder"""
        current = self.get_current()
        if current:
            folder_idx = current[0]
            return Path(self.folders[folder_idx]).name
        return ""
    
    def get_current_file_name(self):
        """Get name of current file"""
        current = self.get_current()
        if current:
            return Path(current[1]).name
        return ""
    
    def set_index(self, index):
        """Set current index directly"""
        if 0 <= index < len(self.playlist):
            self.current_index = index
            return True
        return False

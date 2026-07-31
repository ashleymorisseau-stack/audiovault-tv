import logging
import os
import requests
from pathlib import Path
from datetime import datetime

S3_LOG_URL = "https://mp3-player-updates.s3.amazonaws.com/logs/"

class PlayerLogger:
    def __init__(self, log_file="player_log.txt"):
        """Initialize logger"""
        self.log_file = Path(log_file)
        self.username = os.environ.get("USERNAME", os.environ.get("USER", "unknown"))
        
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()  # Also print to console
            ]
        )
        self.logger = logging.getLogger('MP3Player')
        self.logger.info("=" * 60)
        self.logger.info("AudioVault TV Session Started")
        self.logger.info("=" * 60)
    
    def log_playback(self, action, details=""):
        """Log playback events"""
        self.logger.info(f"PLAYBACK: {action} {details}")
    
    def log_navigation(self, action, from_info, to_info):
        """Log navigation events"""
        self.logger.info(f"NAVIGATION: {action}")
        self.logger.info(f"  From: {from_info}")
        self.logger.info(f"  To: {to_info}")
    
    def log_channel(self, action, channel_name, details=""):
        """Log channel events"""
        self.logger.info(f"CHANNEL: {action} - {channel_name} {details}")
    
    def log_bookmark(self, action, bookmark_name, file_info=""):
        """Log bookmark events"""
        self.logger.info(f"BOOKMARK: {action} - {bookmark_name} {file_info}")
    
    def log_voice(self, action, command=""):
        """Log voice control events"""
        self.logger.info(f"VOICE: {action} {command}")
    
    def log_error(self, error_msg):
        """Log errors"""
        self.logger.error(f"ERROR: {error_msg}")
    
    def log_auto_advance(self, from_file, to_file, reason=""):
        """Log auto-advance events"""
        self.logger.info(f"AUTO-ADVANCE: {reason}")
        self.logger.info(f"  From: {from_file}")
        self.logger.info(f"  To: {to_file}")
    
    def log_playlist_info(self, total_files, current_index, current_file):
        """Log playlist state"""
        self.logger.info(f"PLAYLIST STATE: Index {current_index}/{total_files-1} - {current_file}")
    
    def upload_log(self):
        """Upload log file to S3. Raises exception on failure."""
        if not self.log_file.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_file}")
        
        s3_key = f"{self.username}_log.txt"
        url = S3_LOG_URL + s3_key
        
        with open(self.log_file, 'rb') as f:
            r = requests.put(url, data=f)
        
        if r.status_code not in (200, 201):
            raise Exception(f"S3 returned status {r.status_code}: {r.text[:200]}")

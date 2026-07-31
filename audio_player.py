import pygame
import os
from pathlib import Path

class AudioPlayer:
    def __init__(self):
        pygame.mixer.init()
        self.current_file = None
        self.is_playing = False
        self.paused_position = 0
        self.start_position = 0  # Track where playback started
        self.last_position = 0
        self.position_stuck_count = 0
        
    def load(self, filepath):
        """Load an audio file"""
        if os.path.exists(filepath):
            pygame.mixer.music.load(filepath)
            self.current_file = filepath
            self.paused_position = 0
            return True
        return False
    
    def play(self):
        """Start or resume playback"""
        if self.paused_position > 0:
            pygame.mixer.music.play(start=self.paused_position)
            self.start_position = self.paused_position
            self.paused_position = 0
        else:
            pygame.mixer.music.play()
            self.start_position = 0
        self.is_playing = True
    
    def pause(self):
        """Pause playback"""
        if self.is_playing:
            self.paused_position = self.get_position()
            pygame.mixer.music.stop()
            self.is_playing = False
    
    def unpause(self):
        """Resume from pause"""
        if self.current_file and not self.is_playing:
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play(start=self.paused_position)
            self.start_position = self.paused_position
            self.is_playing = True
    
    def toggle_pause(self):
        """Toggle play/pause"""
        if self.is_playing:
            self.pause()
        else:
            self.unpause()
    
    def stop(self):
        """Stop playback"""
        pygame.mixer.music.stop()
        self.is_playing = False
        self.paused_position = 0
    
    def get_position(self):
        """Get current position in seconds"""
        if self.is_playing:
            pos = pygame.mixer.music.get_pos() / 1000.0
            return max(0, pos + self.start_position)
        return self.paused_position
    
    def set_position(self, seconds):
        """Seek to position in seconds"""
        if self.current_file:
            was_playing = self.is_playing
            pygame.mixer.music.stop()
            pygame.mixer.music.load(self.current_file)
            self.paused_position = seconds
            if was_playing:
                pygame.mixer.music.play(start=seconds)
                self.is_playing = True
    
    def rewind(self, seconds=10):
        """Rewind by specified seconds"""
        pos = self.get_position()
        new_pos = max(0, pos - seconds)
        self.set_position(new_pos)
    
    def fastforward(self, seconds=10):
        """Fast forward by specified seconds"""
        pos = self.get_position()
        self.set_position(pos + seconds)
    
    def is_busy(self):
        """Check if audio is currently playing"""
        busy = pygame.mixer.music.get_busy()
        
        if not busy:
            # Music has stopped according to pygame
            # Reset counters
            self.position_stuck_count = 0
            self.last_position = 0
            return False
        
        # Music is playing
        return True

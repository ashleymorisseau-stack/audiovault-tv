import pygame
import os
from pathlib import Path

# pygame's own music-end signal. When a track really finishes,
# pygame posts this event type to the event queue. It is the only
# end-of-file signal this player trusts: it is posted by pygame
# itself when the music ends, not inferred from the mixer being
# quiet for a moment, and it costs nothing — no counting of quiet
# ticks, and no loading the whole file into memory to measure it.
# (Loading a whole episode with Sound.get_length() would decode
# tens of minutes of audio into memory; that is why length-based
# end detection is NOT used here.)
MUSIC_END_EVENT_TYPE = getattr(pygame, "USEREVENT", 24) + 1


class AudioPlayer:
    def __init__(self):
        pygame.mixer.init()
        self.current_file = None
        self.is_playing = False
        self.paused_position = 0
        self.start_position = 0  # Track where playback started
        self.last_position = 0
        self.position_stuck_count = 0
        self._music_end_seen = False
        try:
            pygame.mixer.music.set_endevent(MUSIC_END_EVENT_TYPE)
        except Exception:
            pass

    def _poll_music_end_events(self):
        """Drain pygame's event queue for the music-end event.

        Returns True once pygame has said the current track
        finished, and stays True until clear_music_end() is
        called (a new track starting). No other pygame events
        are used by this app, so draining the queue here loses
        nothing.
        """
        try:
            events = pygame.event.get()
        except Exception:
            return self._music_end_seen
        for event in events or []:
            if getattr(event, "type", None) == MUSIC_END_EVENT_TYPE:
                self._music_end_seen = True
        return self._music_end_seen

    def music_ended(self):
        """True if pygame itself said the current track finished.

        This is the end-of-file signal: pygame posts the event
        only when the music ends, never for a momentary mixer
        hiccup or a quiet passage in the middle of a file.
        """
        return self._poll_music_end_events()

    def clear_music_end(self):
        """Forget any music-end signal, e.g. a new track starts.

        Also drains the queue, so a stale end event left over
        from the previous track can never be mistaken for this
        track ending.
        """
        self._music_end_seen = False
        try:
            pygame.event.get()
        except Exception:
            pass

    def music_position_ms(self):
        """Raw pygame position in ms, or None if unavailable.

        pygame returns -1 when the music is not playing at all.
        Used only as a backup end check (see main.py _on_timer):
        -1 plus the mixer not busy, well into a file, means the
        music really stopped — never on its own, and never by
        counting how long it has been quiet.
        """
        try:
            pos = pygame.mixer.music.get_pos()
        except Exception:
            return None
        return pos if isinstance(pos, (int, float)) else None

    def load(self, filepath):
        """Load an audio file"""
        if os.path.exists(filepath):
            pygame.mixer.music.load(filepath)
            self.current_file = filepath
            self.paused_position = 0
            self.clear_music_end()
            return True
        return False

    def play(self):
        """Start or resume playback"""
        # A fresh stream: any end signal left over from the
        # previous track must not carry over into this one.
        self.clear_music_end()
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
            # Stopping for a pause is not the track finishing:
            # some pygame versions post an end event on stop(),
            # so forget it here.
            self.clear_music_end()

    def unpause(self):
        """Resume from pause"""
        if self.current_file and not self.is_playing:
            self.clear_music_end()
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
        # Stopping is not the track finishing (see pause()).
        self.clear_music_end()
    
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
            # Seeking restarts the stream, so any end signal
            # from before the seek must not carry over.
            self.clear_music_end()
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

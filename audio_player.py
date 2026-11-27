"""Audio playback engine: soundfile (decode) + sounddevice (output).

Replaces the old pygame.mixer engine. pygame had no wheels for
current Python on macOS (and needed SDL headers to build), while
sounddevice was already a dependency for the microphone, and
soundfile decodes MP3 and WAV the same way on every platform.

The public AudioPlayer interface is unchanged from the pygame
version, so main.py's auto-advance logic keeps working:

- music_ended() is the end-of-file signal. The soundfile read
  itself reports it when the stream runs out of data — the same
  trust model as pygame's end event: a quiet passage mid-file
  never reports an ending, and a stream stopped for pause/seek
  clears the flag (see clear_music_end()).
- music_position_ms() mirrors pygame's music.get_pos():
  milliseconds since the last play(), or -1 when nothing plays.
- Files are streamed in blocks, never decoded whole into
  memory, so an hour-long episode costs no RAM.
"""

import os
import threading

import sounddevice as sd
import soundfile as sf


class AudioPlayer:
    """Streams one audio file at a time through the default output."""

    def __init__(self):
        self.current_file = None
        self.is_playing = False
        self.paused_position = 0
        self.start_position = 0
        self._sound_file = None
        self._stream = None
        self._samplerate = 44100
        self._frames_done = 0
        self._music_end_seen = False
        self._lock = threading.Lock()

    def _open_sound_file(self):
        """(Re)open the current file for reading, positioned at 0."""
        self._close_sound_file()
        self._sound_file = sf.SoundFile(str(self.current_file))
        self._samplerate = self._sound_file.samplerate

    def _close_sound_file(self):
        if self._sound_file is not None:
            try:
                self._sound_file.close()
            except Exception:
                pass
            self._sound_file = None

    def _close_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _callback(self, outdata, frames, _time, _status):
        """Feed the output stream from the open file, block by block."""
        try:
            data = self._sound_file.read(frames, dtype="float32",
                                         always_2d=True)
        except Exception:
            data = []
        n = len(data)
        if n:
            outdata[:n] = data
            self._frames_done += n
        if n < frames:
            outdata[n:] = 0.0
            # The file ran out: this is the end-of-file signal.
            # is_playing stays True (same as the pygame engine:
            # main.py's auto-advance runs inside its "playing"
            # timer branch and needs the flag still set when
            # the end signal arrives).
            self._music_end_seen = True
            raise sd.CallbackStop()

    def _start_stream(self, start_seconds):
        self._close_stream()
        self._open_sound_file()
        start_frame = int(max(0.0, start_seconds) * self._samplerate)
        # Never seek past the end: libsndfile refuses it, and the
        # right behavior at the end is the immediate end signal.
        start_frame = min(start_frame, max(0, len(self._sound_file)))
        if start_frame > 0:
            self._sound_file.seek(start_frame)
        self._frames_done = 0
        self._music_end_seen = False
        channels = self._sound_file.channels
        self._stream = sd.OutputStream(
            samplerate=self._samplerate,
            channels=channels,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()
        self.is_playing = True

    def music_ended(self):
        """True once the current file really ran out of data.

        Stays True until clear_music_end() (a new track starts).
        """
        return self._music_end_seen

    def clear_music_end(self):
        """Forget any end signal, e.g. a new track starts."""
        self._music_end_seen = False

    def music_position_ms(self):
        """Milliseconds since the last play(), or -1 when stopped.

        Backup end check only (see main.py _on_timer): -1 plus
        not busy, well into a file, means the music really
        stopped. Never trusted on its own.
        """
        if not self.is_playing or self._music_end_seen:
            return -1
        return int(self._frames_done / float(self._samplerate) * 1000)

    def load(self, filepath):
        """Load an audio file"""
        if os.path.exists(filepath):
            with self._lock:
                self._close_stream()
                self.current_file = filepath
                self.paused_position = 0
                self.clear_music_end()
            return True
        return False

    def play(self):
        """Start or resume playback"""
        if not self.current_file:
            return
        with self._lock:
            start = self.paused_position
            self.paused_position = 0
            self.start_position = start
            self._start_stream(start)

    def pause(self):
        """Pause playback"""
        if self.is_playing:
            position = self.get_position()
            with self._lock:
                self._close_stream()
                self._close_sound_file()
                self.paused_position = position
                self.is_playing = False
            # Stopping for a pause is not the track finishing.
            self.clear_music_end()

    def unpause(self):
        """Resume from pause"""
        if self.current_file and not self.is_playing:
            with self._lock:
                self.start_position = self.paused_position
                self._start_stream(self.paused_position)
                self.paused_position = 0

    def toggle_pause(self):
        """Toggle play/pause"""
        if self.is_playing:
            self.pause()
        else:
            self.unpause()

    def stop(self):
        """Stop playback"""
        with self._lock:
            self._close_stream()
            self._close_sound_file()
            self.is_playing = False
            self.paused_position = 0
            self.start_position = 0
        # Stopping is not the track finishing (see pause()).
        self.clear_music_end()

    def unload(self):
        """Release the current file (e.g. so it can be deleted)."""
        self.stop()
        self.current_file = None

    def get_position(self):
        """Get current position in seconds"""
        if self.is_playing:
            elapsed = self._frames_done / float(self._samplerate)
            return max(0.0, self.start_position + elapsed)
        return self.paused_position

    def set_position(self, seconds):
        """Seek to position in seconds"""
        if not self.current_file:
            return
        was_playing = self.is_playing
        with self._lock:
            self._close_stream()
            self.paused_position = seconds
            # Seeking restarts the stream, so any end signal
            # from before the seek must not carry over.
            self.clear_music_end()
            if was_playing:
                self.start_position = seconds
                self._start_stream(seconds)
                self.paused_position = 0

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
        """True only while sound is actually flowing: a finished
        file (end seen) and a stopped stream are both not busy,
        the way pygame's music.get_busy() behaved."""
        return (self.is_playing and not self._music_end_seen
                and self._stream is not None)


class ClipPlayer:
    """Plays short clips (voice answers, chimes) one at a time.

    Replaces the single pygame mixer channel Samantha's voice
    used: one clip at a time, a new clip cuts the old one off,
    and a show playing through AudioPlayer is never touched —
    clips use their own stream, not the show's.
    """

    def __init__(self):
        self._stream = None
        self._data = None
        self._pos = 0
        self._busy = False
        self._generation = 0
        self._lock = threading.Lock()

    def _callback(self, outdata, frames, _time, _status):
        remaining = 0 if self._data is None else len(self._data) - self._pos
        n = min(frames, remaining)
        if n:
            outdata[:n] = self._data[self._pos:self._pos + n]
            self._pos += n
        if n < frames:
            outdata[n:] = 0.0
        if self._data is not None and self._pos >= len(self._data):
            raise sd.CallbackStop()

    def _on_stopped(self, generation):
        # Runs on PortAudio's thread right after the stream
        # stops — must NOT take any lock here: stop() may be
        # waiting on this callback while holding the lock.
        # Plain int/bool reads and writes are atomic under the
        # GIL, which is all this needs. A newer clip may
        # already own the player when this (older) stream's
        # callback fires, so only the current generation may
        # clear the busy flag.
        if generation == self._generation:
            self._busy = False

    def play_file(self, path):
        """Play a clip now, cutting off any clip still playing."""
        data, samplerate = sf.read(str(path), dtype="float32",
                                   always_2d=True)
        with self._lock:
            self._stop_locked()
            self._data = data
            self._pos = 0
            self._generation += 1
            generation = self._generation
            try:
                self._stream = sd.OutputStream(
                    samplerate=samplerate,
                    channels=data.shape[1],
                    dtype="float32",
                    callback=self._callback,
                    finished_callback=lambda: self._on_stopped(generation),
                )
                self._stream.start()
                self._busy = True
            except Exception:
                self._busy = False
                self._stop_locked()
                raise

    def busy(self):
        return self._busy

    def stop(self):
        with self._lock:
            self._stop_locked()
            self._busy = False

    def _stop_locked(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        self._data = None
        self._pos = 0


_clip_player = None
_clip_player_lock = threading.Lock()


def clip_player():
    """The one ClipPlayer every Samantha clip plays through."""
    global _clip_player
    with _clip_player_lock:
        if _clip_player is None:
            _clip_player = ClipPlayer()
        return _clip_player

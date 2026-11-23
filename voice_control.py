import json
import queue
import re
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from pathlib import Path


def _clean_query(query):
    """Tidy a spoken search/download phrase into a show or movie name."""
    if not query:
        return ""
    query = query.lower().strip()
    # Drop trailing "and download it / and download" left over from
    # "search for X and download it".
    query = re.sub(r"\s+and\s+download(?:\s+it|\s+that|\s+this)?\s*$", "", query)
    # Drop a trailing "on audiovault / on audio vault / from audiovault".
    query = re.sub(r"\s+(?:on|from)\s+(?:audio\s*?vault|audiovault)\s*$", "", query)
    query = re.sub(r"\s+please\s*$", "", query)
    query = query.strip(" .,")
    # Drop a leading "for / a / an / the" left over from a split.
    query = re.sub(r"^(?:for|a|an|the)\s+", "", query)
    return re.sub(r"\s+", " ", query).strip()


def _kind_from_text(text):
    """'movies' when the phrase names a movie/film, otherwise 'shows'."""
    if "movie" in text or "film" in text:
        return "movies"
    return "shows"


class VoiceControl:
    # Honey asked for more time to speak, 2026-11-23. These used to be
    # 5 seconds for a one-time command and only 3 seconds after "Sam",
    # which cut off slow speech and long show names.
    ONE_TIME_LISTEN_SECONDS = 10
    WAKE_WORD_COMMAND_SECONDS = 8

    def __init__(self, model_path="vosk-model-small-en-us-0.15"):
        """Initialize voice recognition"""
        self.model_path = Path(model_path)
        self.model = None
        self.recognizer = None
        self.is_listening = False
        self.wake_word_active = False
        self.audio_queue = queue.Queue()
        self.wake_word = "sam"

        # Initialize model
        if self.model_path.exists():
            self.model = Model(str(self.model_path))
            self.recognizer = KaldiRecognizer(self.model, 16000)
        else:
            raise FileNotFoundError(f"Vosk model not found at {model_path}")

    def audio_callback(self, indata, frames, time, status):
        """Callback for audio stream"""
        if status:
            print(f"Audio status: {status}")
        self.audio_queue.put(bytes(indata))

    def listen(self, duration=ONE_TIME_LISTEN_SECONDS):
        """Listen for speech for specified duration (seconds)"""
        if not self.model:
            return None

        self.is_listening = True
        self.recognizer.Reset()

        try:
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                                 channels=1, callback=self.audio_callback):

                import time
                start_time = time.time()

                while time.time() - start_time < duration and self.is_listening:
                    data = self.audio_queue.get()

                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip()
                        if text:
                            return text

                # Get final result
                result = json.loads(self.recognizer.FinalResult())
                text = result.get('text', '').strip()
                return text if text else None

        except Exception as e:
            print(f"Voice recognition error: {e}")
            return None
        finally:
            self.is_listening = False

    def listen_for_wake_word(self, callback):
        """Continuously listen for wake word, then command"""
        if not self.model:
            return

        self.wake_word_active = True
        self.recognizer.Reset()

        try:
            with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                                 channels=1, callback=self.audio_callback):

                while self.wake_word_active:
                    data = self.audio_queue.get()

                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip().lower()

                        if text:
                            # Check for wake word
                            if self.wake_word in text:
                                # Wake word detected, notify callback
                                callback('wake_word_detected')

                                # "Sam, play" often arrives as one
                                # utterance, so keep anything said after
                                # "Sam" in that same breath as the command
                                # instead of throwing it away and waiting
                                # for a second utterance.
                                remainder = text.split(self.wake_word, 1)[1]
                                remainder = remainder.strip(" ,").strip()
                                if remainder:
                                    callback('command', remainder)
                                    self.recognizer.Reset()
                                    continue

                                # Listen for command after wake word.
                                # Honey asked for more time here too:
                                # 8 seconds instead of 3.
                                self.recognizer.Reset()
                                import time
                                start_time = time.time()
                                command_text = ""

                                while time.time() - start_time < self.WAKE_WORD_COMMAND_SECONDS and self.wake_word_active:
                                    data = self.audio_queue.get()

                                    if self.recognizer.AcceptWaveform(data):
                                        result = json.loads(self.recognizer.Result())
                                        command_text = result.get('text', '').strip()
                                        if command_text:
                                            break

                                # Get final result if nothing yet
                                if not command_text:
                                    result = json.loads(self.recognizer.FinalResult())
                                    command_text = result.get('text', '').strip()

                                # Send command to callback
                                if command_text:
                                    callback('command', command_text)
                                else:
                                    callback('no_command')

                                # Reset for next wake word
                                self.recognizer.Reset()

        except Exception as e:
            print(f"Wake word listening error: {e}")
            callback('error', str(e))
        finally:
            self.wake_word_active = False

    def stop_listening(self):
        """Stop listening"""
        self.is_listening = False
        self.wake_word_active = False

    def parse_command(self, text):
        """Parse recognized text into a command"""
        if not text:
            return None

        text = text.lower().strip()

        # Download status / cancel: check before the generic "download".
        if 'download status' in text or 'downloads status' in text or 'what is downloading' in text:
            return 'download_status'
        if 'cancel download' in text or 'stop download' in text:
            return 'cancel_downloads'
        # "download it" / "download the first one" means the last search
        # result. Skip this when the sentence is "search for X and
        # download it", which names X and is handled below.
        if 'and download' not in text and re.search(
                r"\bdownload\s+(?:it|that|this|the first(?: one| result)?)\b", text):
            return 'download_first'

        # --- AudioVault search and download ---
        # These are checked before play/pause/navigation, so a show name
        # containing one of those words (for example "play") does not
        # swallow the search or download.
        download = self._parse_download(text)
        if download is not None:
            return download
        search = self._parse_search(text)
        if search is not None:
            return search

        # Play/Pause commands
        if any(word in text for word in ['play', 'pause', 'resume', 'stop']):
            return 'play_pause'

        # Channel commands
        if 'next channel' in text:
            return 'next_channel'
        if 'previous channel' in text or 'last channel' in text:
            return 'prev_channel'

        # Navigation commands
        if 'next file' in text or 'next track' in text:
            return 'next_file'
        if 'previous file' in text or 'previous track' in text or 'last file' in text:
            return 'prev_file'
        if 'next folder' in text or 'next season' in text:
            return 'next_folder'
        if 'previous folder' in text or 'previous season' in text or 'last folder' in text:
            return 'prev_folder'

        # Seek commands
        if 'rewind' in text or 'go back' in text or 'back' in text:
            return 'rewind'
        if 'forward' in text or 'skip' in text or 'fast forward' in text:
            return 'fastforward'

        # A bare "download" with no show named: keep the old behaviour
        # (show recent additions to pick from).
        if 'download' in text:
            return 'download'

        return None

    def _parse_search(self, text):
        """Return ('search_shows'|'search_movies', query) or a plain
        search command, or None when this is not a search."""
        kind = _kind_from_text(text)

        patterns = [
            # "search for a TV show Close Enough"
            # "find a movie Ghostbusters"
            r"(?:search|find|look for|look up)\s+(?:for\s+)?(?:a\s+|an\s+|the\s+)?"
            r"(?:tv\s+shows?|shows?|movies?|films?)\s+(?:called\s+|named\s+)?(.+)",
            # "search audiovault for Close Enough"
            r"search\s+(?:audio\s*?vault|audiovault)\s+(?:for\s+)?(.+)",
            r"find\s+(?:audio\s*?vault|audiovault)\s+(?:for\s+)?(.+)",
            # "search for Close Enough on audiovault"
            r"(?:search|find)\s+(?:for\s+)?(.+?)\s+on\s+(?:audio\s*?vault|audiovault)\b",
            # "search for Close Enough" / "find Close Enough"
            r"(?:search|find)\s+(?:for\s+)?(.+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                query = _clean_query(match.group(1))
                # "search movies" / "search tv" with no name is a plain
                # search, not a search for a show called "movies".
                if query in ("movie", "movies", "film", "films",
                             "show", "shows", "tv", "tv show", "tv shows"):
                    return f"search_{kind}"
                if query:
                    return (f"search_{kind}", query)
                return f"search_{kind}"

        # Old exact phrases, kept for compatibility.
        if 'search movie' in text or 'find movie' in text:
            return 'search_movies'
        if 'search show' in text or 'find show' in text or 'search tv' in text:
            return 'search_shows'
        return None

    def _parse_download(self, text):
        """Return ('download_shows'|'download_movies', query) when Honey
        names something to download, or None when this is not a
        named download."""
        if 'download' not in text:
            return None

        kind = _kind_from_text(text)

        # "search and download Close Enough" / "find and download it"
        match = re.search(
            r"(?:search|find)\s+(?:for\s+)?(?:a\s+|an\s+|the\s+)?"
            r"(?:tv\s+shows?|shows?|movies?|films?)?\s*(?:called\s+|named\s+)?"
            r"(.+?)\s+and\s+download(?:\s+it|\s+that|\s+this)?\s*$",
            text)
        if match:
            query = _clean_query(match.group(1))
            if query:
                return (f"download_{kind}", query)

        # "download a TV show Close Enough" / "download Close Enough"
        match = re.search(
            r"download\s+(?:a\s+|an\s+|the\s+)?"
            r"(?:tv\s+shows?|shows?|movies?|films?)?\s*(?:called\s+|named\s+)?(.+)",
            text)
        if match:
            query = _clean_query(match.group(1))
            # "download status" and "download it" are handled above;
            # anything left here is a named download.
            if query and query not in ("status", "it", "that", "this"):
                return (f"download_{kind}", query)
        return None

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
    # Drop a trailing "on youtube / from youtube".
    query = re.sub(r"\s+(?:on|from)\s+(?:you\s*?tube|youtube)\s*$", "", query)
    query = re.sub(r"\s+please\s*$", "", query)
    # Honey, 2026-11-23: "search for Friends the sitcom new
    # description" returned nothing on AudioVault, because the site
    # search matches the show title, not those extra words.
    # "friends new description" -> 0 results, "friends the sitcom"
    # -> 0 results, but "friends" -> 54 results, including the exact
    # "Friends - Season 01 (1994) [US New Description]". So drop
    # those descriptive words here; main.py then picks the exact
    # show, preferring a New Description version, instead of
    # taking the first alphabetical result ("A Killer Among
    # Friends").
    # Drop "new description" first, then "the sitcom", then
    # "new description" again, so "friends the sitcom new
    # description" cleans all the way down to "friends".
    query = re.sub(r"\s+(?:us\s+)?new\s+description\s*$", "", query)
    query = re.sub(
        r"\s+(?:the\s+)?(?:sitcom|tv\s+show|tv\s+series|television\s+show)\s*$",
        "", query)
    query = re.sub(r"\s+(?:us\s+)?new\s+description\s*$", "", query)
    query = query.strip(" .,")
    # Drop a leading "for / a / an / the" left over from a split.
    query = re.sub(r"^(?:for|a|an|the)\s+", "", query)
    return re.sub(r"\s+", " ", query).strip()


def _kind_from_text(text):
    """'movies' when the phrase names a movie/film, otherwise 'shows'."""
    if "movie" in text or "film" in text:
        return "movies"
    return "shows"


def _clean_name(name):
    """Tidy a spoken name into a short display name, or '' if unusable."""
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"\s+please\s*$", "", name)
    name = name.strip(" .,!")
    # A name is one or two words; anything longer is probably a
    # sentence Vosk misheard, not a name.
    words = [w for w in re.split(r"\s+", name) if w]
    words = [w for w in words if re.fullmatch(r"[a-z][a-z'\-]*", w)]
    if not words:
        return ""
    words = words[:2]
    return " ".join(w.capitalize() for w in words)


class VoiceControl:
    # Honey asked for more time to speak, 2026-11-23. These used to be
    # 5 seconds for a one-time command and only 3 seconds after "Samantha",
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
        self.wake_word = "samantha"

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

                                # "Samantha, play" often arrives as one
                                # utterance, so keep anything said after
                                # "Samantha" in that same breath as the command
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

        # --- Name: Honey asked 2026-11-23 that Samantha learn her
        # name when she tells it to her, and remember it. Checked
        # before search/download/play, so "my name is Honey" is not
        # swallowed by another command.
        name_command = self._parse_name_command(text)
        if name_command is not None:
            return name_command

        # --- Live TV: Honey asked 2026-11-23 that Samantha also
        # play live channels, like Game Show Network and other
        # channels. Checked before YouTube/AudioVault search and
        # before generic "play", so "play Game Show Network live"
        # is not swallowed by play/pause or by a show search.
        live = self._parse_live_tv(text)
        if live is not None:
            return live

        # --- Delete a channel's downloads: Honey asked 2026-11-23
        # to get rid of the downloads for "A Killer Among Friends"
        # (the wrong Friends download). Checked before the generic
        # download handlers, so "delete ... downloads" is not
        # treated as a download request.
        delete_dl = self._parse_delete_downloads(text)
        if delete_dl is not None:
            return delete_dl

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

        # --- YouTube search and download ---
        # Checked before AudioVault, so "search for X on YouTube" is
        # not swallowed by the plain AudioVault "search for X" pattern.
        # Honey asked for the same voice search and download for
        # YouTube as for AudioVault, 2026-11-23.
        yt_download = self._parse_youtube_download(text)
        if yt_download is not None:
            return yt_download
        yt_search = self._parse_youtube_search(text)
        if yt_search is not None:
            return yt_search

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

    def _parse_name_command(self, text):
        """Name commands. Returns ('set_name', name), 'what_is_my_name',
        'forget_name', 'what_is_your_name' or 'greet', or None.

        Samantha learns the name only when Honey tells it to her, by
        voice — "my name is Honey" / "call me Honey" — and main.py
        saves it with _set_user_name, so she remembers it after a
        restart. She never guesses a name she has not been told.
        """
        # In one-time mode the whole utterance can start with
        # "Samantha, ..."; in wake-word mode it is already stripped.
        text = re.sub(r"^(?:hey\s+)?samantha[,\s]+", "", text.strip())

        if re.search(r"\bforget my name\b|\bforget what my name is\b",
                     text):
            return 'forget_name'
        if re.search(r"\bwhat(?:'s| is) my name\b"
                     r"|\bdo you know my name\b"
                     r"|\bwho am i\b"
                     r"|\bwhat do you call me\b", text):
            return 'what_is_my_name'
        if re.search(r"\bwhat(?:'s| is) your name\b|\bwho are you\b",
                     text):
            return 'what_is_your_name'
        if re.search(r"^(?:hello|hi|hey|good morning|good afternoon"
                     r"|good evening)\b", text):
            return 'greet'

        match = re.search(
            r"(?:my name is|my name's|call me|remember my name is"
            r"|remember my name's|please call me|you can call me)"
            r"\s+([a-z][a-z' \-]{0,30})",
            text)
        if match:
            name = _clean_name(match.group(1))
            if name and name.lower() not in ("samantha", "you", "me"):
                return ('set_name', name)
        return None

    def _parse_live_tv(self, text):
        """Return a live-TV command, or None.

        'play_live_tv' | ('play_live_channel', name) |
        ('search_live_channels', name) | 'stop_live_tv'
        """
        if 'live' not in text and 'game show network' not in text:
            return None
        if re.search(r"\bstop\s+(?:the\s+)?live\s+(?:tv|television|channel)\b", text):
            return 'stop_live_tv'
        # "search live channels for Game Show Network"
        m = re.search(r"(?:search|find)\s+(?:live\s+)?(?:tv\s+)?channels?\s+(?:for\s+)?(.+)", text)
        if m and 'live' in text:
            q = _clean_query(m.group(1))
            q = re.sub(r"\s+(?:live|channel|channels|tv|television)\s*$", "", q)
            if q:
                return ('search_live_channels', q)
            return 'search_live_channels'
        # "play Game Show Network live" / "play live channel Game
        # Show Network" / "watch Game Show Network live"
        m = re.search(
            r"(?:play|watch|tune\s+(?:in\s+)?to)\s+(?:a\s+|an\s+|the\s+)?"
            r"(?:live\s+)?(?:tv\s+)?(?:channel\s+)?(.+?)\s+live\b", text)
        if m:
            q = _clean_query(m.group(1))
            if q:
                return ('play_live_channel', q)
        m = re.search(
            r"(?:play|watch|tune\s+(?:in\s+)?to)\s+(?:a\s+|an\s+|the\s+)?"
            r"live\s+(?:tv\s+|television\s+)?(?:channel\s+)?(.+)", text)
        if m:
            q = _clean_query(m.group(1))
            if q in ("tv", "television", "channel", "channels"):
                return 'play_live_tv'
            if q:
                return ('play_live_channel', q)
            return 'play_live_tv'
        if re.search(r"\bplay\s+(?:the\s+)?live\s+(?:tv|television|channels?)\b", text):
            return 'play_live_tv'
        if 'game show network' in text and re.search(r"\b(?:play|watch)\b", text):
            return ('play_live_channel', 'game show network')
        return None

    def _parse_delete_downloads(self, text):
        """Return ('delete_channel_downloads', name),
        'delete_channel_downloads' (current channel), or None.

        "delete A Killer Among Friends downloads" -> the named
        channel. Vosk may hear "amongst" for "among", so normalise
        it here; main.py matches "killer among friends" either way.
        """
        if not re.search(r"\b(?:delete|remove|get rid of)\b", text):
            return None
        if 'download' not in text and 'channel' not in text:
            return None
        text = text.replace('amongst', 'among')
        m = re.search(
            r"(?:delete|remove|get rid of)\s+(?:the\s+)?(.+?)\s+downloads?\b", text)
        if m:
            q = _clean_query(m.group(1))
            q = re.sub(r"^(?:the\s+)?channel\s+", "", q)
            if q and q not in ('them', 'it', 'those', 'these'):
                return ('delete_channel_downloads', q)
            return 'delete_channel_downloads'
        m = re.search(
            r"(?:delete|remove|get rid of)\s+(?:the\s+)?downloads?\s+(?:for|of)\s+(?:the\s+)?(.+)", text)
        if m:
            q = _clean_query(m.group(1))
            if q:
                return ('delete_channel_downloads', q)
        if re.search(r"\bdelete\s+(?:the\s+)?channel\b", text):
            return 'delete_channel_downloads'
        return None

    def _parse_youtube_search(self, text):
        """Return ('search_youtube', query) or 'search_youtube', or
        None when this is not a YouTube search."""
        if "youtube" not in text and "you tube" not in text:
            return None
        text = text.replace("you tube", "youtube")

        patterns = [
            # "search for a TV show Close Enough on YouTube"
            r"(?:search|find|look for|look up)\s+(?:for\s+)?(?:a\s+|an\s+|the\s+)?"
            r"(.+?)\s+(?:on|from)\s+youtube\b",
            # "search YouTube for Close Enough" / "find YouTube Close Enough"
            r"(?:search|find)\s+youtube\s+(?:for\s+)?(.+)",
            # "search on YouTube for Close Enough"
            r"(?:search|find)\s+(?:on\s+)?youtube\s+(?:for\s+)?(.+)",
            # "search Close Enough on YouTube" is caught by the first
            # pattern; "search Close Enough YouTube" by this one.
            r"(?:search|find)\s+(?:for\s+)?(.+?)\s+youtube\s*$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                query = _clean_query(match.group(1))
                query = re.sub(
                    r"^(?:tv\s+shows?|shows?|movies?|films?|videos?|songs?|music)\s+",
                    "", query)
                if query and query not in ("youtube",):
                    return ("search_youtube", query)
                return "search_youtube"

        if re.search(r"\b(?:search|find)\s+youtube\b", text):
            return "search_youtube"
        return None

    def _parse_youtube_download(self, text):
        """Return ('download_youtube', query) when Honey names
        something to download from YouTube, or None otherwise."""
        if "download" not in text:
            return None
        if "youtube" not in text and "you tube" not in text:
            return None
        text = text.replace("you tube", "youtube")

        patterns = [
            # "search and download Close Enough on YouTube"
            r"(?:search|find)\s+(?:for\s+)?(?:a\s+|an\s+|the\s+)?"
            r"(.+?)\s+and\s+download(?:\s+it|\s+that|\s+this)?\s*"
            r"(?:(?:on|from)\s+youtube)?\s*$",
            # "download from YouTube Close Enough"
            r"download\s+(?:from\s+)?youtube\s+(?:for\s+)?(.+)",
            # "download YouTube Close Enough"
            r"download\s+youtube\s+(?:a\s+|an\s+|the\s+)?(.+)",
            # "download Close Enough from YouTube"
            r"download\s+(?:a\s+|an\s+|the\s+)?(.+?)\s+(?:on|from)\s+youtube\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                query = _clean_query(match.group(1))
                # "search youtube for X and download it" leaves a
                # leading "youtube for" in the captured name.
                query = re.sub(r"^youtube\s+(?:for\s+)?", "", query)
                query = re.sub(
                    r"^(?:tv\s+shows?|shows?|movies?|films?|videos?|songs?|music)\s+",
                    "", query)
                if query and query not in ("status", "it", "that", "this",
                                           "youtube"):
                    return ("download_youtube", query)
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

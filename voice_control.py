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
    # which cut off slow speech and long show names. Raised again
    # 2026-11-23 evening, when she said the voice feature was broken
    # and asked for more time to speak and for it to hear her:
    # 20 seconds for a one-time command, 15 seconds after "Samantha".
    ONE_TIME_LISTEN_SECONDS = 20
    WAKE_WORD_COMMAND_SECONDS = 15
    # After the first words are heard, keep listening this long for
    # more words, so a pause between words does not cut her off.
    PAUSE_GRACE_SECONDS = 2.5

    def __init__(self, model_path="vosk-model-small-en-us-0.15"):
        """Initialize voice recognition"""
        self.model_path = Path(model_path)
        self.model = None
        self.recognizer = None
        self.is_listening = False
        self.wake_word_active = False
        self.audio_queue = queue.Queue()
        self.wake_word = "samantha"
        # Ashley, 2026-11-26: Samantha answers to more than one
        # name — Samantha, Sam, Sammy, Guide, and Metro. Longest
        # first, so "samantha" wins over "sam" inside it, and
        # "sammy" wins over "sam". wake_word stays "samantha"
        # for anything that only knows the one name.
        self.wake_words = ("samantha", "sammy", "sam",
                           "guide", "metro")

    def _find_wake_word(self, text):
        """Which wake word is in this text, or None.

        Word boundaries only, so "sam" does not fire inside
        "samantha" or inside another word, and "guide" does
        not fire inside "guided".
        """
        m = re.search(r"\b(samantha|sammy|sam|guide|metro)\b", text)
        return m.group(1) if m else None

    def _strip_wake_word(self, text):
        """Strip a leading wake word ("Samantha, ..." / "Hey Sam, ...")."""
        return re.sub(
            r"^(?:hey\s+)?(?:samantha|sammy|sam|guide|metro)[,\s]+",
            "", text.strip())

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
                # Honey, 2026-11-23: "make it so that it can hear me".
                # Do not return on the very first words. Keep
                # collecting words, and only stop after a short
                # pause with no new words, or when time runs out.
                # queue.get() has a timeout now, so a silent mic
                # cannot block here forever past the duration.
                heard = ""
                last_heard_time = None

                while time.time() - start_time < duration and self.is_listening:
                    try:
                        data = self.audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        if heard and last_heard_time is not None and (
                                time.time() - last_heard_time
                                > self.PAUSE_GRACE_SECONDS):
                            break
                        continue

                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip()
                        if text:
                            heard = (heard + " " + text).strip() if heard else text
                            last_heard_time = time.time()
                    if heard and last_heard_time is not None and (
                            time.time() - last_heard_time
                            > self.PAUSE_GRACE_SECONDS):
                        break

                # Get final result, and add any trailing words to
                # what was already heard.
                result = json.loads(self.recognizer.FinalResult())
                text = result.get('text', '').strip()
                if text and text not in heard:
                    heard = (heard + " " + text).strip() if heard else text
                return heard if heard else None

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
                    try:
                        data = self.audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    if self.recognizer.AcceptWaveform(data):
                        result = json.loads(self.recognizer.Result())
                        text = result.get('text', '').strip().lower()

                        if text:
                            # Check for wake word — any of Samantha,
                            # Sam, Sammy, Guide, Metro (Ashley, 2026-11-26).
                            heard = self._find_wake_word(text)
                            if heard:
                                # Wake word detected, notify callback
                                callback('wake_word_detected')

                                # "Samantha, play" often arrives as one
                                # utterance, so keep anything said after
                                # the wake word in that same breath as the
                                # command instead of throwing it away and
                                # waiting for a second utterance.
                                remainder = re.split(
                                    r"\b" + re.escape(heard) + r"\b",
                                    text, maxsplit=1)[1]
                                remainder = remainder.strip(" ,").strip()
                                if remainder:
                                    callback('command', remainder)
                                    self.recognizer.Reset()
                                    continue

                                # Listen for command after wake word.
                                # Honey asked for more time here too:
                                # 15 seconds instead of 8, and keep
                                # collecting words through a pause,
                                # so slow speech is heard in full.
                                self.recognizer.Reset()
                                import time
                                start_time = time.time()
                                command_text = ""
                                last_heard_time = None

                                while time.time() - start_time < self.WAKE_WORD_COMMAND_SECONDS and self.wake_word_active:
                                    try:
                                        data = self.audio_queue.get(timeout=0.5)
                                    except queue.Empty:
                                        if command_text and last_heard_time is not None and (
                                                time.time() - last_heard_time
                                                > self.PAUSE_GRACE_SECONDS):
                                            break
                                        continue

                                    if self.recognizer.AcceptWaveform(data):
                                        result = json.loads(self.recognizer.Result())
                                        text = result.get('text', '').strip()
                                        if text:
                                            command_text = (
                                                (command_text + " " + text).strip()
                                                if command_text else text)
                                            last_heard_time = time.time()
                                    if command_text and last_heard_time is not None and (
                                            time.time() - last_heard_time
                                            > self.PAUSE_GRACE_SECONDS):
                                        break

                                # Get final result if nothing yet
                                if not command_text:
                                    result = json.loads(self.recognizer.FinalResult())
                                    command_text = result.get('text', '').strip()
                                else:
                                    result = json.loads(self.recognizer.FinalResult())
                                    tail = result.get('text', '').strip()
                                    if tail and tail not in command_text:
                                        command_text = (command_text + " " + tail).strip()

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

        # Honey, 2026-11-23 evening: she does not have to say
        # Samantha's name all the time. In one-time mode
        # (Ctrl+Shift+B, the push button) she just says the
        # command, for example "search for Young Sheldon".
        # Strip a leading wake word — Samantha, Sam, Sammy,
        # Guide, or Metro (Ashley, 2026-11-26) — here, so
        # it is optional and never becomes part of the show name.
        # The wake-word path already strips it; this covers the
        # push-button path too.
        text = self._strip_wake_word(text)

        # --- Name: Honey asked 2026-11-23 that Samantha learn her
        # name when she tells it to her, and remember it. Checked
        # before search/download/play, so "my name is Honey" is not
        # swallowed by another command.
        name_command = self._parse_name_command(text)
        if name_command is not None:
            return name_command

        # --- "I'm good": Ashley, 2026-11-26. Samantha asks
        # "How are you doing?" in the greeting, and Ashley
        # answers "I am good". Checked before search/play, so
        # "good" is not swallowed by another command, and
        # before the TV guide, so "I'm doing good" is not
        # treated as a guide request. main.py answers in
        # Samantha's own voice, then reads her channels and
        # what comes up next, without her having to ask.
        if re.search(
                r"\b(?:i am|i'm|im|i feel|i'm doing|i am doing"
                r"|i'm feeling|i am feeling|doing|feeling)\s+"
                r"(?:good|great|fine|okay|ok|well|wonderful"
                r"|fantastic|awesome|happy|better|alright"
                r"|pretty good|really good)\b", text):
            return 'feeling_good'
        if text in ("good", "i'm good", "i am good", "all good",
                    "doing good", "feeling good", "i feel good",
                    "i'm doing good", "i am doing good"):
            return 'feeling_good'

        # --- "Can you hear me?": Ashley, 2026-11-26. When she
        # asks if Samantha can hear her, Samantha answers
        # "Yes, I can hear you" in her own voice. Checked
        # before search/play, so it is not treated as a
        # search for a show called that.
        if re.search(
                r"\bcan you hear me\b|\bdo you hear me\b"
                r"|\bdid you hear me\b|\bcan you hear\b"
                r"|\bare you listening\b|\bcan you hear us\b",
                text):
            return 'can_you_hear_me'

        # --- List shows: Ashley, 2026-11-26. "What are my
        # options?" / "tell me the list of shows I have so I
        # can choose a channel". Checked before live-TV search
        # and before the TV guide, so "what shows do I have"
        # is not treated as a guide or a show search.
        if re.search(
                r"\bwhat are my (?:options|choices)\b"
                r"|\bwhat can i (?:watch|choose)\b"
                r"|\bwhat shows? (?:do i have|have i got|are there)"
                r"|\blist (?:all )?(?:the )?shows?\b"
                r"|\btell me (?:the )?(?:list of )?(?:shows?|options)\b"
                r"|\bshow me (?:the )?(?:shows?|options)\b"
                r"|\bwhat are my shows?\b", text):
            return 'list_shows'
        if re.search(
                r"\b(?:list|show|tell me|read|name)\b.*\bchannels?\b",
                text) and ("list" in text or "what" in text
                           or "show" in text or "tell" in text
                           or "read" in text or "name" in text):
            return 'list_channels'
        if re.search(r"\bwhat channels? (?:do i|have i|are there)"
                     r"|\bwhat are my channels?\b", text):
            return 'list_channels'

        # --- Game Show Network guide: Honey asked 2026-11-23
        # for another guide for the Game Show Network, so she
        # knows what is coming up next there. Checked before the
        # general TV guide, so "on Game Show Network" is not
        # swallowed by it.
        if "game show network" in text and ("next" in text or "guide" in text or "coming up" in text or "what" in text):
            m = re.search(r"(?:on|for)\s+(?:the\s+)?game show network", text)
            return ('livetv_guide', 'game show network')
        if re.search(r"\bwhat(?:'s| is) (?:on|coming up)(?: next)? on\b", text):
            m = re.search(r"\bon\s+(.+)$", text)
            if m:
                return ('livetv_guide', m.group(1).strip())

        # --- TV guide: Honey asked 2026-11-23 for the whole
        # TV guide of what is coming up next, read by Samantha.
        # Checked before search, so "what's next" is not
        # swallowed by a show search.
        if re.search(
                r"\b(?:what(?:'s| is)|tell me|give me|samantha,?\s+)?"
                r"(?:what(?:'s| is)\s+)?(?:coming up|on|next|up next)\b",
                text) and ("next" in text or "guide" in text or "coming up" in text):
            return 'whats_next'
        if "tv guide" in text or "television guide" in text:
            return 'whats_next'

        # --- Fix mixed-up shows: Honey asked 2026-11-23 that
        # shows she already has are still mixed up with other
        # shows. Checked before search/download, so "fix the
        # mixed up shows" is not swallowed by a show search.
        if re.search(
                r"\b(?:fix|unmix|un-mix|sort out|straighten out)\b.*"
                r"\b(?:mixed|mix|mixed up|mix up|mixed-up)\b",
                text):
            return 'fix_mixed_channels'
        if re.search(r"\bshows? (?:are|is) mixed up\b", text):
            return 'fix_mixed_channels'
        if re.search(r"\bunmix\b", text):
            return 'fix_mixed_channels'

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

        # --- Play a named channel/show: Ashley, 2026-11-26.
        # After Samantha reads the list of shows, Ashley picks
        # one by name: "play Friends", "watch Classic Doctor
        # Who", "play the Frasier channel". Checked before the
        # generic play/pause below, so "play Friends" switches
        # to that channel instead of just toggling play/pause.
        # Live TV is already handled above.
        m = re.search(
            r"^(?:play|watch|switch to|go to)\s+(?:the\s+)?"
            r"(.+?)(?:\s+channel)?\s*$", text)
        if m:
            name = m.group(1).strip()
            if name and name not in (
                    "it", "that", "this", "live tv",
                    "live television", "tv", "television",
                    "music", "something", "the"):
                return ('play_channel', name)

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
        # a wake word ("Samantha, ..." / "Sam, ..."); in
        # wake-word mode it is already stripped.
        text = self._strip_wake_word(text)

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
            if name and name.lower() not in (
                    "samantha", "sam", "sammy", "guide", "metro",
                    "you", "me"):
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
        # Honey, 2026-11-23: voice search should do live shows too,
        # as well as AudioVault search and download. So "search live
        # for Game Show Network", "search for Game Show Network
        # live", "search for live shows" and "search for Game Show
        # Network" all go to the live-channel search, not to an
        # AudioVault show search for a show called that.
        if re.search(r"\b(?:search|find|look for|look up)\b", text):
            if "live" in text or "game show network" in text:
                m = re.search(
                    r"(?:search|find|look for|look up)\s+(?:for\s+)?(.+)", text)
                q = ""
                if m:
                    q = _clean_query(m.group(1))
                    # Strip leading filler words, in any order:
                    # "live for", "for live", "live channels for",
                    # "live tv shows for", and so on.
                    while True:
                        q2 = re.sub(
                            r"^(?:live|for|tv|television|shows?|channels?|channel)\s+",
                            "", q)
                        if q2 == q:
                            break
                        q = q2
                    q = re.sub(
                        r"\s+(?:live|channel|channels|tv|television|shows?|show)\s*$",
                        "", q)
                    q = q.strip()
                    # "search for live shows" / "find live tv" name
                    # no channel at all, so search all live channels.
                    if q in ("live", "tv", "television", "shows", "show",
                             "channels", "channel", "for"):
                        q = ""
                if q:
                    return ('search_live_channels', q)
                return 'search_live_channels'
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

        Honey, 2026-11-23: "whenever I tell it to delete the
        show, it deletes it." So this must catch every way she
        says it, not only "delete ... downloads":
        "delete Friends", "delete the show", "delete this show",
        "delete A Killer Among Friends", "get rid of this show".
        "delete the show" / "delete this show" / "delete it"
        means the channel playing right now, so main.py deletes
        the current channel. Vosk may hear "amongst" for "among",
        so normalise it here; main.py matches "killer among
        friends" either way.
        """
        if not re.search(r"\b(?:delete|remove|get rid of)\b", text):
            return None
        text = text.replace('amongst', 'among')
        # "delete the show" / "delete this show" / "delete this
        # channel" / "delete it" - the current show.
        if re.search(
                r"(?:delete|remove|get rid of)\s+(?:the\s+|this\s+)?"
                r"(?:show|channel|episode|movie|it|that|them)\s*$", text):
            return 'delete_channel_downloads'
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
        # "delete Friends" / "delete A Killer Among Friends" /
        # "delete the show Friends" - a named show, no "downloads"
        # word needed.
        m = re.search(
            r"(?:delete|remove|get rid of)\s+(?:the\s+)?"
            r"(?:show\s+|channel\s+)?(.+)", text)
        if m:
            q = _clean_query(m.group(1))
            q = re.sub(r"\s+(?:show|channel|downloads?)\s*$", "", q)
            if q and q not in ('them', 'it', 'those', 'these', 'show',
                               'channel', 'episode', 'movie'):
                return ('delete_channel_downloads', q)
            return 'delete_channel_downloads'
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
            # "get Young Sheldon Who Wants to Be a Millionaire on
            # YouTube" - Honey, 2026-11-23: "get" means find it
            # for her on YouTube, so this is a YouTube search,
            # not a download. She picks from the results, or
            # says "download it" after.
            r"(?:get|fetch|bring(?:\s+me)?|show\s+me)\s+(?:me\s+)?"
            r"(?:a\s+|an\s+|the\s+)?(.+?)\s+(?:on|from)\s+youtube\b",
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

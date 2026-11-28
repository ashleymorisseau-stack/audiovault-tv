import time
import sys
import os
# Ashley, 2026-11-27: the reading voice ships WITH the app, in
# the vendor/ folder next to main.py, so edge-tts is ready the
# moment the app opens — no pip install, no internet needed
# just to have the library, no Command Prompt. vendor/ holds
# edge-tts 7.3.1 and the pure-Python parts of its dependencies
# (aiohttp, yarl, multidict, frozenlist, propcache, aiosignal,
# aiohappyeyeballs, attrs, certifi, tabulate, typing_extensions,
# edge_playback). The compiled .pyd extensions are deliberately
# left out: every one of those packages falls back to its
# pure-Python version when they are missing, so the library
# still imports and speaks. pip is only a fallback now, for a
# library that is not vendored. This runs before anything else
# imports, so `import edge_tts` anywhere in this file finds the
# vendored copy first.
_VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "vendor")
if os.path.isdir(_VENDOR_DIR) and _VENDOR_DIR not in sys.path:
    sys.path.insert(0, _VENDOR_DIR)
# Ashley, 2026-11-26: NO print() at startup. NVDA reads the
# terminal out loud, so every "Loading ..." line was spoken
# by NVDA while Audio Vault TV opened, and she does not want
# that. Loading is silent now — Samantha says "Audio Vault TV"
# in her own voice when the app is ready, in
# _show_greeting_dialog, then greets her and names the channels
# she has, and that is the only loading signal she hears.
import wx
import json
import threading
import subprocess
import tempfile
import shutil
import zipfile
from pathlib import Path

try:
    from audio_player import AudioPlayer
    AUDIO_PLAYER_AVAILABLE = True
except ImportError:
    # soundfile / sounddevice (which audio_player needs) are
    # not installed yet: the app still opens, and the
    # requirements install below gets them and then loads
    # AudioPlayer (see _reload_missing_modules), instead of
    # the whole app refusing to start over one missing library.
    AudioPlayer = None
    AUDIO_PLAYER_AVAILABLE = False
from playlist_manager import PlaylistManager
from channel_manager import ChannelManager
try:
    from voice_control import VoiceControl
    VOICE_CONTROL_AVAILABLE = True
except ImportError:
    # vosk / sounddevice (which voice_control needs) are not
    # installed yet: voice control stays off until the
    # requirements install gets them (see
    # _reload_missing_modules), instead of the whole app
    # refusing to start. Typing still works: _run_typed_command
    # builds a bare parser when there is no voice control.
    VoiceControl = None
    VOICE_CONTROL_AVAILABLE = False
from player_logger import PlayerLogger
try:
    import audiovault_client as av
    AV_AVAILABLE = True
except ImportError:
    # requests / beautifulsoup4 (which audiovault_client
    # needs) are not installed yet: AudioVault search and
    # download stay off until the requirements install gets
    # them (see _reload_missing_modules), instead of the
    # whole app refusing to start.
    av = None
    AV_AVAILABLE = False
try:
    import youtube_client as yt
    YT_AVAILABLE = True
except ImportError:
    yt = None
    YT_AVAILABLE = False

try:
    import livetv_client as livetv
    LIVETV_AVAILABLE = True
except ImportError:
    livetv = None
    LIVETV_AVAILABLE = False

# NVDA integration
nvda = None
NVDA_AVAILABLE = False
try:
    import ctypes
    nvda = ctypes.windll.LoadLibrary("./nvdaControllerClient.dll")
    res = nvda.nvdaController_testIfRunning()
    if res == 0:
        NVDA_AVAILABLE = True
except Exception:
    pass

def speak(text):
    """Speak text through NVDA if available"""
    # Ashley, 2026-11-26: while NVDA quiet mode is on, nothing is
    # spoken through NVDA at all — not even the app's own messages.
    # Samantha's recorded voice and the shows still play, because
    # they go through the audio engine, not NVDA.
    if _NVDA_QUIET:
        return
    if NVDA_AVAILABLE and nvda:
        try:
            nvda.nvdaController_speakText(text)
        except Exception:
            pass


# NVDA quiet mode — Ashley, 2026-11-26:
# "I just want it to stop talking while I'm in the app. But if I
# close the app I want it to talk."
# NVDA's sleep mode (NVDA+Shift+S) stops all NVDA speech and braille
# for the current app only, and NVDA talks again as soon as she is in
# another app. The controller DLL has no sleep function, so the app
# presses that key itself (NVDA key is Insert on her PC) while its own
# window is focused. NVDA only keeps sleep mode until NVDA restarts.
# A marker file in the temp folder remembers when quiet was left on
# (for example the app crashed before it could turn it back off), so
# the next start does not press the key a second time and turn it
# back off by mistake — unless the marker is from before this Windows
# boot, in which case NVDA has restarted and the marker is stale.
# The key is only ever pressed while this window is actually focused:
# an earlier version pressed it once at 500 ms no matter what had
# focus, so the keypress could land in another window and NVDA kept
# saying "pane" in this app with nothing ever trying again. Now the
# app brings its window forward, waits for focus, and retries every
# 2 seconds up to 5 times, and tries again whenever the window is
# activated. Manual version, any time: press NVDA+Shift+S while
# AudioVault TV is focused; Ctrl+Shift+Q in the app flips it too.
# Honest limit: this is a blind keypress toggle — NVDA gives the app no
# way to ask whether sleep is already on. The keypress must use the
# NVDA key this PC actually uses, so _nvda_modifier_vk() reads it
# from NVDA's own settings file (see below). If NVDA's settings
# cannot be read, Insert is assumed. If the keypress still does
# nothing, she should press NVDA+Shift+S herself once instead.
_NVDA_QUIET = False
_NVDA_QUIET_MARKER = Path(tempfile.gettempdir()) / "audiovault_tv_nvda_quiet"


def _nvda_modifier_vk():
    """Virtual-key code of the NVDA modifier key on this PC.

    Ashley, 2026-11-26: "the pain toggle does not work" — the
    app pressed Insert+Shift+S, but that only works when the
    NVDA key IS Insert (desktop keyboard layout). With the
    laptop layout the NVDA key is CapsLock, so the Insert
    keypress did nothing at all and NVDA kept talking in the
    app. NVDA stores its layout in %APPDATA%\\nvda\\nvda.ini
    ([keyboard] keyboardLayout, and the useCapsLock / numpad
    modifier flags), so read it and press the right key.
    Returns 0x14 (CapsLock) for laptop layout, 0x60 (Numpad 0)
    for numpad Insert, 0x2D (Insert) otherwise.
    """
    try:
        import configparser
        ini = Path(os.environ.get("APPDATA", "")) / "nvda" / "nvda.ini"
        cfg = configparser.ConfigParser()
        cfg.read(ini)
        layout = cfg.get("keyboard", "keyboardLayout",
                         fallback="desktop").strip().lower()
        if layout == "laptop":
            return 0x14
        if cfg.getboolean("keyboard", "useCapsLockAsNVDAModifierKey",
                          fallback=False):
            return 0x14
        if cfg.getboolean("keyboard", "useNumpadInsertAsNVDAModifierKey",
                          fallback=False):
            return 0x60
        return 0x2D
    except Exception:
        return 0x2D


def _press_nvda_sleep_toggle():
    """Press NVDA+Shift+S with the NVDA key this PC uses."""
    if os.name != "nt":
        return False
    try:
        # Ashley, 2026-11-27: NVDA kept saying "pane" all the
        # time. Clear anything NVDA is already saying first, so
        # a queued "pane" does not keep repeating after sleep
        # is supposed to be on.
        if NVDA_AVAILABLE and nvda:
            try:
                nvda.nvdaController_cancelSpeech()
            except Exception:
                pass
        user32 = ctypes.windll.user32
        VK_SHIFT = 0x10
        VK_NVDA = _nvda_modifier_vk()
        KEYEVENTF_KEYUP = 0x0002
        for vk in (VK_SHIFT, VK_NVDA, 0x53):  # Shift, NVDA key, S
            user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.05)
        for vk in (0x53, VK_NVDA, VK_SHIFT):
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


def _nvda_quiet_marker_stale():
    """True if the quiet marker is from before this Windows boot.

    The marker says a previous run left NVDA quiet on, but NVDA
    sleep does not survive an NVDA or PC restart. If the marker
    was written before the current boot, NVDA has restarted since
    and is awake again, so the marker must not be trusted.
    Boot time is now minus the system uptime (GetTickCount64).
    If anything about the check fails, the marker is trusted,
    which is the old behaviour.
    """
    try:
        if not _NVDA_QUIET_MARKER.exists():
            return False
        uptime_ms = ctypes.windll.kernel32.GetTickCount64()
        boot_time = time.time() - (uptime_ms / 1000.0)
        marker_time = _NVDA_QUIET_MARKER.stat().st_mtime
        return marker_time < boot_time - 60
    except Exception:
        return False


def set_nvda_quiet(on):
    """Turn NVDA quiet (sleep) mode for this app on or off."""
    global _NVDA_QUIET
    if on == _NVDA_QUIET:
        return _NVDA_QUIET
    if not NVDA_AVAILABLE:
        return False
    if not _press_nvda_sleep_toggle():
        return False
    _NVDA_QUIET = on
    try:
        if on:
            _NVDA_QUIET_MARKER.write_text("on")
        else:
            _NVDA_QUIET_MARKER.unlink(missing_ok=True)
    except Exception:
        pass
    return _NVDA_QUIET


class _YTDownloadCancelled(Exception):
    """Raised inside the download progress callback to abort a YouTube download."""
    pass


class _BackgroundDownloadCancelled(Exception):
    """Raised inside a download progress callback to stop a background
    download when Honey asks to cancel downloads (no pop-up window)."""
    pass


# Work commands — Ashley, 2026-11-26: "have her say I'm on it."
# When she asks Samantha to do work — search, download, play a
# channel, list shows, read the guide — Samantha answers "I'm on
# it" in her own recorded voice right away, so Ashley knows she
# was heard and is working on it. Quick replies (how she is
# doing, "can you hear me", her name, play/pause, skipping)
# answer directly instead and do not get an extra "I'm on it".
_WORK_COMMANDS = (
    'search_shows', 'search_movies', 'search_youtube',
    'download', 'download_shows', 'download_movies',
    'download_youtube', 'download_first',
    'download_status', 'cancel_downloads',
    'play_channel', 'play_live_tv', 'play_live_channel',
    'search_live_channels', 'stop_live_tv',
    'list_shows', 'list_channels', 'whats_next',
    'livetv_guide', 'fix_mixed_channels',
    'delete_channel_downloads',
)

# Libraries Audio Vault TV needs, that the app gets and
# installs itself on startup — Ashley, 2026-11-27: "I want
# it to get Edge and then install it", and then: whatever
# requirements she needs for Command Prompt, the app should
# just get them and install them itself, so she never has to
# do it in Command Prompt. Each entry is (module name to
# check for, pip package name, plain spoken name, required).
# "required" ones must all be ready before Samantha says
# everything is ready. cloudscraper is optional: the show
# client already falls back to plain requests without it, so
# a failed cloudscraper install never blocks the rest.
# wxPython is deliberately NOT here: the app cannot open at
# all without it, so there is no app yet to install it from —
# it has to come with the installer. Everything else is
# checked on startup and installed in the background, one at
# a time (see _ensure_requirements).
_REQUIRED_LIBRARIES = (
    ("edge_tts", "edge-tts", "the reading voice", True),
    ("vosk", "vosk", "voice listening", True),
    ("sounddevice", "sounddevice", "the microphone", True),
    ("soundfile", "soundfile", "sound playing", True),
    ("requests", "requests", "getting shows", True),
    ("bs4", "beautifulsoup4", "reading show pages", True),
    ("yt_dlp", "yt-dlp", "YouTube downloads", True),
    ("cloudscraper", "cloudscraper", "getting shows", False),
)

# The Vosk listening model — Ashley, 2026-11-27: Samantha says
# her reading voice is ready, but "she doesn't understand
# anything". Listening (Vosk) and speaking (Edge TTS) are
# separate: the reading voice being ready says nothing about
# listening. Listening needs this model folder beside main.py,
# and _ensure_requirements only ever pip-installed libraries —
# it never downloaded the model itself. So the app now
# downloads it itself, in the background, like the other
# installs: no Command Prompt, no manual download. The zip is
# about 40 MB from alphacephei.com (the Vosk model list).
_VOSK_MODEL_NAME = "vosk-model-small-en-us-0.15"
_VOSK_MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
# The download (zip) plus the extracted model need room: fail
# plainly instead of filling the disk.
_VOSK_MODEL_MIN_FREE_BYTES = 200_000_000


# Ashley, 2026-11-28: the Fish Audio voices her Samantha can use,
# by the names they appear in her NVDA fishy settings (custom
# voices) or in Fish Audio's free built-in list. The reference
# ids are 32-hex; a raw id pasted into config.ini works too.
_FISH_VOICES = {
    "Ariana Grande": "0c793bf68b534d168357c09a50e9b423",
    "Dolly Pardon": "234e60f891c1414dabf5737c98190e1c",
    "Josh": "f13958f6a0424bc7b3ea18a209bd0910",
    "Sarah": "933563129e564b19a115bedd57b7406a",
    "Selene": "b347db033a6549378b48d00acb0d06cd",
    "Taylor": "cfc33da8775c47afacccf4eebabe44dc",
}

# The Voice menu's Edge option. Saving it in samantha_fish_voice
# makes _fish_settings() find no Fish voice (it is neither a Fish
# name nor a 32-hex id), so readings fall to the Edge reading
# voice (samantha_reading_voice in config.ini, the voice the
# audition picked).
_EDGE_VOICE_OPTION = "Aria (Edge reading voice)"

class PlayerFrame(wx.Frame):
    def __init__(self):
        import time
        t0 = time.time()
        super().__init__(None, title="AudioVault TV", size=(600, 400))
        
        # Initialize logger
        self.logger = PlayerLogger(Path.home() / "mp3_player_log.txt")
        
        # AudioPlayer is None when the audio libraries are not
        # installed yet (see the guarded import at the top):
        # playback stays off until the requirements install
        # gets them, instead of the app refusing to start.
        try:
            self.player = AudioPlayer() if AudioPlayer is not None else None
        except Exception:
            self.player = None
        self.playlist = PlaylistManager()
        self.channels = ChannelManager(Path.home() / ".mp3_player_channels.json", logger=self.logger)

        t1 = time.time()
        self.logger.log_playback("STARTUP", f"Basic init: {t1-t0:.2f}s")

        # Initialize voice control
        try:
            if VoiceControl is None:
                raise ImportError("voice_control is not available")
            self.voice = VoiceControl()
            self.voice_available = True
        except Exception as e:
            print(f"Voice control not available: {e}")
            self.voice = None
            self.voice_available = False
        
        t2 = time.time()
        self.logger.log_playback("STARTUP", f"Voice init: {t2-t1:.2f}s")
        
        self.is_voice_listening = False
        self.wake_word_mode = False
        # Ashley, 2026-11-26: "make it so that it listens to me
        # and responds every time I ask it something." Once
        # Samantha hears a command, she keeps listening for the
        # next one instead of stopping — continuous conversation.
        # True while one-time listening should re-arm itself
        # after each heard command. Set False when she stops
        # listening herself (Ctrl+Shift+B) or starts wake-word
        # mode, which has its own loop.
        self._want_continuous = False
        # True while Samantha is reading something out loud
        # (show list, guide) in her reading voice, so the
        # automatic re-arm waits instead of listening to her
        # own reading as if it were a command.
        self._samantha_reading = False
        # Cached result of _samantha_voice_mode(): "edge" or
        # None. None until first checked.
        self._samantha_voice_mode_cache = "unset"
        # Reading-voice install state — ALL of it is defined
        # BEFORE the install thread below is started. Ashley,
        # 2026-11-26: the thread used to start first and these
        # attributes were set after it, so if the thread ran
        # first it saw _edge_install_lock as None and returned
        # silently — no install ever happened, and Samantha
        # just kept saying "not ready". Nothing below may be
        # moved after the thread start.
        self._edge_install_state = "unknown"
        self._edge_install_running = False
        self._edge_install_lock = threading.Lock()
        self._edge_install_last_try = 0.0
        self._edge_install_fail_count = 0
        self._edge_install_not_ready_said = 0
        self._edge_install_explicit = False
        # Ashley, 2026-11-27: the plain reason the last try
        # failed, so she can ask "why is my reading voice not
        # ready" and be told it instead of us guessing. None
        # when no try has failed yet. _edge_install_source is
        # where the working library came from: "vendor" when
        # it imports from the vendor/ folder shipped with the
        # app, "pip" when it had to be installed, None while
        # it is not ready yet.
        self._edge_install_last_reason = None
        self._edge_install_source = None
        self._pending_reading_text = None
        self._edge_install_retry_timer = None
        self._edge_install_started_announced = False
        # Requirements install state — ALL of it is defined
        # BEFORE the install thread below is started, for the
        # same reason as the edge state above: the thread must
        # never run before the flags it needs exist. One
        # library at a time, in the background (see
        # _ensure_requirements): "ready" / "missing" /
        # "installing" / "failed" per library, how many times
        # each one has failed, and the plain reason for the
        # latest failure, so Samantha can say it once instead
        # of going silent or repeating "not ready" forever.
        self._requirements_state = {}
        self._requirements_running = False
        self._requirements_lock = threading.Lock()
        self._requirements_last_try = 0.0
        self._requirements_fail_count = {}
        self._requirements_last_reason = {}
        self._requirements_announced_started = False
        self._requirements_ready_announced = False
        # (library, fail count) pairs Samantha has already
        # announced a failure for, so the same failure is
        # never said twice.
        self._requirements_failed_said = set()
        # A failed Edge TTS synthesis (the library is there
        # but the internet failed) says "not ready" once, not
        # on every ask, until a reading works again.
        self._edge_tts_read_failed_said = False
        # Listening-model install state — ALL of it is defined
        # BEFORE the startup install thread below is started,
        # for the same reason as the edge state above: the
        # thread chain (edge -> requirements -> model) must
        # never run before the flags it needs exist.
        # "unknown" / "checking" / "installing" / "ready" /
        # "failed", like the reading-voice install.
        self._vosk_model_state = "unknown"
        self._vosk_model_running = False
        self._vosk_model_lock = threading.Lock()
        self._vosk_model_last_try = 0.0
        self._vosk_model_fail_count = 0
        self._vosk_model_not_ready_said = 0
        self._vosk_model_last_reason = None
        self._vosk_model_explicit = False
        self._vosk_model_retry_timer = None
        self._vosk_model_started_announced = False
        # True once "I cannot hear you yet" has been said for
        # the current install attempt, so the greeting does
        # not repeat it on every retry (see
        # _say_listening_not_ready). An explicit press of
        # Ctrl+Shift+B / Ctrl+Shift+W always answers anyway.
        self._listening_not_ready_announced = False
        # Plain reason the microphone stream last failed with,
        # if it did (see voice_control.listen / _voice_error).
        self._voice_last_error = None
        # Get Samantha's reading voice ready in the background
        # (installs edge-tts itself if it is missing, and
        # retries on its own if a try fails — Ashley never
        # has to use Command Prompt for it). When the reading
        # voice is dealt with, the same thread goes on to get
        # every other library the app needs (see
        # _ensure_requirements) — still in the background,
        # still one at a time, still no Command Prompt.
        threading.Thread(target=self._ensure_edge_tts,
                         daemon=True).start()
        # Ashley, 2026-11-26: the wake chimes were playing twice.
        # This flag says the high+low chimes already played for
        # this listening session, so they are not played again
        # and the low chime is not repeated at the end.
        self._wake_chimes_played = False
        # Samantha's voice, one clip at a time (Ashley,
        # 2026-11-26): a dedicated clip player, a queue for
        # sequences, and the install state for her reading voice
        # — see audio_player.ClipPlayer and _ensure_edge_tts.
        self._samantha_queue = []
        self._samantha_pump_timer = None
        self._pending_voice_command_timer = None
        self._last_typed_command = None
        self._last_typed_command_at = 0.0
        # (Reading-voice install state lives above, before the
        # startup install thread — see the note there.)
        # Ashley, 2026-11-26: after the startup greeting asks
        # "How are you doing?", Samantha listens first and reads
        # the channel list after her answer (or after silence).
        # True while the startup list has not been read yet.
        self._startup_list_pending = False
        # "Excuse me" is said only once in a row in wake-word
        # mode, so it does not keep repeating while she is not
        # speaking. Cleared whenever a real command is heard.
        self._excuse_me_said = False
        # NVDA quiet: True means she wants NVDA quiet while in
        # the app (the default). Ctrl+Shift+Q flips it. The
        # automatic enable only runs while this is True, so it
        # never overrules her turning it back on herself.
        self._nvda_quiet_wanted = True
        self.wake_word_thread = None
        self.is_switching_channels = False  # Flag to prevent multiple channel switches
        self.vault_logged_in = False
        self.livetv_process = None  # Live TV stream subprocess
        self._livetv_last_channel = None  # last live channel, for Space resume
        self._livetv_fallback_in_progress = False  # Live TV fallback is loading in the background

        # Background downloads: downloads run in a worker thread with no
        # pop-up window, so playback, Live TV and the menus keep working
        # while a download runs. Progress is kept here so Honey can ask
        # for a spoken download status at any time.
        self.download_progress = None  # no download dialog is shown any more
        self._bg_vault_percent = 0
        self._bg_yt_percent = 0
        self._bg_cancel_requested = False
        
        self._create_ui()
        self._bind_hotkeys()
        
        t3 = time.time()
        self.logger.log_playback("STARTUP", f"UI created: {t3-t2:.2f}s")
        
        self._load_current_channel()
        
        t4 = time.time()
        self.logger.log_playback("STARTUP", f"Channel loaded: {t4-t3:.2f}s")
        
        # Check for data corruption after startup
        wx.CallAfter(self._check_channel_integrity)
        
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer)
        self.timer.Start(100)  # Check every 100ms
        
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self._update_title()
        
        # Play startup sound
        self._play_startup_sound()
        
        self.logger.log_playback("STARTUP", f"Total startup: {time.time()-t0:.2f}s")
        
        # Defer slow operations until after window shows
        wx.CallAfter(self._vault_auto_login)
        
        # Show greeting dialog after a short delay. Ashley,
        # 2026-11-27: 2.5 seconds, not 1 — the reading-voice
        # install thread starts at the top of __init__, but the
        # greeting clip is only about 5 seconds and she answers
        # it right away, so the voice was still "not ready" on
        # her very first ask. The extra time lets the vendored
        # library (which imports in well under a second) be
        # confirmed ready before she is asked anything, and
        # listening still only starts after the greeting
        # finishes, so her answer is never lost.
        wx.CallLater(2500, self._show_greeting_dialog)

        # Ashley, 2026-11-26: quiet NVDA shortly after the window
        # opens, so it stops talking while she is in the app. Samantha
        # still greets her in her own voice at 2500 ms — that plays
        # through the audio engine, not NVDA, so quiet mode does not silence it.
        # If the window is not focused yet when this runs, the enable
        # keeps trying every 2 seconds, and coming back to the window
        # tries again too — the key is only ever pressed while this
        # window is focused, so it cannot toggle sleep for another app.
        wx.CallLater(500, self._enable_nvda_quiet)
        self.Bind(wx.EVT_ACTIVATE, self._on_activate_nvda_quiet)
        # Ashley, 2026-11-27: focus starts on the panel, so NVDA
        # says "pane". Put it in the "Type to Samantha" box
        # instead, once quiet mode has had a moment to engage.
        wx.CallLater(1200, self._focus_command_box_if_on_panel)
        # Ashley, 2026-11-28: "make it so NVDA does not say pain
        # [pane] every time the program loads". The focus move
        # above happens too late: NVDA is still awake when the
        # window first takes focus (quiet mode's keypress lands
        # at about 800 ms), so it announces the panel, "pane",
        # before quiet mode can engage. Keep the first second
        # quiet instead — see _quiet_nvda_startup.
        wx.CallLater(50, self._quiet_nvda_startup)
    
    def _create_ui(self):
        """Create accessible UI with menu bar"""
        # Create menu bar
        menubar = wx.MenuBar()
        
        # File menu
        file_menu = wx.Menu()
        select_item = file_menu.Append(wx.ID_ANY, "Select Folders\tCtrl+O", "Select folders to play")
        self.Bind(wx.EVT_MENU, self._on_select_folders, select_item)
        select_recursive_item = file_menu.Append(wx.ID_ANY, "Select Folder (with subfolders)\tCtrl+Shift+O", "Select folder and include all subfolders")
        self.Bind(wx.EVT_MENU, self._on_select_folder_recursive, select_recursive_item)
        file_menu.AppendSeparator()
        upload_log_item = file_menu.Append(wx.ID_ANY, "Upload Log\tCtrl+Shift+U", "Upload log file to GitHub for troubleshooting")
        self.Bind(wx.EVT_MENU, self._on_upload_log, upload_log_item)
        check_updates_item = file_menu.Append(wx.ID_ANY, "Check for Updates", "Check for and install program updates")
        self.Bind(wx.EVT_MENU, self._on_check_updates, check_updates_item)
        file_menu.AppendSeparator()
        set_movies_dir = file_menu.Append(wx.ID_ANY, "Set Default Movies Folder", "Set default download folder for movies")
        self.Bind(wx.EVT_MENU, lambda e: self._on_set_default_folder("movies"), set_movies_dir)
        set_shows_dir = file_menu.Append(wx.ID_ANY, "Set Default TV Shows Folder", "Set default download folder for TV shows")
        self.Bind(wx.EVT_MENU, lambda e: self._on_set_default_folder("shows"), set_shows_dir)
        file_menu.AppendSeparator()
        restore_item = file_menu.Append(wx.ID_ANY, "Restore Channel Backup\tCtrl+Shift+R", "Restore channels from a backup")
        self.Bind(wx.EVT_MENU, self._on_restore_backup, restore_item)
        file_menu.AppendSeparator()
        quit_item = file_menu.Append(wx.ID_EXIT, "Quit\tCtrl+Q", "Quit without outro")
        self.Bind(wx.EVT_MENU, self._on_quick_quit, quit_item)
        menubar.Append(file_menu, "&File")
        
        # Channels menu
        channels_menu = wx.Menu()
        new_channel_item = channels_menu.Append(wx.ID_ANY, "New Channel\tCtrl+T", "Create a new channel")
        self.Bind(wx.EVT_MENU, self._on_new_channel, new_channel_item)
        rename_channel_item = channels_menu.Append(wx.ID_ANY, "Rename Channel\tCtrl+R", "Rename current channel")
        self.Bind(wx.EVT_MENU, self._on_rename_channel, rename_channel_item)
        delete_channel_item = channels_menu.Append(wx.ID_ANY, "Delete Channel\tCtrl+D", "Delete current channel")
        self.Bind(wx.EVT_MENU, self._on_delete_channel, delete_channel_item)
        # Honey, 2026-11-23: get rid of a channel's downloads, e.g.
        # "A Killer Among Friends" - deletes its downloaded files
        # from disk and removes the channel, so it stops coming up.
        delete_dl_item = channels_menu.Append(wx.ID_ANY, "Delete Channel and Downloads\tCtrl+Shift+D", "Delete the current channel and all its downloaded files")
        self.Bind(wx.EVT_MENU, self._on_delete_channel_downloads, delete_dl_item)
        channels_menu.AppendSeparator()
        list_channels_item = channels_menu.Append(wx.ID_ANY, "List Channels\tCtrl+L", "Show list of all channels")
        self.Bind(wx.EVT_MENU, self._on_list_channels, list_channels_item)
        channels_menu.AppendSeparator()
        channels_menu.Append(wx.ID_ANY, "Next Channel\tCtrl+Tab", "Switch to next channel")
        channels_menu.Append(wx.ID_ANY, "Previous Channel\tCtrl+Shift+Tab", "Switch to previous channel")
        menubar.Append(channels_menu, "&Channels")
        
        # Controls menu
        controls_menu = wx.Menu()
        controls_menu.Append(wx.ID_ANY, "Play/Pause\tSpace", "Toggle playback")
        controls_menu.Append(wx.ID_ANY, "Previous File\tLeft", "Go to previous file")
        controls_menu.Append(wx.ID_ANY, "Next File\tRight", "Go to next file")
        controls_menu.Append(wx.ID_ANY, "Previous Folder\tCtrl+Left", "Go to previous folder")
        controls_menu.Append(wx.ID_ANY, "Next Folder\tCtrl+Right", "Go to next folder")
        controls_menu.Append(wx.ID_ANY, "Rewind 10s\tShift+Left", "Rewind 10 seconds")
        controls_menu.Append(wx.ID_ANY, "Fast Forward 10s\tShift+Right", "Fast forward 10 seconds")
        controls_menu.AppendSeparator()
        set_bookmark_item = controls_menu.Append(wx.ID_ANY, "Set Bookmark\tCtrl+S", "Create bookmark at current position")
        self.Bind(wx.EVT_MENU, self._on_set_bookmark, set_bookmark_item)
        jump_bookmark_item = controls_menu.Append(wx.ID_ANY, "Jump to Bookmark\tCtrl+J", "Jump to a saved bookmark")
        self.Bind(wx.EVT_MENU, self._on_jump_bookmark, jump_bookmark_item)
        delete_file_item = controls_menu.Append(wx.ID_ANY, "Remove Current File\tCtrl+Delete",
                                                "Delete the currently playing file and remove it from this channel")
        self.Bind(wx.EVT_MENU, self._on_delete_current_file, delete_file_item)
        controls_menu.AppendSeparator()
        voice_listen_item = controls_menu.Append(wx.ID_ANY, "Voice Command (One-time)\tCtrl+Shift+B", "Listen for one voice command")
        self.Bind(wx.EVT_MENU, self._toggle_voice_listening, voice_listen_item)
        wake_word_item = controls_menu.Append(wx.ID_ANY, "Wake Word Mode\tCtrl+Shift+W", "Toggle continuous wake word listening")
        self.Bind(wx.EVT_MENU, self._toggle_wake_word_mode, wake_word_item)
        tv_guide_item = controls_menu.Append(wx.ID_ANY, "What's Coming Up Next\tCtrl+Shift+G", "Hear the TV guide: what is playing now and what comes up next")
        self.Bind(wx.EVT_MENU, self._on_tv_guide, tv_guide_item)
        controls_menu.AppendSeparator()
        toggle_sounds_item = controls_menu.Append(wx.ID_ANY, "Toggle Sounds\tCtrl+Shift+S", "Turn startup/exit sounds on or off")
        self.Bind(wx.EVT_MENU, self._toggle_sounds, toggle_sounds_item)
        nvda_quiet_item = controls_menu.AppendCheckItem(wx.ID_ANY, "NVDA Quiet While In App\tCtrl+Shift+Q", "Stop NVDA talking while you are in AudioVault TV; NVDA talks again when you close the app")
        self.Bind(wx.EVT_MENU, self._on_toggle_nvda_quiet, nvda_quiet_item)
        self._nvda_quiet_menu_item = nvda_quiet_item
        set_name_item = controls_menu.Append(wx.ID_ANY, "Set My Name", "Set your name for personalized messages")
        self.Bind(wx.EVT_MENU, self._on_set_name, set_name_item)
        install_voice_item = controls_menu.Append(wx.ID_ANY, "Install My Reading Voice", "Get Samantha's reading voice ready, so she can read the show list")
        self.Bind(wx.EVT_MENU, self._on_install_reading_voice, install_voice_item)
        install_listen_item = controls_menu.Append(wx.ID_ANY, "Install the Listening Model", "Get Samantha listening, so she can hear your voice commands")
        self.Bind(wx.EVT_MENU, self._on_install_listening_model, install_listen_item)
        install_all_item = controls_menu.Append(wx.ID_ANY, "Install Everything I Need", "Get everything Audio Vault TV needs — reading voice, voice listening, sound playing, getting shows — so nothing needs Command Prompt")
        self.Bind(wx.EVT_MENU, self._on_install_requirements, install_all_item)
        controls_menu.AppendSeparator()
        cloud_toggle_item = controls_menu.Append(wx.ID_ANY, "Auto Free Up Space (OneDrive)",
                                                 "Automatically make downloads online-only to save disk space")
        self.Bind(wx.EVT_MENU, self._toggle_cloud_cleanup, cloud_toggle_item)
        free_space_item = controls_menu.Append(wx.ID_ANY, "Free Up Space Now",
                                               "Make all downloaded files online-only right now")
        self.Bind(wx.EVT_MENU, self._on_free_up_space_now, free_space_item)
        menubar.Append(controls_menu, "&Controls")
        
        # AudioVault menu
        vault_menu = wx.Menu()
        self.vault_login_item = vault_menu.Append(wx.ID_ANY, "Login\tCtrl+Shift+L", "Login to AudioVault")
        self.Bind(wx.EVT_MENU, self._on_vault_login_toggle, self.vault_login_item)
        vault_menu.AppendSeparator()
        search_movies_item = vault_menu.Append(wx.ID_ANY, "Search Movies\tCtrl+Shift+F", "Search AudioVault movies")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_search(e, "movies"), search_movies_item)
        search_shows_item = vault_menu.Append(wx.ID_ANY, "Search TV Shows\tCtrl+Shift+T", "Search AudioVault TV shows")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_search(e, "shows"), search_shows_item)
        vault_menu.AppendSeparator()
        recent_movies_item = vault_menu.Append(wx.ID_ANY, "Recent Movies\tCtrl+Shift+M", "View recently added movies")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_recents(e, "movies"), recent_movies_item)
        recent_shows_item = vault_menu.Append(wx.ID_ANY, "Recent TV Shows\tCtrl+Shift+N", "View recently added shows")
        self.Bind(wx.EVT_MENU, lambda e: self._on_vault_recents(e, "shows"), recent_shows_item)
        vault_menu.AppendSeparator()
        download_status_item = vault_menu.Append(wx.ID_ANY, "Download Status", "Hear what is downloading in the background right now")
        self.Bind(wx.EVT_MENU, self._on_download_status, download_status_item)
        cancel_downloads_item = vault_menu.Append(wx.ID_ANY, "Cancel Downloads", "Stop any downloads running in the background")
        self.Bind(wx.EVT_MENU, self._on_cancel_downloads, cancel_downloads_item)
        menubar.Append(vault_menu, "&AudioVault")
        
        # YouTube menu
        if YT_AVAILABLE:
            yt_menu = wx.Menu()
            yt_search_item = yt_menu.Append(wx.ID_ANY, "Search YouTube\tCtrl+Y", "Search and download from YouTube")
            self.Bind(wx.EVT_MENU, self._on_yt_search, yt_search_item)
            yt_url_item = yt_menu.Append(wx.ID_ANY, "Download from URL\tCtrl+Shift+Y", "Download audio from a YouTube URL")
            self.Bind(wx.EVT_MENU, self._on_yt_url, yt_url_item)
            yt_folder_item = yt_menu.Append(wx.ID_ANY, "Set Download Folder", "Set default YouTube download folder")
            self.Bind(wx.EVT_MENU, self._on_yt_set_folder, yt_folder_item)
            yt_status_item = yt_menu.Append(wx.ID_ANY, "Download Status", "Hear what is downloading in the background right now")
            self.Bind(wx.EVT_MENU, self._on_download_status, yt_status_item)
            yt_menu.AppendSeparator()
            yt_update_item = yt_menu.Append(wx.ID_ANY, "Update YouTube Downloader", "Update yt-dlp to fix download issues")
            self.Bind(wx.EVT_MENU, self._on_yt_update, yt_update_item)
            menubar.Append(yt_menu, "&YouTube")
        
        # Live TV menu (iptv-org)
        if LIVETV_AVAILABLE:
            livetv_menu = wx.Menu()
            lt_browse = livetv_menu.Append(wx.ID_ANY, "Browse Live Channels\tCtrl+Shift+V", "Browse live TV channels by category")
            self.Bind(wx.EVT_MENU, self._on_livetv_browse, lt_browse)
            lt_search = livetv_menu.Append(wx.ID_ANY, "Search Live Channels", "Search live TV channels by name")
            self.Bind(wx.EVT_MENU, self._on_livetv_search, lt_search)
            lt_favs = livetv_menu.Append(wx.ID_ANY, "Live TV Favorites", "View your favorite live channels")
            self.Bind(wx.EVT_MENU, self._on_livetv_favorites, lt_favs)
            livetv_menu.AppendSeparator()
            lt_stop = livetv_menu.Append(wx.ID_ANY, "Stop Live TV\tCtrl+Shift+X", "Stop the live stream")
            self.Bind(wx.EVT_MENU, self._on_livetv_stop, lt_stop)
            lt_refresh = livetv_menu.Append(wx.ID_ANY, "Refresh Channel List", "Re-download the live channel list")
            self.Bind(wx.EVT_MENU, self._on_livetv_refresh, lt_refresh)
            menubar.Append(livetv_menu, "&Live TV")
        
        # Voice menu: switch Samantha's reading voice between the
        # Fish Audio voices and the Edge reading voice. The check
        # follows whatever config.ini says, and "Hear a Sample"
        # reads a short line in the selected voice, so the choice
        # can be made by ear.
        voice_menu = wx.Menu()
        self._voice_menu_items = {}  # {menu item id: (item, name)}
        for _vname in _FISH_VOICES:
            # wx.ITEM_CHECK makes the item checkable, so the menu can
            # put a tick on the voice config.ini currently uses. Without
            # it, Check() trips a C++ assertion on Windows.
            item = voice_menu.Append(wx.ID_ANY, f"{_vname} (Fish Audio)",
                                     kind=wx.ITEM_CHECK)
            # wx.MenuItem is not a window, so it has no Bind. Bind on
            # the frame with the item as scope, like the other menus
            # in this file; the handler picks the item by event id.
            self.Bind(wx.EVT_MENU, self._on_voice_select, item)
            self._voice_menu_items[item.GetId()] = (item, _vname)
        item = voice_menu.Append(wx.ID_ANY, _EDGE_VOICE_OPTION,
                                 kind=wx.ITEM_CHECK)
        self.Bind(wx.EVT_MENU, self._on_voice_select, item)
        self._voice_menu_items[item.GetId()] = (item, _EDGE_VOICE_OPTION)
        voice_menu.AppendSeparator()
        voice_sample = voice_menu.Append(wx.ID_ANY, "Hear a Sample")
        self.Bind(wx.EVT_MENU, self._on_voice_sample, voice_sample)
        voice_menu.Bind(wx.EVT_MENU_OPEN, self._on_voice_menu_open)
        menubar.Append(voice_menu, "&Voice")
        
        self.SetMenuBar(menubar)
        
        # Main panel. Ashley, 2026-11-27: NVDA kept saying
        # "pane" all the time. The panel had no name, so that is
        # all NVDA had to say when focus landed on it. Give it
        # the app name, and keep a handle to it so focus can be
        # moved off it (see _focus_command_box_if_on_panel).
        panel = wx.Panel(self)
        panel.SetName("Audio Vault TV")
        self._main_panel = panel
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        # Channel display
        sizer.Add(wx.StaticText(panel, label="Current Channel:"), 0, wx.LEFT | wx.TOP, 10)
        self.channel_label = wx.StaticText(panel, label="No channel")
        sizer.Add(self.channel_label, 0, wx.ALL, 10)
        
        # Current folder display
        sizer.Add(wx.StaticText(panel, label="Current Folder:"), 0, wx.LEFT | wx.TOP, 10)
        self.folder_label = wx.StaticText(panel, label="No folder selected")
        sizer.Add(self.folder_label, 0, wx.ALL, 10)
        
        # Current file display
        sizer.Add(wx.StaticText(panel, label="Current File:"), 0, wx.LEFT | wx.TOP, 10)
        self.file_label = wx.StaticText(panel, label="No file loaded")
        sizer.Add(self.file_label, 0, wx.ALL, 10)
        
        # Position display
        sizer.Add(wx.StaticText(panel, label="Position:"), 0, wx.LEFT | wx.TOP, 10)
        self.position_label = wx.StaticText(panel, label="0:00")
        sizer.Add(self.position_label, 0, wx.ALL, 10)
        
        # Status display
        self.status_label = wx.StaticText(panel, label="Press Ctrl+T to create a channel")
        sizer.Add(self.status_label, 0, wx.ALL, 10)

        # Type to Samantha: a text box, so Ashley can type a
        # command when Samantha cannot hear her (Ashley,
        # 2026-11-26: "I still want the text box just in case
        # she can't hear me"). Pressing Enter runs it and
        # Samantha answers in her own voice, the same as if
        # it had been spoken. Tab reaches the box; NVDA reads
        # its label.
        sizer.Add(wx.StaticText(panel, label="Type to Samantha (press Enter):"), 0, wx.LEFT | wx.TOP, 10)
        self.command_box = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.command_box.Bind(wx.EVT_TEXT_ENTER, self._on_command_box_enter)
        # Belt and braces for Enter (see _on_command_box_key):
        # EVT_TEXT_ENTER is the normal path, but if Enter never
        # produces one, the key itself still runs the command.
        self.command_box.Bind(wx.EVT_KEY_DOWN, self._on_command_box_key)
        sizer.Add(self.command_box, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(sizer)
    
    def _bind_hotkeys(self):
        """Bind keyboard shortcuts"""
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)
    
    def _on_key(self, event):
        """Handle keyboard events"""
        keycode = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        # Ashley, 2026-11-27: Ctrl+Shift+B "does not seem to
        # be working". One reason was here: when focus was in
        # the "Type to Samantha" box, this handler returned
        # early for EVERY key — including Ctrl+Shift+B and
        # Ctrl+Shift+W — so pressing B while in the box did
        # nothing at all. And the box is where focus usually
        # is: it keeps focus after Enter, and it is where she
        # types. So the voice keys are handled first, whatever
        # has focus, and only the other keys are handed to
        # the box.
        if ctrl and shift and keycode == ord('B'):
            self._toggle_voice_listening()
            return
        if ctrl and shift and keycode == ord('W'):
            self._toggle_wake_word_mode()
            return
        if ctrl and shift and keycode == ord('Q'):
            self._on_toggle_nvda_quiet()
            return
        # Typing in the command box: let the box have every
        # other key (Space types a space, Enter sends the
        # command, arrows move the caret) instead of the app
        # hotkeys, which would otherwise pause playback on
        # Space.
        if getattr(self, "command_box", None) is not None:
            try:
                if wx.Window.FindFocus() is self.command_box:
                    event.Skip()
                    return
            except Exception:
                pass
        
        if keycode == wx.WXK_SPACE:
            self._toggle_play_pause()
        elif keycode == wx.WXK_TAB and ctrl:
            if shift:
                self._prev_channel()
            else:
                self._next_channel()
        elif keycode == ord('Q') and ctrl and shift:
            self._on_toggle_nvda_quiet()
        # NOTE, Ashley, 2026-11-26: Ctrl+Shift+G was tried as
        # a second NVDA-quiet key, but it is already the TV
        # guide key ("What's Coming Up Next", menu line 290),
        # so it stays the guide. Ctrl+Shift+Q is the NVDA
        # quiet toggle.
        elif keycode == ord('B') and ctrl and shift:
            self._toggle_voice_listening()
        elif keycode == ord('W') and ctrl and shift:
            self._toggle_wake_word_mode()
        elif keycode == ord('S') and ctrl and not shift:
            self._on_set_bookmark(None)
        elif keycode == ord('J') and ctrl:
            self._on_jump_bookmark(None)
        elif keycode == wx.WXK_DELETE and ctrl:
            self._on_delete_current_file(None)
        elif keycode == wx.WXK_LEFT:
            if ctrl:
                self._prev_folder()
            elif shift:
                self._rewind()
            else:
                self._prev_file()
        elif keycode == wx.WXK_RIGHT:
            if ctrl:
                self._next_folder()
            elif shift:
                self._fastforward()
            else:
                self._next_file()
        else:
            event.Skip()
    
    def _on_select_folders(self, event):
        """Open folder selection dialog"""
        if not self.channels.current_channel:
            wx.MessageBox("Please create a channel first (Ctrl+T)", "No Channel", wx.OK | wx.ICON_INFORMATION)
            return
        
        folders = []
        
        while True:
            dlg = wx.DirDialog(self, "Select a folder with MP3 files", style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
            
            if dlg.ShowModal() == wx.ID_OK:
                folders.append(dlg.GetPath())
                dlg.Destroy()
                
                result = wx.MessageBox("Add another folder?", "Continue", wx.YES_NO | wx.ICON_QUESTION)
                if result != wx.YES:
                    break
            else:
                dlg.Destroy()
                break
        
        if folders:
            self.playlist.add_folders(folders)
            self._load_current_file()
            self._update_display()
            self.channels.update_current_channel(folders=folders)
            self.status_label.SetLabel(f"Loaded {len(folders)} folder(s) with {len(self.playlist.playlist)} files total")
            self._start_playback()
    
    def _on_select_folder_recursive(self, event):
        """Open folder selection dialog and include all subfolders"""
        if not self.channels.current_channel:
            wx.MessageBox("Please create a channel first (Ctrl+T)", "No Channel", wx.OK | wx.ICON_INFORMATION)
            return
        
        dlg = wx.DirDialog(self, "Select Folder (all subfolders will be included)", style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST)
        
        if dlg.ShowModal() == wx.ID_OK:
            parent_folder = Path(dlg.GetPath())
            # Get all subfolders that contain MP3 files
            from playlist_manager import natural_sort_key
            subfolders = []
            for subfolder in sorted(parent_folder.rglob("*"), key=lambda x: natural_sort_key(str(x))):
                if subfolder.is_dir():
                    # Check if this folder has MP3 files
                    if any(f.suffix.lower() == '.mp3' for f in subfolder.iterdir() if f.is_file()):
                        subfolders.append(str(subfolder))
            
            if subfolders:
                self.playlist.add_folders(subfolders)
                self._load_current_file()
                self._update_display()
                self.channels.update_current_channel(folders=subfolders)
                self.status_label.SetLabel(f"Loaded {len(subfolders)} subfolder(s) with {len(self.playlist.playlist)} files total")
                self._start_playback()
            else:
                self.status_label.SetLabel("No subfolders with MP3 files found")
        
        dlg.Destroy()
    
    def _load_current_file(self):
        """Load current file from playlist"""
        current = self.playlist.get_current()
        if current:
            filepath = current[1]
            try:
                if self.player.load(str(filepath)):
                    self._update_display()
                    return True
            except Exception as e:
                self.status_label.SetLabel(f"Error loading file: {e}")
                return False
        return False
    
    def _toggle_play_pause(self):
        """Toggle play/pause.

        Live TV can't truly pause (it's a live broadcast), so we emulate
        pause/resume: Space stops the stream; Space again re-tunes the SAME
        live channel from the live edge. Only once the user does something
        else (picks a channel, selects folders) do we leave 'live mode' and
        let Space control the local MP3 player again.
        """
        # Currently streaming live -> stop it (acts as "pause")
        if getattr(self, "livetv_process", None):
            self.logger.log_playback("LIVETV", "Space pressed during live TV -> pausing stream")
            self._livetv_stop_stream()
            self._update_title()
            msg = "Live TV paused"
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
            return

        # Stopped, but live TV was the last thing playing -> resume it (re-tune)
        if getattr(self, "_livetv_last_channel", None):
            ch = self._livetv_last_channel
            self.logger.log_playback("LIVETV", "Space pressed -> resuming last live channel")
            self._answer_in_samantha_voice("Resuming live TV")
            self._livetv_play(ch)
            return

        if not self.playlist.get_current():
            # No local shows at all: fall back to Live TV, which streams
            # over the internet and does not need the external drive.
            # This works with the drive plugged in too - it only runs
            # when there is nothing local to play.
            if self._livetv_fallback("No shows are available"):
                return
            msg = "No files loaded. Use Ctrl+O to select folders."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
            return
        
        if self.player.is_playing:
            self.player.pause()
            # Auto-resume: save the position right away so a crash
            # while paused can't lose it.
            try:
                self._save_current_channel_state()
            except Exception:
                pass
            msg = ("Paused: "
                   + self._spoken_episode(
                       self.playlist.get_current_file_name()))
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
        else:
            # If no file loaded yet, load it first
            if not self.player.current_file:
                if self._load_current_file():
                    self.player.play()
                    msg = self._spoken_playing_msg(
                        self.playlist.get_current_file_name())
                    self.status_label.SetLabel(msg)
                    self._answer_in_samantha_voice(msg)
            else:
                self.player.unpause()
                msg = self._spoken_playing_msg(
                    self.playlist.get_current_file_name())
                self.status_label.SetLabel(msg)
                self._answer_in_samantha_voice(msg)

    def _start_playback(self):
        """Stop any live stream and start/resume local MP3 playback.
        Used by auto-play after selecting folders or a channel (unlike the
        Space key, this always begins local playback)."""
        if getattr(self, "livetv_process", None):
            self._livetv_stop_stream()
            self._update_title()
        # The user chose local content, so leave live mode: Space should now
        # control the MP3 player, not resume a live channel.
        self._livetv_last_channel = None
        if not self.playlist.get_current():
            # No local show to play: fall back to Live TV instead of
            # stopping silently. Live TV streams over the internet,
            # so it plays with or without the external drive.
            self._livetv_fallback("No shows are available")
            return
        if not self.player.is_playing:
            # Every show says its own name first, so Doctor Who says
            # "Doctor Who", Odd Squad says "Odd Squad", The Big Bang Theory
            # says "The Big Bang Theory", and no show ever says another
            # show's name.
            channel_name = self.channels.current_channel or ""
            if not self.player.current_file:
                if self._load_current_file():
                    self.player.play()
                    msg = self._spoken_playing_msg(
                        self.playlist.get_current_file_name(), channel_name)
                    self.status_label.SetLabel(msg)
                    self._answer_in_samantha_voice(msg)
            else:
                self.player.unpause()
                msg = self._spoken_playing_msg(
                    self.playlist.get_current_file_name(), channel_name)
                self.status_label.SetLabel(msg)
                self._answer_in_samantha_voice(msg)

    def _on_delete_current_file(self, event=None):
        """Delete the currently-loaded file from disk and remove it from the
        channel, then move on to the next file. Bound to Ctrl+Delete."""
        current = self.playlist.get_current()
        if not current:
            msg = "No file is loaded to remove."
            self.status_label.SetLabel(msg)
            speak(msg)
            return

        filepath = str(current[1])
        file_name = self.playlist.get_current_file_name()

        # Confirm, so a file isn't deleted by an accidental key press
        result = wx.MessageBox(
            f"Remove and delete this file?\n\n{file_name}\n\n"
            f"This deletes the file from your computer and removes it from this channel.",
            "Delete File",
            wx.YES_NO | wx.ICON_WARNING
        )
        if result != wx.YES:
            return

        # Stop playback and release the file so the OS lets us delete it
        try:
            self.player.stop()
            self.player.is_playing = False
            self.player.current_file = None
            try:
                self.player.unload()
            except Exception:
                pass
        except Exception:
            pass

        # Delete from disk (best effort)
        deleted = False
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                deleted = True
        except Exception as e:
            self.logger.log_error(f"DELETE FILE ERROR: {file_name} - {e}")
            wx.MessageBox(
                f"Could not delete the file from disk: {e}\n\n"
                f"It will still be removed from this channel.",
                "Delete Warning", wx.OK | wx.ICON_WARNING
            )

        # Remove from the in-memory playlist and refresh the channel cache
        self.playlist.remove_current()
        try:
            self.channels.update_current_channel(
                cached_playlist=self.playlist.get_cache_data()
            )
        except Exception:
            pass

        self.logger.log_channel("REMOVE-FILE", self.channels.current_channel or "",
                                f"{file_name} (deleted from disk: {deleted})")

        # Load whatever is now at the current position and continue
        if self.playlist.get_current():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            new_name = self.playlist.get_current_file_name()
            msg = ("Removed " + self._spoken_episode(file_name)
                   + ". Now on: " + self._spoken_episode(new_name))
        else:
            msg = ("Removed " + self._spoken_episode(file_name)
                   + ". No more files in this channel.")
        self.status_label.SetLabel(msg)
        speak(msg)

    def _next_file(self):
        """Go to next file"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.next_file():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            # Auto-resume: record the new file right away.
            try:
                self._save_current_channel_state(quiet=True)
            except Exception:
                pass
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("NEXT FILE", old_file, new_file)
            # Spoken name only: the folder is usually the show name
            # again, so "folder - file" said the show twice, then
            # the file name with ".mp3" and its S01E02 code.
            msg = "Next file: " + self._spoken_episode(file)
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
    
    def _prev_file(self):
        """Go to previous file"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.prev_file():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            # Auto-resume: record the new file right away.
            try:
                self._save_current_channel_state(quiet=True)
            except Exception:
                pass
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("PREV FILE", old_file, new_file)
            msg = "Previous file: " + self._spoken_episode(file)
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
    
    def _next_folder(self):
        """Go to next folder"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.next_folder():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            # Auto-resume: record the new file right away.
            try:
                self._save_current_channel_state(quiet=True)
            except Exception:
                pass
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("NEXT FOLDER", old_file, new_file)
            msg = "Next folder: " + self._spoken_episode(file)
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
    
    def _prev_folder(self):
        """Go to previous folder"""
        old_file = f"{self.playlist.get_current_folder_name()}/{self.playlist.get_current_file_name()}"
        if self.playlist.prev_folder():
            self._load_current_file()
            if self.player.is_playing:
                self.player.play()
            # Auto-resume: record the new file right away.
            try:
                self._save_current_channel_state(quiet=True)
            except Exception:
                pass
            folder = self.playlist.get_current_folder_name()
            file = self.playlist.get_current_file_name()
            new_file = f"{folder}/{file}"
            self.logger.log_navigation("PREV FOLDER", old_file, new_file)
            msg = "Previous folder: " + self._spoken_episode(file)
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
    
    def _rewind(self):
        """Rewind 10 seconds"""
        self.player.rewind(10)
        # Auto-resume: save the new position right away.
        try:
            self._save_current_channel_state()
        except Exception:
            pass
        pos = self.player.get_position()
        minutes = int(pos // 60)
        seconds = int(pos % 60)
        msg = f"Rewind to {minutes}:{seconds:02d}"
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
    
    def _fastforward(self):
        """Fast forward 10 seconds"""
        self.player.fastforward(10)
        # Auto-resume: save the new position right away.
        try:
            self._save_current_channel_state()
        except Exception:
            pass
        pos = self.player.get_position()
        minutes = int(pos // 60)
        seconds = int(pos % 60)
        msg = f"Fast forward to {minutes}:{seconds:02d}"
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
    
    def _on_clear_all(self, event):
        """Clear all folders and stop playback"""
        self.player.stop()
        self.playlist.folders = []
        self.playlist.playlist = []
        self.playlist.current_index = 0
        self.folder_label.SetLabel("No folder selected")
        self.file_label.SetLabel("No file loaded")
        self.position_label.SetLabel("0:00")
        self.SetTitle("AudioVault TV")
        self.status_label.SetLabel("Cleared. Press Ctrl+O to select folders.")
    
    def _update_display(self):
        """Update UI labels and title bar"""
        folder_name = self.playlist.get_current_folder_name()
        file_name = self.playlist.get_current_file_name()
        
        self.folder_label.SetLabel(folder_name if folder_name else "No folder selected")
        self.file_label.SetLabel(file_name if file_name else "No file loaded")
        self.channel_label.SetLabel(self.channels.current_channel or "No channel")
    
    def _update_title(self):
        """Update window title with current channel"""
        if self.channels.current_channel:
            self.SetTitle(f"AudioVault TV - {self.channels.current_channel}")
        else:
            self.SetTitle("AudioVault TV")
    
    def _save_current_channel_state(self, quiet=False):
        """Save current playback state to channel.

        quiet=True is used by the high-frequency auto-saves (once per
        second while playing, after file/folder jumps) so the debug
        log isn't flooded; user-triggered saves (quit, channel
        switch, pause, rewind/fast-forward) still log.
        """
        if self.channels.current_channel and self.playlist.get_current():
            current_position = self.player.get_position()
            if current_position < 0:
                # Mixer reports no active music (file loaded but not
                # started, or a brief gap): treat as the start.
                current_position = 0
            self.channels.update_current_channel(
                current_index=self.playlist.current_index,
                position=current_position
            )
            if not quiet:
                # Log what we're saving
                minutes = int(current_position // 60)
                seconds = int(current_position % 60)
                file_name = self.playlist.get_current_file_name()
                self.logger.log_channel("SAVED", self.channels.current_channel, f"File: {file_name}, Position: {minutes}:{seconds:02d}")
    
    def _load_current_channel(self):
        """Load current channel data"""
        if not self.channels.has_channels():
            return
        
        channel_data = self.channels.get_current_channel_data()
        if channel_data and channel_data['folders']:
            # Use cached playlist if available, otherwise scan folders.
            # The cache was already repaired on load (stale entries
            # dropped, index clamped), so a stale cache can no longer
            # point at a file that is gone.
            cached_playlist = channel_data.get('cached_playlist')
            if cached_playlist:
                self.playlist.load_from_cache(channel_data['folders'], cached_playlist)
                if not self.playlist.playlist:
                    # Every cached file is gone: rescan the folders
                    # instead of sitting on an empty playlist.
                    self.playlist.add_folders(channel_data['folders'])
                    self.channels.update_current_channel(cached_playlist=self.playlist.get_cache_data())
            else:
                self.playlist.add_folders(channel_data['folders'])
                # Save cache for next time
                self.channels.update_current_channel(cached_playlist=self.playlist.get_cache_data())

            # Files unmixed out of this channel stay out: a
            # rescan of its folders must not put them back in.
            removed_names = set(channel_data.get("mixed_files_removed") or [])
            if removed_names and self.playlist.playlist:
                before = len(self.playlist.playlist)
                self.playlist.playlist = [
                    (i, fp) for i, fp in self.playlist.playlist
                    if fp.name not in removed_names]
                if len(self.playlist.playlist) != before:
                    self.channels.update_current_channel(
                        cached_playlist=self.playlist.get_cache_data())

            # Clamp the saved index: a file that was deleted could
            # otherwise leave it past the end of the playlist.
            try:
                saved_index = int(channel_data.get('current_index', 0))
            except Exception:
                saved_index = 0
            if self.playlist.playlist:
                saved_index = max(0, min(saved_index, len(self.playlist.playlist) - 1))
            else:
                saved_index = 0
            self.playlist.set_index(saved_index)
            self._load_current_file()
            saved_position = channel_data.get('position', 0)
            self.player.paused_position = saved_position
            self._update_display()
            
            # Show position info
            minutes = int(saved_position // 60)
            seconds = int(saved_position % 60)
            file_name = self.playlist.get_current_file_name()
            msg = f"Loaded {self.channels.current_channel}: {file_name} at {minutes}:{seconds:02d}. Press Space to play."
            self.status_label.SetLabel(msg)
            self.logger.log_channel("LOADED", self.channels.current_channel, f"File: {file_name}, Position: {minutes}:{seconds:02d}")
    
    def _on_restore_backup(self, event):
        """Restore channels from a backup"""
        backups = self.channels.get_backups()
        if not backups:
            msg = "No backups available."
            wx.MessageBox(msg, "No Backups", wx.OK | wx.ICON_INFORMATION)
            speak(msg)
            return

        items = [display for _, display in backups]
        dlg = wx.SingleChoiceDialog(self, "Select a backup to restore:", "Restore Channel Backup", items)
        if dlg.ShowModal() == wx.ID_OK:
            idx = dlg.GetSelection()
            backup_path = backups[idx][0]
            dlg.Destroy()

            confirm = wx.MessageBox(
                f"Restore backup from {items[idx]}?\n\nThis will replace your current channel list.",
                "Confirm Restore",
                wx.YES_NO | wx.ICON_WARNING
            )
            if confirm == wx.YES:
                if self.channels.restore_backup(backup_path):
                    self.player.stop()
                    self.player.is_playing = False
                    self.playlist = PlaylistManager()
                    self._load_current_channel()
                    self._update_title()
                    self._update_display()
                    msg = "Backup restored successfully."
                    self.status_label.SetLabel(msg)
                    speak(msg)
                else:
                    msg = "Failed to restore backup."
                    wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)
                    speak(msg)
        else:
            dlg.Destroy()

    def _on_new_channel(self, event):
        """Create a new channel"""
        dlg = wx.TextEntryDialog(self, "Enter channel name:", "New Channel")
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name:
                if self.channels.create_channel(name):
                    self._save_current_channel_state()
                    self.player.stop()
                    self.player.is_playing = False
                    self.playlist = PlaylistManager()
                    self._update_display()
                    self._update_title()
                    self.status_label.SetLabel(f"Created channel: {name}. Press Ctrl+O to add folders.")
                else:
                    wx.MessageBox("Channel already exists or invalid name", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()
    
    def _on_rename_channel(self, event):
        """Rename current channel"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        dlg = wx.TextEntryDialog(self, "Enter new name:", "Rename Channel", self.channels.current_channel)
        if dlg.ShowModal() == wx.ID_OK:
            new_name = dlg.GetValue().strip()
            if new_name:
                if self.channels.rename_channel(self.channels.current_channel, new_name):
                    self._update_display()
                    self._update_title()
                    self.status_label.SetLabel(f"Renamed to: {new_name}")
                else:
                    wx.MessageBox("Channel name already exists or invalid", "Error", wx.OK | wx.ICON_ERROR)
        dlg.Destroy()
    
    def _on_delete_channel(self, event):
        """Delete current channel"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        result = wx.MessageBox(f"Delete channel '{self.channels.current_channel}'?", "Confirm Delete", wx.YES_NO | wx.ICON_QUESTION)
        if result == wx.YES:
            old_name = self.channels.current_channel
            if self.channels.delete_channel(old_name):
                self.player.stop()
                self.player.is_playing = False
                self.playlist = PlaylistManager()
                self._load_current_channel()
                self._update_display()
                self._update_title()
                self.status_label.SetLabel(f"Deleted channel: {old_name}")
    
    def _on_list_channels(self, event):
        """Show list of channels"""
        channels = self.channels.get_channel_list()
        if not channels:
            wx.MessageBox("No channels available. Press Ctrl+T to create one.", "No Channels", wx.OK | wx.ICON_INFORMATION)
            return
        
        dlg = wx.SingleChoiceDialog(self, "Select a channel:", "Channels", channels)
        if self.channels.current_channel and self.channels.current_channel in channels:
            dlg.SetSelection(channels.index(self.channels.current_channel))
        
        if dlg.ShowModal() == wx.ID_OK:
            selected = dlg.GetStringSelection()
            self._switch_to_channel(selected)
        dlg.Destroy()
    
    def _next_channel(self):
        """Switch to next channel"""
        self._save_current_channel_state()
        next_ch = self.channels.next_channel()
        if next_ch:
            self._switch_to_channel(next_ch)
        else:
            msg = "No channels available"
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
    
    def _prev_channel(self):
        """Switch to previous channel"""
        self._save_current_channel_state()
        prev_ch = self.channels.prev_channel()
        if prev_ch:
            self._switch_to_channel(prev_ch)
        else:
            msg = "No channels available"
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
    
    def _switch_to_channel(self, channel_name, start_from_beginning=False):
        """Switch to a specific channel"""
        self._play_sound_effect("remote.mp3")
        # Switching to a local MP3 channel exits live mode and stops any stream.
        if getattr(self, "livetv_process", None):
            self._livetv_stop_stream()
        self._livetv_last_channel = None
        # Stop timer during switch to prevent saving wrong state
        self.timer.Stop()
        if self.channels.switch_channel(channel_name):
            self.player.stop()
            self.player.is_playing = False
            self.playlist = PlaylistManager()
            
            if start_from_beginning:
                # Load channel but start from index 0
                channel_data = self.channels.get_current_channel_data()
                if channel_data and channel_data['folders']:
                    self.playlist.add_folders(channel_data['folders'])
                    self.playlist.set_index(0)  # Start from beginning
                    if self._load_current_file():
                        self.player.paused_position = 0
                        self._update_display()
                        self.logger.log_channel("LOADED", channel_name, "from beginning (index 0)")
                    else:
                        self.logger.log_error(f"Failed to load first file in channel: {channel_name}")
                else:
                    self.logger.log_error(f"No folders in channel: {channel_name}")
            else:
                # Load channel from saved position
                self._load_current_channel()
            
            self._update_title()
            msg = f"Channel: {channel_name}"
            self.status_label.SetLabel(f"Switched to channel: {channel_name}")
            self._answer_in_samantha_voice(msg)
        self.timer.Start(100)
    
    def _on_timer(self, event):
        """Timer callback for position updates and auto-advance"""
        try:
            if self.player.is_playing:
                pos = self.player.get_position()
                if pos >= 0:  # Valid position
                    minutes = int(pos // 60)
                    seconds = int(pos % 60)
                    self.position_label.SetLabel(f"{minutes}:{seconds:02d}")
                    # Auto-resume: save the position every time it
                    # changes — once per second while playing, and
                    # immediately after a seek (the position jumps),
                    # so a crash or power loss loses nothing.
                    sec = int(pos)
                    if sec != getattr(self, "_auto_save_last_sec", None):
                        self._auto_save_last_sec = sec
                        try:
                            self._save_current_channel_state(quiet=True)
                        except Exception:
                            pass
                
                # Auto-advance to next file when current finishes.
                # Ashley, 2026-11-27: play the whole series, then
                # the next channel, and so on — and do NOT wait
                # for quiet moments. There is NO quiet-tick
                # counting here at all: no 1-tick and no 3-tick
                # check, nothing that guesses "finished" from the
                # mixer being quiet for a moment. A file only
                # advances when the audio engine itself says it
                # really ended, in one of two ways:
                #   1. The end-of-file signal: the stream posts
                #      it when a track finishes (see AudioPlayer.
                #      music_ended()). A momentary dropout
                #      or a quiet passage mid-file never posts
                #      it, so it can never cut a show off early.
                #   2. Backup, only if the end signal never
                #      arrives: the engine says the music is not
                #      playing at all (position -1) AND nothing
                #      is busy AND we were well into
                #      the file (past 5 seconds in). The first
                #      moments after pressing play can never
                #      look like an ending, and a single
                #      not-busy tick on its own never advances
                #      anything — it needs the position to say
                #      the music stopped too.
                # If neither says the file ended, the show just
                # keeps playing — even if the mixer goes quiet
                # for a moment. That is the safe failure: never
                # jump ahead, never stop in the middle.
                try:
                    _current = self.playlist.get_current()
                except Exception:
                    _current = None
                if _current != getattr(self, "_timer_playing_file", None):
                    self._timer_playing_file = _current
                    self._last_music_pos_s = 0
                try:
                    _busy_now = bool(self.player.is_busy())
                except Exception:
                    _busy_now = True
                if _busy_now and pos and pos > 0:
                    self._last_music_pos_s = pos
                _ended = False
                _music_ended = getattr(self.player, "music_ended", None)
                if callable(_music_ended):
                    try:
                        _ended = bool(_music_ended())
                    except Exception:
                        _ended = False
                if not _ended:
                    _raw_pos = None
                    _music_pos = getattr(
                        self.player, "music_position_ms", None)
                    if callable(_music_pos):
                        try:
                            _raw_pos = _music_pos()
                        except Exception:
                            _raw_pos = None
                    _ended = (_raw_pos == -1 and not _busy_now
                              and getattr(self, "_last_music_pos_s", 0) > 5)
                if _ended:
                    current_file = self.playlist.get_current_file_name()
                    current_folder = self.playlist.get_current_folder_name()
                    
                    if self.playlist.next_file():
                        # Successfully moved to next file
                        next_file = self.playlist.get_current_file_name()
                        next_folder = self.playlist.get_current_folder_name()
                        
                        self.logger.log_auto_advance(
                            f"{current_folder}/{current_file}",
                            f"{next_folder}/{next_file}",
                            "File finished"
                        )
                        
                        self._load_current_file()
                        self.player.play()
                        # The new file is playing: forget the old
                        # file's position, so the backup end
                        # check (past 5 seconds in) can never
                        # fire on a file that only just started.
                        self._last_music_pos_s = 0
                        try:
                            self._timer_playing_file = \
                                self.playlist.get_current()
                        except Exception:
                            pass
                        # Say this show's own name when the next file in
                        # the same channel starts, too — in plain words,
                        # not the file name: no ".mp3", no S01E02 code,
                        # and the show name once, not once for the
                        # channel and once for the file.
                        channel_name = self.channels.current_channel or ""
                        now_file = self.playlist.get_current_file_name()
                        # Ashley, 2026-11-27, smoother TV guide:
                        # one flowing announcement, not three
                        # separate bits with gaps between them —
                        # what is playing, the marathon, then
                        # what comes up next, all in one breath.
                        msg = self._smooth_advance_text(
                            now_file, channel_name)
                        self.status_label.SetLabel(msg)
                        speak(msg)
                        self._save_current_channel_state()
                    else:
                        # No more files in current channel
                        # Prevent multiple simultaneous channel switches
                        if self.is_switching_channels:
                            return
                        
                        self.is_switching_channels = True
                        self.player.is_playing = False
                        
                        self.logger.log_auto_advance(
                            f"{current_folder}/{current_file}",
                            "End of channel",
                            "Channel finished, attempting next channel"
                        )
                        
                        # Peek at next channel name
                        channel_list = sorted(self.channels.channels.keys())
                        current_idx = channel_list.index(self.channels.current_channel) if self.channels.current_channel in channel_list else -1
                        next_idx = (current_idx + 1) % len(channel_list)
                        next_name = channel_list[next_idx]
                        msg = f"Channel finished. Coming up next: {next_name}"
                        self.status_label.SetLabel(msg)
                        speak(msg)
                        
                        # Save current channel state, then switch
                        self._save_current_channel_state()
                        
                        # Use delayed call to switch and play
                        wx.CallLater(500, self._auto_advance_to_next_channel)
        except Exception as e:
            self.logger.log_error(f"Timer error: {e}")
            self.status_label.SetLabel(f"Playback error: {e}")
    
    def _on_set_bookmark(self, event):
        """Set a bookmark at current position"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        if not self.playlist.get_current():
            wx.MessageBox("No file is loaded", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        # Check if at bookmark limit
        bookmarks = self.channels.get_bookmarks()
        if len(bookmarks) >= 20:
            # Ask if they want to overwrite
            dlg = wx.SingleChoiceDialog(
                self, 
                "Bookmark limit reached (20). Select a bookmark to overwrite or cancel:", 
                "Overwrite Bookmark", 
                sorted(bookmarks.keys())
            )
            if dlg.ShowModal() == wx.ID_OK:
                bookmark_name = dlg.GetStringSelection()
                dlg.Destroy()
            else:
                dlg.Destroy()
                return
        else:
            # Ask for new bookmark name
            dlg = wx.TextEntryDialog(self, "Enter bookmark name:", "Set Bookmark")
            if dlg.ShowModal() == wx.ID_OK:
                bookmark_name = dlg.GetValue().strip()
                dlg.Destroy()
                
                if not bookmark_name:
                    return
                
                # Check if bookmark exists, ask to overwrite
                if bookmark_name in bookmarks:
                    result = wx.MessageBox(
                        f"Bookmark '{bookmark_name}' already exists. Overwrite?", 
                        "Confirm Overwrite", 
                        wx.YES_NO | wx.ICON_QUESTION
                    )
                    if result != wx.YES:
                        return
            else:
                dlg.Destroy()
                return
        
        # Save bookmark
        current_index = self.playlist.current_index
        current_position = self.player.get_position()
        
        if self.channels.add_bookmark(bookmark_name, current_index, current_position):
            file_name = self.playlist.get_current_file_name()
            folder_name = self.playlist.get_current_folder_name()
            self.logger.log_bookmark("SET", bookmark_name, f"{folder_name}/{file_name} at {current_position:.1f}s")
            msg = f"Bookmark '{bookmark_name}' saved"
            self.status_label.SetLabel(msg)
            speak(msg)
        else:
            wx.MessageBox("Failed to save bookmark", "Error", wx.OK | wx.ICON_ERROR)
    
    def _on_jump_bookmark(self, event):
        """Jump to a saved bookmark"""
        if not self.channels.current_channel:
            wx.MessageBox("No channel selected", "Error", wx.OK | wx.ICON_ERROR)
            return
        
        bookmarks = self.channels.get_bookmarks()

        # Auto-resume: the channel's own saved position (kept updated
        # automatically while playing) shows up first, so there is
        # always a "go back to where I left off" entry.
        auto_entry = None
        auto_index = 0
        auto_position = 0.0
        channel_data = self.channels.get_current_channel_data()
        if channel_data:
            try:
                auto_index = int(channel_data.get('current_index', 0) or 0)
            except Exception:
                auto_index = 0
            try:
                auto_position = float(channel_data.get('position', 0) or 0)
            except Exception:
                auto_position = 0.0
            if (auto_index > 0 or auto_position > 0) and \
                    0 <= auto_index < len(self.playlist.playlist):
                file_name = Path(self.playlist.playlist[auto_index][1]).name
                minutes = int(auto_position // 60)
                seconds = int(auto_position % 60)
                auto_entry = f"Auto-resume (last saved) - {file_name} ({minutes}:{seconds:02d})"

        if not bookmarks and not auto_entry:
            msg = "No bookmarks in this channel"
            wx.MessageBox(msg, "No Bookmarks", wx.OK | wx.ICON_INFORMATION)
            speak(msg)
            return
        
        # Create list with bookmark info
        bookmark_list = []
        if auto_entry:
            bookmark_list.append(auto_entry)
        for name in sorted(bookmarks.keys()):
            bm = bookmarks[name]
            # Get file name if possible
            if bm['index'] < len(self.playlist.playlist):
                file_path = self.playlist.playlist[bm['index']][1]
                file_name = Path(file_path).name
                minutes = int(bm['position'] // 60)
                seconds = int(bm['position'] % 60)
                bookmark_list.append(f"{name} - {file_name} ({minutes}:{seconds:02d})")
            else:
                bookmark_list.append(f"{name} - (file not found)")
        
        # Show dialog with delete option
        dlg = wx.SingleChoiceDialog(self, "Select bookmark to jump to:", "Bookmarks", bookmark_list)
        
        if dlg.ShowModal() == wx.ID_OK:
            selection_index = dlg.GetSelection()
            dlg.Destroy()

            if auto_entry and selection_index == 0:
                # Auto-resume: jump only (it is the channel's saved
                # position, not a named bookmark, so there is nothing
                # to delete).
                result = wx.MessageBox(
                    "Jump to your last saved position?",
                    "Auto-Resume",
                    wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
                )
                if result == wx.YES:
                    was_playing = self.player.is_playing
                    self.player.stop()
                    self.player.is_playing = False

                    if len(self.playlist.playlist) > 0:
                        idx = max(0, min(auto_index, len(self.playlist.playlist) - 1))
                        if self.playlist.set_index(idx):
                            self._load_current_file()
                            self.player.paused_position = auto_position
                            self._update_display()

                            if was_playing:
                                self.player.unpause()

                            file_name = self.playlist.get_current_file_name()
                            folder_name = self.playlist.get_current_folder_name()
                            self.logger.log_bookmark("JUMP", "auto-resume", f"to {folder_name}/{file_name}")

                            msg = "Jumped to your last saved position"
                            self.status_label.SetLabel(msg)
                            speak(msg)
                        else:
                            wx.MessageBox("Saved file no longer exists", "Error", wx.OK | wx.ICON_ERROR)
                return

            selected_name = sorted(bookmarks.keys())[selection_index - (1 if auto_entry else 0)]
            
            # Ask if they want to jump or delete
            result = wx.MessageBox(
                f"Jump to '{selected_name}'?\n\nClick 'No' to delete this bookmark instead.", 
                "Jump to Bookmark", 
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
            )
            
            if result == wx.YES:
                # Jump to bookmark
                bookmark = self.channels.get_bookmark(selected_name)
                if bookmark:
                    was_playing = self.player.is_playing
                    self.player.stop()
                    self.player.is_playing = False
                    
                    if self.playlist.set_index(bookmark['index']):
                        self._load_current_file()
                        self.player.paused_position = bookmark['position']
                        self._update_display()
                        
                        if was_playing:
                            self.player.unpause()
                        
                        file_name = self.playlist.get_current_file_name()
                        folder_name = self.playlist.get_current_folder_name()
                        self.logger.log_bookmark("JUMP", selected_name, f"to {folder_name}/{file_name}")
                        
                        msg = f"Jumped to bookmark: {selected_name}"
                        self.status_label.SetLabel(msg)
                        speak(msg)
                    else:
                        wx.MessageBox("Bookmark file no longer exists", "Error", wx.OK | wx.ICON_ERROR)
            elif result == wx.NO:
                # Delete bookmark
                if self.channels.delete_bookmark(selected_name):
                    self.logger.log_bookmark("DELETE", selected_name)
                    msg = f"Deleted bookmark: {selected_name}"
                    self.status_label.SetLabel(msg)
                    speak(msg)
        else:
            dlg.Destroy()
    
    def _toggle_voice_listening(self):
        """Toggle voice control listening"""
        if not self.voice_available:
            # Ashley, 2026-11-27: pressing Ctrl+Shift+B when
            # listening is not available used to answer only
            # with speak() — NVDA — which is silent while NVDA
            # quiet is on, so she heard nothing at all. First
            # try to create voice control now (the model may
            # have appeared since startup); if that works,
            # carry on and listen. Otherwise say so in
            # Samantha's own voice (see
            # _say_listening_not_ready), never NVDA.
            if self._try_create_voice_control():
                pass
            else:
                self._say_listening_not_ready(force=True)
                return
        
        if self.is_voice_listening:
            # Ashley, 2026-11-27: Ctrl+Shift+B "does not seem
            # to be working". One reason: pressing it a second
            # time — for example because she heard nothing
            # after the first press — used to STOP listening,
            # so the press that was meant as "try again"
            # switched it off instead. The window is only 20
            # seconds and ends by itself, so a second press
            # now just says so, in Samantha's own voice, and
            # keeps the window running. There is no need for
            # a stop key: one press, one turn, then it stops
            # on its own.
            self._answer_in_samantha_voice(
                "I'm already listening. Go ahead.",
                "samantha_im_on_it.wav")
            return
        else:
            # Start listening in a separate thread
            # Honey, 2026-11-23 evening: Samantha says "I'm listening"
            # when she starts listening, so Honey knows she is ready.
            # Ashley, 2026-11-26: high chime, then the low chime
            # 2 seconds later, and she still has 20 seconds to speak.
            # Ashley, 2026-11-27: press-to-talk only. This is ONE
            # listening turn: when it ends (command heard, or
            # silence), listening stops and does NOT start again
            # by itself. She presses Ctrl+Shift+B again for the
            # next command. _want_continuous stays False.
            self._want_continuous = False
            self._start_listening(chimes=True)
    
    def _start_listening(self, chimes=True):
        """Start one-time listening (20 seconds) in a thread.

        Press-to-talk only, Ashley 2026-11-27: this runs only
        because she pressed Ctrl+Shift+B. When the turn ends,
        listening stops and never restarts itself (see
        _rearm_listening, which now does nothing).
        chimes=True rings the high-then-low wake chimes, for
        that fresh press.
        """
        self.is_voice_listening = True
        if chimes:
            self._play_wake_chimes()
        msg = "I'm listening"
        self.status_label.SetLabel(msg)
        # Ashley, 2026-11-27: Ctrl+Shift+B "does not seem to
        # be working". This used to say "I'm listening" with
        # speak() — NVDA — which is silent while NVDA quiet
        # is on, so after pressing B she heard only the
        # chimes and nothing telling her listening had
        # started. Now Samantha says it herself, in her own
        # voice (reading voice when ready, "I'm on it" clip
        # when not). The chimes still ring first.
        self._answer_in_samantha_voice(msg)
        # Ashley, 2026-11-27: the listen thread used to start
        # in the same breath as the chimes, so the first ~6
        # seconds of her 20-second window were spent with
        # the high chime (4.6 s) and low chime (1.6 s)
        # ringing into the microphone — and she speaks
        # slowly, so a slow answer could run out of window.
        # Now the microphone opens only once the chimes have
        # actually finished, and she gets the full 20
        # seconds from then. _begin_listen_thread checks
        # she is still listening before starting.
        if chimes:
            try:
                ms = (self._clip_ms(
                    Path(__file__).parent / "sounds"
                    / "start_of_request.wav")
                    + self._clip_ms(
                        Path(__file__).parent / "sounds"
                        / "end_of_request.wav") + 300)
            except Exception:
                ms = 6500
            wx.CallLater(ms, self._begin_listen_thread)
        else:
            self._begin_listen_thread()

    def _begin_listen_thread(self, _waited_ms=0):
        """Open the microphone for a press-to-talk turn.

        Only runs when a turn is still wanted (she has not
        pressed anything else since). Separated from
        _start_listening so the thread starts after the
        wake chimes finish, not during them.
        Ashley, 2026-11-27: also wait until Samantha herself
        is quiet — her "I'm listening" reading, or a clip
        still playing — before opening the microphone. The
        old code opened it on a fixed timer, so it could
        open while she was still speaking and hear her own
        voice as a command ("I'm listening" heard back as
        words she never said, then "Excuse me"). Waits up
        to 15 seconds, then opens anyway, so a stuck flag
        can never leave her with no listening at all.
        """
        if not getattr(self, "is_voice_listening", False):
            return
        _busy = bool(getattr(self, "_samantha_reading", False))
        if not _busy:
            _busy = self._samantha_busy()
        if _busy and _waited_ms < 15000:
            wx.CallLater(500, self._begin_listen_thread,
                         _waited_ms + 500)
            return
        thread = threading.Thread(target=self._voice_listen_thread, daemon=True)
        thread.start()
    
    def _rearm_listening(self):
        """Press-to-talk only (Ashley, 2026-11-27): this does
        nothing now, on purpose.

        It used to listen again by itself after a command —
        8 seconds later, with no button press and no wake
        word, even while a show was playing. Words from the
        show itself were then heard as commands, and a
        "stop" / "pause" / "play" in the dialogue paused the
        show in the middle. That is also why Samantha kept
        answering words nobody said to her. Now, after a
        command (or silence), listening stops and stays
        stopped until Ashley presses Ctrl+Shift+B again for
        the next command. Ctrl+Shift+W is the only
        always-listening mode, and only she turns it on.
        Kept as a method so any already-scheduled call to
        it is harmless.
        """
        return
    
    def _voice_listen_thread(self):
        """Thread for voice listening"""
        try:
            # Honey asked for more time to speak: 20 seconds, up from 10.
            text = self.voice.listen(
                duration=getattr(self.voice, "ONE_TIME_LISTEN_SECONDS", 20))
            
            # Play end sound, once only (see _play_end_chime)
            wx.CallAfter(self._play_end_chime)

            if not text:
                # The microphone stream itself failed (see
                # voice_control.listen, which records it in
                # voice.last_error): say so as a voice error
                # in Samantha's voice, with the plain reason,
                # instead of "Excuse me" as if she had simply
                # not spoken. Silence (no speech) has no
                # last_error, so it still goes to
                # _voice_no_command below.
                last_error = getattr(self.voice, "last_error", None)
                if last_error:
                    try:
                        self.voice.last_error = None
                    except Exception:
                        pass
                    wx.CallAfter(
                        self._voice_error,
                        "the microphone could not be opened: "
                        + str(last_error)[:200])
                    return

            if text:
                # A command was heard. Press-to-talk only
                # (Ashley, 2026-11-27): listening ends here.
                # It used to re-arm itself 8 seconds later
                # with no press, and then hear the show as a
                # command and pause it. No re-arm now — she
                # presses Ctrl+Shift+B again for the next
                # command, or uses Ctrl+Shift+W wake-word
                # mode if she wants always-listening.
                # Parse command
                command = self.voice.parse_command(text)
                
                # Execute command on main thread
                wx.CallAfter(self._execute_voice_command, command, text)
            else:
                wx.CallAfter(self._voice_no_command)
        except Exception as e:
            wx.CallAfter(self._voice_error, str(e))
        finally:
            self.is_voice_listening = False
            # NOTE: do NOT clear _wake_chimes_played here. This
            # finally runs in the listening thread, and the
            # end chime is queued to the main thread with
            # CallAfter — if the flag were cleared here first,
            # the end chime would think the chimes never played
            # and ring the low chime a second time. _play_end_chime
            # (on the main thread) owns clearing the flag.
    
    def _on_command_box_enter(self, event):
        """Enter pressed in the Type to Samantha box.

        Ashley, 2026-11-26: "I want her to respond when
        whenever I press enter." Runs the typed text as a
        command, exactly like a spoken one, and Samantha
        answers in her own voice. Enter is also caught by
        _on_command_box_key (below): some setups swallow the
        text-enter event, so the key handler is the belt to
        this one's braces. Either way the command runs once:
        the box is cleared before it runs, and a repeat of the
        same words within a second is ignored. The box keeps
        focus after Enter, so she can type the next command
        straight away.
        """
        text = self.command_box.GetValue().strip()
        if not text:
            return
        if (getattr(self, "_last_typed_command", None) == text
                and time.time() - getattr(
                    self, "_last_typed_command_at", 0) < 1.0):
            return
        self._last_typed_command = text
        self._last_typed_command_at = time.time()
        self.command_box.SetValue("")
        self.status_label.SetLabel(f"You typed: {text}")
        self._run_typed_command(text)
        # Ashley, 2026-11-27: the box keeps focus after Enter,
        # so she can type the next command straight away without
        # having to find the box again. Focus is returned here,
        # after the command runs — and _enable_nvda_quiet never
        # steals it in the first place (it only Raises the
        # window, never SetFocus). Guarded: a box that cannot
        # take focus must not break the command that just ran.
        try:
            self.command_box.SetFocus()
        except Exception:
            pass

    def _on_command_box_key(self, event):
        """Enter pressed in the Type to Samantha box (key event).

        EVT_TEXT_ENTER is the normal path, but if Enter never
        produces one — the frame's EVT_CHAR_HOOK, NVDA, or the
        control itself can swallow it — this catches the key
        itself, runs the command, and does not pass the key on,
        so the text-enter event cannot run it a second time.
        Every other key is passed on, so typing, Space, and the
        arrow keys still work in the box.
        """
        keycode = event.GetKeyCode()
        if keycode in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_command_box_enter(event)
            return
        event.Skip()

    def _run_typed_command(self, text):
        """Run a typed command through the same path as voice.

        Uses the same parse_command and _execute_voice_command
        as a spoken command, so typing "play Friends" or "list
        shows" does exactly what saying it does. Works even
        when the voice recogniser is not available (no Vosk
        model): parsing is pure text, so a bare parser is built
        for the purpose instead of failing. If anything in the
        command fails, Samantha says so in her own voice
        instead of the box going silent.
        """
        try:
            parser = self.voice
            if parser is None:
                try:
                    parser = VoiceControl()
                except Exception:
                    # No model: parsing needs no model, only the
                    # word lists, so build a bare parser with
                    # every attribute __init__ sets, so parsing
                    # can never fail on a missing attribute.
                    import queue
                    parser = VoiceControl.__new__(VoiceControl)
                    parser.model_path = Path("vosk-model-small-en-us-0.15")
                    parser.model = None
                    parser.recognizer = None
                    parser.is_listening = False
                    parser.wake_word_active = False
                    parser.audio_queue = queue.Queue()
                    parser.wake_word = "samantha"
                    parser.wake_words = ("samantha", "sammy", "sam",
                                         "guide", "metro")
            command = parser.parse_command(text)
            self._execute_voice_command(command, text)
        except Exception as e:
            try:
                self.logger.log_error(f"TYPED COMMAND: {text!r} - {e}")
            except Exception:
                pass
            self._answer_in_samantha_voice(
                "Sorry, that didn't work. Could you say that again?",
                "samantha_excuse_me.wav")

    def _execute_voice_command(self, command, text):
        """Execute a voice command.

        Ashley, 2026-11-26: "have her say I'm on it." When she
        asks Samantha to do work — search, download, play a
        channel, list shows, read the guide — Samantha answers
        "I'm on it" in her own recorded voice
        (sounds/samantha_im_on_it.wav) right away, so Ashley
        knows she was heard and is working on it. The answer
        itself waits until "I'm on it" has finished: the old
        code played it and ran the command in the same breath,
        so the answer talked over it. Quick replies (how she
        is doing, "can you hear me", her name, play/pause,
        skipping) answer directly instead and do not get an
        extra "I'm on it" first. A newer command replaces a
        still-waiting one — she only ever hears the latest
        answer.
        """
        name = command[0] if isinstance(command, tuple) else command
        if name in _WORK_COMMANDS:
            pending = getattr(self, "_pending_voice_command_timer", None)
            if pending is not None:
                try:
                    pending.Stop()
                except Exception:
                    pass
            ms = self._play_sound_effect("samantha_im_on_it.wav")
            self._pending_voice_command_timer = wx.CallLater(
                ms + 200, self._execute_voice_command_now, command, text)
            return
        self._execute_voice_command_now(command, text)

    def _execute_voice_command_now(self, command, text):
        """Run a voice command (after "I'm on it", if there was one)."""
        self._pending_voice_command_timer = None
        # Handle tuple commands (command, argument)
        query = None
        if isinstance(command, tuple):
            command, query = command

        if command == 'set_name':
            # Honey, 2026-11-23: Samantha learns her name when Honey
            # tells it to her by voice, and remembers it in config.ini
            # (local only, never pushed to GitHub) via _set_user_name.
            if query:
                self._set_user_name(query)
                msg = f"Got it, {query}. I'll remember your name is {query}."
            else:
                msg = "I didn't hear a name. Tell me, say my name is Honey."
        elif command == 'what_is_my_name':
            name = self._get_user_name()
            if name:
                msg = f"Your name is {name}, and I remember it."
            else:
                msg = ("I don't know your name yet. Tell me, "
                       "say my name is Honey.")
        elif command == 'forget_name':
            self._set_user_name("")
            msg = ("Okay, I've forgotten your name. Tell me again any "
                   "time, just say my name is Honey.")
        elif command == 'what_is_your_name':
            # Ashley, 2026-11-26: her full name is Samantha
            # Hernandez Right — first Samantha, middle Hernandez,
            # last Right. She is still called Samantha.
            # Samantha says it in her own recorded voice
            # (sounds/samantha_my_name_is.wav), and NVDA does
            # not repeat it, so Ashley only hears Samantha.
            self._play_sound_effect("samantha_my_name_is.wav")
            msg = ("My name is Samantha Hernandez Right. "
                   "I'm your voice helper for Audio Vault TV.")
            self.status_label.SetLabel(msg)
            return
        elif command == 'greet':
            name = self._get_user_name()
            if name:
                # Samantha asks, in her own recorded voice, what
                # Honey wants to watch. NVDA does not repeat it.
                self._play_sound_effect("samantha_how_are_you_doing.wav")
                msg = f"Hi {name}! I'm Samantha Hernandez Right. I'm listening."
            else:
                self._play_sound_effect("samantha_my_name_is.wav")
                msg = ("Hi! I'm Samantha Hernandez Right. I'm listening. "
                       "Tell me your name any time, just say my name is Honey.")
            self.status_label.SetLabel(msg)
            return
        elif command == 'feeling_good':
            # Ashley, 2026-11-26: Samantha asks "How are you
            # doing?" in the greeting, and Ashley answers
            # "I am good". Samantha answers in her own recorded
            # voice — samantha_glad_youre_good.wav, Caitlin —
            # and NVDA does not repeat it. Then, without Ashley
            # having to ask, she reads the list of channels
            # Ashley has, and what comes up next in the TV
            # guide, so Ashley can tell her which channel she
            # wants to watch. The list and the guide are read
            # after the recorded reply finishes (about 6 sec),
            # in the app's usual speaking voice, because
            # Samantha's voice is recordings and cannot read
            # channel names she never recorded — the same
            # pattern as the TV guide in _speak_tv_guide.
            # The startup list is read here instead (list and
            # guide together), so the pending startup list is
            # cleared and _voice_no_command will not read it
            # a second time.
            self._startup_list_pending = False
            glad_ms = self._play_sound_effect("samantha_glad_youre_good.wav")
            msg = ("That's wonderful! I'm so glad you're doing "
                   "good. What do you want to watch?")
            self.status_label.SetLabel(msg)
            wx.CallLater(glad_ms + 300, self._speak_channels_and_guide)
            return
        elif command == 'can_you_hear_me':
            # Ashley, 2026-11-26: when she asks "can you hear
            # me", Samantha answers in her own recorded voice:
            # "Yes, I can hear you." (sounds/samantha_yes_i_can.wav)
            # NVDA does not repeat it.
            # Ashley, 2026-11-27: that answer was a lie when
            # listening was not available at all — the reading
            # voice being ready does not mean she can hear.
            # Only say "Yes, I can" when voice_available is
            # really True; otherwise say she cannot hear yet
            # and why, in her own voice (see
            # _say_listening_not_ready).
            if self.voice_available:
                self._play_sound_effect("samantha_yes_i_can.wav")
                msg = "Yes, I can hear you."
                self.status_label.SetLabel(msg)
            else:
                self._say_listening_not_ready(force=True)
            return
        elif command == 'listening_status':
            # Ashley, 2026-11-27: "why can't you hear me" —
            # Samantha tells her whether she can hear, and if
            # not, why (model installing / missing / failed),
            # in her own voice. Only "Yes, I can hear you"
            # when listening is actually available.
            self._say_listening_status()
            return
        elif command == 'install_listening_model':
            # Ashley, 2026-11-27: "install the listening model"
            # / "get Samantha listening" — the checkable step
            # for listening, like "install my reading voice"
            # is for the reading voice (see
            # _on_install_listening_model).
            self._on_install_listening_model()
            return
        elif command == 'install_reading_voice':
            # Ashley, 2026-11-26: "install my reading voice" —
            # the checkable step for Samantha's reading voice.
            # Samantha says "I'm on it", the install runs in
            # the background, and she says when it is ready
            # (see _on_install_reading_voice).
            self._on_install_reading_voice()
            return
        elif command == 'install_requirements':
            # Ashley, 2026-11-27: "install everything I need"
            # — get every library the app needs, not just the
            # reading voice, so nothing needs Command Prompt.
            # Samantha says "I'm on it", the installs run in
            # the background one at a time, and she says when
            # it is all ready (see _on_install_requirements).
            self._on_install_requirements()
            return
        elif command == 'reading_voice_status':
            # Ashley, 2026-11-27: "why is my reading voice not
            # ready" / "what happened to my reading voice" —
            # Samantha tells her the last install reason and
            # state, in her own voice, so nobody has to guess
            # next time (see _say_reading_voice_status).
            self._say_reading_voice_status()
            return
        elif command == 'list_channels':
            # "Samantha, list all the channels I have" — read
            # them out, without opening the channel picker.
            # Heard even with NVDA quiet on (see _speak_and_requiet).
            self._speak_and_requiet(self._speak_channel_list)
            return
        elif command == 'list_shows':
            # Ashley, 2026-11-26: "What are my options?" /
            # "tell me the list of shows I have so I can
            # choose a channel". Samantha reads the shows,
            # so Ashley can pick one by name. Heard even with
            # NVDA quiet on (see _speak_and_requiet).
            self._speak_and_requiet(self._speak_show_list)
            return
        elif command == 'play_live_tv':
            # "Samantha, play live TV" - a favourite live channel
            # first, otherwise the first live channel.
            self._livetv_voice_play(None)
            return
        elif command == 'play_live_channel':
            # "Samantha, play Game Show Network live" - and any
            # other live channel by name.
            self._livetv_voice_play(query)
            return
        elif command == 'search_live_channels':
            self._livetv_voice_search(query)
            return
        elif command == 'stop_live_tv':
            self._on_livetv_stop()
            return
        elif command == 'whats_next':
            # "Samantha, what's coming up next?" / "give me the
            # TV guide" - Samantha reads the whole guide.
            self._speak_tv_guide()
            return
        elif command == 'livetv_guide':
            # "Samantha, what's coming up next on Game Show
            # Network?" - a guide for that live channel.
            self._speak_livetv_guide(query)
            return
        elif command == 'fix_mixed_channels':
            self._fix_mixed_channels()
            return
        elif command == 'delete_channel_downloads':
            # "Samantha, delete the show" / "delete A Killer Among
            # Friends downloads" - deletes right away when she
            # tells it to, then speaks what was removed.
            self._delete_channel_downloads(query, confirm=False)
            return
        elif command == 'play_channel':
            # Ashley, 2026-11-26: after Samantha reads the list
            # of shows, Ashley picks one by name — "play
            # Friends", "watch Classic Doctor Who". _find_local_
            # channel matches exact, then starts-with, then
            # contains, so "friends" finds the Friends channel.
            # She also asked: "when I choose one, I want her to
            # tell me if I have it or not." So the answer says
            # plainly whether she has it. And it is read through
            # _speak_and_requiet, not plain speak(): with NVDA
            # quiet on, plain speak() is silent, so she would
            # otherwise hear nothing at all when she picks one.
            found = self._find_local_channel(query)
            if found:
                self._switch_to_channel(found)
                if self.playlist.get_current():
                    self.player.play()
                    # The channel name, then the episode in plain
                    # words — not the channel name twice in a row,
                    # and never the file name with ".mp3" in it.
                    msg = ("You have " + found + ". Now playing: "
                           + self._spoken_episode(
                               self.playlist.get_current_file_name(),
                               found) + ".")
                else:
                    msg = f"You have {found}, but there is nothing to play."
            else:
                msg = (f"You don't have a channel called {query}, "
                       "so I didn't change anything.")
            self.status_label.SetLabel(msg)
            self._speak_and_requiet(
                lambda: self._say_in_samantha_voice(msg))
            return
        elif command == 'play_pause':
            # The helper announces itself in Samantha's voice
            # now (see _toggle_play_pause) — no extra "Command
            # recognized" over it.
            self._toggle_play_pause()
            return
        elif command == 'next_file':
            self._next_file()
            return
        elif command == 'prev_file':
            self._prev_file()
            return
        elif command == 'next_folder':
            self._next_folder()
            return
        elif command == 'prev_folder':
            self._prev_folder()
            return
        elif command == 'next_channel':
            self._next_channel()
            return
        elif command == 'prev_channel':
            self._prev_channel()
            return
        elif command == 'rewind':
            self._rewind()
            return
        elif command == 'fastforward':
            self._fastforward()
            return
        elif command == 'search_movies':
            # Honey, 2026-11-23 evening: "search for Young Sheldon
            # and that is it" - a voice search downloads the show
            # right after it searches, so she does not have to say
            # "download it" again. No name needed in one-time mode.
            if query:
                self._vault_voice_download(query, "movies")
            else:
                self._on_vault_search(None, kind="movies")
            # The downloading clip (or the search results) speaks
            # for itself — no extra "Command recognized" over it.
            return
        elif command == 'search_shows':
            # Honey, 2026-11-23 evening: same as movies above.
            # "search for Young Sheldon" searches AudioVault for
            # the exact show and downloads it in the background.
            if query:
                self._vault_voice_download(query, "shows")
            else:
                self._on_vault_search(None, kind="shows")
            # The downloading clip (or the search results) speaks
            # for itself — no extra "Command recognized" over it.
            return
        elif command in ('download_shows', 'download_movies'):
            # "Samantha, download Close Enough" — search AudioVault for the
            # named show/movie and download the top result, with no
            # checklist to pick from by hand.
            kind = 'shows' if command == 'download_shows' else 'movies'
            if query:
                self._vault_voice_download(query, kind)
            else:
                self._on_vault_recents(None, kind="movies")
            # The downloading clip speaks for itself — no extra
            # "Command recognized" over it.
            return
        elif command == 'search_youtube':
            if query:
                self._yt_voice_search(query)
            else:
                self._on_yt_search(None)
            # _yt_voice_search already answers in Samantha's
            # voice — no extra "Command recognized" over it.
            return
        elif command == 'download_youtube':
            # "Samantha, download Close Enough from YouTube" — search
            # YouTube for the named video and download the top
            # result in the background, with no checklist to pick
            # from by hand. Honey asked for this 2026-11-23.
            if query:
                self._yt_voice_download(query)
            else:
                self._on_yt_search(None)
            # The downloading clip speaks for itself — no extra
            # "Command recognized" over it.
            return
        elif command == 'download_first':
            # "Samantha, download it" after a voice search: download the
            # first result from that search. _vault_voice_download_first
            # speaks the result itself, so return here like
            # download_status does.
            self._vault_voice_download_first()
            return
        elif command == 'cancel_downloads':
            self._on_cancel_downloads()
            return
        elif command == 'download_status':
            # _on_download_status already speaks the status; return here
            # so the generic "Command recognized" message does not talk
            # over it or replace it in the status line.
            self._on_download_status()
            return
        elif command == 'download':
            self._on_vault_recents(None, kind="movies")
            # The recents list speaks for itself — no extra
            # "Command recognized" over it.
            return
        else:
            # Honey, 2026-11-23 evening: if Samantha heard words
            # but did not understand them, she says "Excuse me"
            # and asks Honey to say it again. In her own voice:
            # the old fall-through answered with speak(), which
            # is NVDA and silent while NVDA quiet is on, so a
            # typed command she did not understand was met with
            # silence.
            # Ashley, 2026-11-27: "Excuse me" used to say
            # nothing about what she actually heard, so she
            # had no way to know what went wrong. Now Samantha
            # says the words she heard, and gives one example
            # of what to say — in her own voice, never NVDA,
            # never Microsoft. This only runs when words were
            # really heard but matched no command; silence
            # goes to _voice_no_command instead, so "Excuse
            # me, I didn't understand" is never said for
            # nothing at all.
            # Ashley, 2026-11-28: after the list she says the
            # show she wants — "Doctor Who", "I want Friends" —
            # without the word "play", which matches no command
            # and reaches here. Match it against her channels
            # the same way play_channel does (exact, then
            # starts-with, then fuzzy), and play it, instead
            # of "Excuse me".
            import re
            intent = re.compile(
                r"^(?:i want|i would like|i'd like|i am going to watch"
                r"|i'm going to watch|i want to (?:watch|play)|let's watch"
                r"|lets watch|i'll watch|can you play (?:me )?watch)\s+")
            candidate = str(text).strip().lower()
            said_intent = bool(intent.match(candidate))
            candidate = intent.sub("", candidate)
            found = (self._find_local_channel(candidate)
                     if len(candidate) >= 3 else None)
            if (found is None and said_intent
                    and len(candidate.split()) <= 4):
                # She named a specific show she does not have —
                # say so plainly, the same way "play X" does.
                msg = (f"You don't have a channel called {candidate}, "
                       "so I didn't change anything.")
                self.status_label.SetLabel(msg)
                self._speak_and_requiet(
                    lambda: self._say_in_samantha_voice(msg))
                return
            if found:
                self._switch_to_channel(found)
                if self.playlist.get_current():
                    self.player.play()
                    msg = ("You have " + found + ". Now playing: "
                           + self._spoken_episode(
                               self.playlist.get_current_file_name(),
                               found) + ".")
                else:
                    msg = (f"You have {found}, but there is "
                           "nothing to play.")
                self.status_label.SetLabel(msg)
                self._speak_and_requiet(
                    lambda: self._say_in_samantha_voice(msg))
                return
            msg = (f"Excuse me, I didn't understand {text}. "
                   "I heard " + str(text) + ". "
                   "Try saying, list shows, or play Doctor Who.")
            self._answer_in_samantha_voice(
                msg, "samantha_excuse_me.wav")
            return

        # Ashley, 2026-11-26: every other answer goes through
        # Samantha's voice too (see _answer_in_samantha_voice).
        # The old code ended here with speak(msg) — NVDA — which
        # is silent while NVDA quiet is on, so typing "my name
        # is Ashley", "pause", "next file" or "download status"
        # ran the command and she heard nothing at all.
        self._answer_in_samantha_voice(msg)
    
    def _voice_no_command(self):
        """Handle no command recognized"""
        # Ashley, 2026-11-26: after the startup greeting she
        # said nothing yet — do not say "Excuse me". The list
        # of channels has not been read, so read it now (she
        # still needs her options), and listen again after it
        # so she can pick one. _startup_show_list clears the
        # flag, so this only happens once.
        if getattr(self, "_startup_list_pending", False):
            self._startup_show_list()
            return
        # Honey, 2026-11-23 evening: if Samantha cannot hear
        # anything, she says "Excuse me" and asks Honey to
        # say it again, instead of just "No command recognized".
        # Ashley, 2026-11-26: in her own recorded voice, not
        # NVDA's (sounds/samantha_excuse_me.wav), so NVDA
        # stays quiet.
        msg = "Excuse me, I didn't hear you. Could you say that again?"
        self.status_label.SetLabel(msg)
        self._play_sound_effect("samantha_excuse_me.wav")
    
    def _voice_error(self, error):
        """Handle voice recognition error"""
        # Listening ended with an error, so no end chime was
        # played — clear the chime flag so the next session
        # can chime again. And do not re-arm listening: a
        # broken mic must not loop.
        self._want_continuous = False
        self._wake_chimes_played = False
        msg = f"Voice error: {error}"
        self.status_label.SetLabel(msg)
        # Ashley, 2026-11-27: even an error is answered in
        # Samantha's voice, never NVDA — the "Excuse me" clip
        # fits (she could not be heard), and the exact error
        # stays on the status line and in the log.
        self._answer_in_samantha_voice(msg, "samantha_excuse_me.wav")
    
    def _toggle_wake_word_mode(self, event=None):
        """Toggle wake word listening mode"""
        if not self.voice_available:
            # Same as _toggle_voice_listening above: try to
            # create voice control now, and if that fails say
            # so in Samantha's voice, never silent NVDA.
            if self._try_create_voice_control():
                pass
            else:
                self._say_listening_not_ready(force=True)
                return
        
        if self.wake_word_mode:
            # Stop wake word mode
            self.wake_word_mode = False
            self._wake_chimes_played = False
            self.voice.stop_listening()
            msg = "Wake word mode stopped"
            # In Samantha's voice, not NVDA speak(): NVDA is
            # quiet in the app, so speak() would be silent.
            self._answer_in_samantha_voice(
                msg, "samantha_excuse_me.wav")
        else:
            # Start wake word mode
            # Honey asked 2026-11-23: the start bell should ring on the
            # call button, as soon as she calls Samantha with Ctrl+Shift+W,
            # not only after Samantha is heard. Ashley, 2026-11-26:
            # high chime first, then the low chime 2 seconds later.
            # Ashley, 2026-11-27: if a Ctrl+Shift+B turn is already
            # listening, do not start a second listener on top of
            # it — the two share one microphone and one recogniser,
            # so they would hear each other. Say so and keep the
            # B turn running; she presses W again after it ends.
            if getattr(self, "is_voice_listening", False):
                self._answer_in_samantha_voice(
                    "I'm already listening. Go ahead.",
                    "samantha_im_on_it.wav")
                return
            self.wake_word_mode = True
            # Wake-word mode has its own continuous loop, so
            # one-time listening must not re-arm on top of it.
            self._want_continuous = False
            self._excuse_me_said = False
            self._play_wake_chimes()
            # Ashley, 2026-11-27: Ctrl+Shift+W turns on
            # always-listening wake-word mode. She then says
            # Samantha's name — Samantha, Sam, Sammy, Guide,
            # or Metro — followed by her command, and Samantha
            # answers "Yes?" and then hears the command.
            # The announcement below deliberately does NOT
            # speak the wake words out loud: the old wording
            # said "Say 'Samantha', 'Sam', 'Sammy'..." in
            # Samantha's own reading voice, and the microphone
            # — already listening — heard her own voice saying
            # "Samantha" and answered itself, then heard the
            # rest of the announcement as a command and said
            # "Excuse me". "Say my name" says the same thing
            # without ever speaking a wake word.
            msg = "I'm listening. Say my name, then your command."
            # In Samantha's voice, not NVDA speak(): NVDA is
            # quiet in the app, so speak() would be silent.
            self._answer_in_samantha_voice(msg)

            self.wake_word_thread = threading.Thread(target=self._wake_word_listen_thread, daemon=True)
            self.wake_word_thread.start()
    
    def _wake_word_listen_thread(self):
        """Thread for continuous wake word listening"""
        def callback(event_type, data=None):
            if event_type == 'wake_word_detected':
                wx.CallAfter(self._wake_word_detected)
            elif event_type == 'command':
                wx.CallAfter(self._wake_word_command, data)
            elif event_type == 'no_command':
                wx.CallAfter(self._wake_word_no_command)
            elif event_type == 'error':
                wx.CallAfter(self._voice_error, data)
        
        try:
            self.voice.listen_for_wake_word(callback)
        except Exception as e:
            wx.CallAfter(self._voice_error, str(e))
    
    def _wake_word_detected(self):
        """Handle wake word detection"""
        # Ashley, 2026-11-26: the wake chime should be steadier.
        # The start bell already rang once when wake-word mode
        # started (Ctrl+Shift+W), so it is not played again
        # here — a second bell on top of it was doubling up.
        # Samantha just answers "Yes?" in her own voice
        # (sounds/samantha_yes.wav), then listens for the
        # command. The "Hi Sweetie, how are you doing?"
        # greeting stays for startup and the greet command.
        # Ashley, 2026-11-27: if Samantha herself is still
        # reading something out loud (the list, the guide),
        # do not play "Yes?" over it — the microphone may
        # have heard her own reading, not Ashley, and a
        # "Yes?" on top of the reading would only add a
        # second voice. The command window in voice_control
        # still runs, so a real command spoken now is heard.
        if getattr(self, "_samantha_reading", False):
            return
        self._play_sound_effect("samantha_yes.wav")
        # Samantha greets Ashley by name, when she has told Samantha
        # her name by voice (see _parse_name_command / _set_user_name).
        name = self._get_user_name()
        msg = f"Yes? Hi {name}, I'm listening" if name else "Yes? I'm listening"
        self.status_label.SetLabel(msg)
        return
    
    def _wake_word_command(self, text):
        """Handle command after wake word"""
        self._play_end_chime()
        # A real command was heard, so a later "Excuse me"
        # may be said again if Samantha stops hearing her.
        self._excuse_me_said = False
        command = self.voice.parse_command(text)
        self._execute_voice_command(command, text)
    
    def _wake_word_no_command(self):
        """Handle no command after wake word"""
        self._play_end_chime()
        # Ashley, 2026-11-26: "it also keeps on saying excuse
        # me." In wake-word mode this runs every time a command
        # window ends empty, so it repeated over and over while
        # she was not speaking. Now "Excuse me" is said only
        # once in a row — after that, Samantha stays quiet and
        # keeps listening for the wake word. The flag clears
        # whenever a real command is heard, or wake-word mode
        # is started again.
        msg = "Excuse me, I didn't hear you. Could you say that again?"
        self.status_label.SetLabel(msg)
        if not getattr(self, "_excuse_me_said", False):
            self._excuse_me_said = True
            self._play_sound_effect("samantha_excuse_me.wav")
    
    def _check_channel_integrity(self):
        """Repair channels on startup instead of calling them corrupted.

        An out-of-range index or a stale cached playlist only means a
        file was moved or deleted, or the cache is old -- it does not
        mean the channels file itself is corrupt. So this method repairs
        that channel only (clamp the index, drop stale cached entries,
        rebuild the cache from the folders) and keeps every channel.
        It never deletes the channels file.

        Only a channels file that cannot be read as JSON at all, or is
        missing its 'channels' section, is treated as corrupt, and even
        then a backup is tried first and nothing is deleted.
        """
        # True file corruption: the load failed and backup recovery in
        # ChannelManager.load_channels() could not fix it. The file is
        # left exactly as it is (save is locked) so no data is lost.
        if not self.channels._load_ok:
            if self.channels._recover_from_backup():
                self.logger.log_channel("RECOVERED", "", "channels restored from backup")
                self.playlist = PlaylistManager()
                self._load_current_channel()
                self._update_title()
                self._update_display()
                msg = "Honey, your channels could not be read, so I brought them back from a backup."
                self.status_label.SetLabel(msg)
                speak(msg)
                return
            self.logger.log_error("CORRUPTION DETECTED: channels file unreadable, no valid backup found")
            msg = ("Honey, your channels file could not be read, and no backup "
                   "could bring it back. I did not delete anything, so your "
                   "channels file is still there for us to look at together.")
            wx.MessageBox(msg, "Channels Could Not Be Read", wx.OK | wx.ICON_WARNING)
            self.status_label.SetLabel(msg)
            speak(msg)
            return

        repaired = self.channels.repair_channels()
        if repaired:
            names = ", ".join(n for n in repaired if n != "(current channel)")
            self.logger.log_channel("REPAIRED", "", f"channels repaired on startup: {', '.join(repaired)}")
            # The repair may have changed the index or cleared a stale
            # cache, so reload the current channel from the repaired data.
            self.playlist = PlaylistManager()
            self._load_current_channel()
            self._update_title()
            self._update_display()
            if names:
                msg = (f"Honey, I fixed your channel list for {names}. "
                       f"Nothing was deleted. Your channels are still there.")
            else:
                msg = "Honey, I fixed your channel list. Nothing was deleted."
            self.status_label.SetLabel(msg)
            speak(msg)

    def _sounds_enabled(self):
        """Check if startup/outro sounds are enabled"""
        import configparser
        config = configparser.ConfigParser()
        config_path = Path(__file__).parent / "config.ini"
        try:
            config.read(config_path)
            return config.getboolean("settings", "sounds_enabled", fallback=True)
        except Exception:
            return True

    def _get_user_name(self):
        """Return the saved user name, or empty string if not set."""
        import configparser
        config = configparser.ConfigParser()
        config_path = Path(__file__).parent / "config.ini"
        try:
            config.read(config_path)
            return config.get("settings", "user_name", fallback="").strip()
        except Exception:
            return ""

    def _set_user_name(self, name):
        """Save the user's name to config."""
        import configparser
        config_path = Path(__file__).parent / "config.ini"
        config = configparser.ConfigParser()
        config.read(config_path)
        if "settings" not in config:
            config["settings"] = {}
        config["settings"]["user_name"] = name.strip()
        with open(config_path, "w") as f:
            config.write(f)

    def _on_set_name(self, event=None):
        """Prompt the user to set or change their name."""
        current = self._get_user_name()
        dlg = wx.TextEntryDialog(
            self, "What is your name? (used to personalize messages)",
            "Your Name", current
        )
        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            self._set_user_name(name)
            if name:
                msg = f"Name set to {name}"
            else:
                msg = "Name cleared"
            self.status_label.SetLabel(msg)
            speak(msg)
        dlg.Destroy()

    def _toggle_sounds(self, event=None):
        """Toggle startup/outro sounds on or off"""
        import configparser
        config_path = Path(__file__).parent / "config.ini"
        config = configparser.ConfigParser()
        config.read(config_path)
        if "settings" not in config:
            config["settings"] = {}
        currently_enabled = config.getboolean("settings", "sounds_enabled", fallback=True)
        new_value = not currently_enabled
        config["settings"]["sounds_enabled"] = str(new_value)
        with open(config_path, "w") as f:
            config.write(f)
        state = "on" if new_value else "off"
        msg = f"Startup and exit sounds turned {state}"
        self.status_label.SetLabel(msg)
        speak(msg)

    def _cancel_nvda_speech_once(self):
        """Cancel whatever NVDA is saying (NVDA speech only).

        Never touches Samantha's own voice or the shows: those
        play through the audio engine, not NVDA.
        """
        if _NVDA_QUIET:
            return
        try:
            if NVDA_AVAILABLE and nvda:
                nvda.nvdaController_cancelSpeech()
        except Exception:
            pass

    def _quiet_nvda_startup(self, _tick=0):
        """Keep the first second after launch quiet.

        Ashley, 2026-11-28: "make it so NVDA does not say pain
        every time the program loads". At launch, focus lands on
        the unnamed main panel, and NVDA — still awake, because
        quiet mode's keypress has not landed yet — announces the
        panel's role, "pane" (she hears "pain"). Two things cover
        the gap before quiet mode engages: focus is moved to the
        named "Type to Samantha" box as early as it can, and
        whatever NVDA is saying in that first second is
        cancelled. Ticks about eight times at 120 ms, and stops
        the moment quiet mode is on, because then NVDA is asleep
        and there is nothing left to cancel.
        """
        if _NVDA_QUIET or not NVDA_AVAILABLE:
            return
        try:
            self._focus_command_box_if_on_panel()
            self._cancel_nvda_speech_once()
        except Exception:
            pass
        if _tick < 8:
            wx.CallLater(120, self._quiet_nvda_startup, _tick + 1)

    def _enable_nvda_quiet(self, _retry=0):
        """Quiet NVDA for this app after the window opens.

        Ashley, 2026-11-26: NVDA should stop talking while she is in
        AudioVault TV and talk again when she closes it — and she
        wants the toggle to do it automatically, so she does not
        have to press anything. The window is brought to the front
        first, because the sleep keypress only affects the focused
        app. The key is only pressed once the window is actually
        focused: an earlier version pressed it once at 500 ms
        whether the window had focus or not, so the keypress could
        land in another window, NVDA kept saying "pane" in this
        app, and nothing ever tried again. Now, if the window is
        not focused yet, it tries again every 2 seconds, up to
        5 times. If she comes back to the window later, the
        activate event tries again too (see _on_activate_nvda_quiet).

        If a marker file says a previous run left quiet on (the
        app crashed before it could turn it back off), NVDA is
        probably still asleep for this app, so the key is not
        pressed again — pressing it again would wake NVDA up.
        But a marker from before this Windows boot is stale:
        NVDA restarted since then and is awake again, so a stale
        marker is deleted and the key is pressed after all.
        """
        global _NVDA_QUIET
        if not NVDA_AVAILABLE:
            return
        if not getattr(self, "_nvda_quiet_wanted", True):
            return
        if _NVDA_QUIET:
            return
        if _NVDA_QUIET_MARKER.exists():
            if _nvda_quiet_marker_stale():
                try:
                    _NVDA_QUIET_MARKER.unlink(missing_ok=True)
                except Exception:
                    pass
                self.logger.log_playback("NVDA", "Quiet marker is from before this boot; enabling quiet again")
            else:
                _NVDA_QUIET = True
                try:
                    self._nvda_quiet_menu_item.Check(True)
                except Exception:
                    pass
                self.logger.log_playback("NVDA", "Quiet mode already on from previous run; key not pressed again")
                return
        # Raise the window, but do NOT SetFocus() on the frame:
        # that yanked focus out of the "Type to Samantha" box
        # (and out of anywhere else she was typing) every time
        # quiet mode was enabled or re-enabled, so her typing
        # went nowhere and Enter did nothing. Raising the window
        # is enough for the NVDA sleep keypress, which only
        # needs this window to be the active one.
        # Ashley, 2026-11-27: only raise it when it is not
        # already active — raising an already-active window
        # re-announces it, so NVDA said "pane" again for
        # nothing, every time quiet mode was re-checked.
        try:
            if not self.IsActive():
                self.Raise()
        except Exception:
            pass
        wx.CallLater(300, self._press_nvda_quiet_if_focused, _retry)

    def _press_nvda_quiet_if_focused(self, _retry=0):
        """Press the NVDA sleep key, but only while this window is focused."""
        global _NVDA_QUIET
        if not NVDA_AVAILABLE:
            return
        if not getattr(self, "_nvda_quiet_wanted", True):
            return
        if _NVDA_QUIET:
            return
        try:
            focused = self.IsActive()
        except Exception:
            focused = False
        if not focused:
            if _retry < 5:
                wx.CallLater(2000, self._enable_nvda_quiet, _retry + 1)
                self.logger.log_playback("NVDA", f"Window not focused yet; will try quiet again ({_retry + 1}/5)")
            else:
                self.logger.log_playback("NVDA", "Quiet mode not enabled: window never took focus; press Ctrl+Shift+Q once in the app")
            return
        if set_nvda_quiet(True):
            try:
                self._nvda_quiet_menu_item.Check(True)
            except Exception:
                pass
            self.logger.log_playback("NVDA", "Quiet mode on: NVDA sleeps while in AudioVault TV")
            # Focus was on the unnamed panel, so NVDA said
            # "pane". Move it to the "Type to Samantha" box
            # now that NVDA is asleep, so coming back to the
            # window never lands on the panel again.
            self._focus_command_box_if_on_panel()

    def _focus_command_box_if_on_panel(self):
        """Move focus off the main panel, into the text box.

        Ashley, 2026-11-27: NVDA kept saying "pane" all the
        time, because focus started on — and kept landing back
        on — the main wx.Panel, which NVDA announces by its
        role, "pane". The "Type to Samantha" box is a named
        edit box, so focus there is announced as the box, not
        "pane", and it is where she types anyway. Only move
        focus when it is on the panel, the frame, or nowhere:
        never steal it from a control she is already using,
        a menu, or a dialog.
        """
        try:
            box = getattr(self, "command_box", None)
            if box is None:
                return
            current = wx.Window.FindFocus()
            panel = getattr(self, "_main_panel", None)
            if current is None or current is self or current is panel:
                box.SetFocus()
        except Exception:
            pass

    def _on_activate_nvda_quiet(self, event):
        """When the app window becomes the focused one, quiet NVDA if wanted."""
        try:
            if event.GetActive():
                self._enable_nvda_quiet()
                self._focus_command_box_if_on_panel()
                # Ashley, 2026-11-28: if quiet mode should be on
                # but has not engaged yet (first launch, or after
                # a Windows/NVDA restart), cancel whatever NVDA is
                # saying about this window, so "pane" does not come
                # back when she returns to it. Skipped while she
                # has quiet mode turned off herself.
                if (getattr(self, "_nvda_quiet_wanted", True)
                        and not _NVDA_QUIET and NVDA_AVAILABLE):
                    wx.CallLater(120, self._cancel_nvda_speech_once)
            event.Skip()
        except Exception:
            pass

    def _disable_nvda_quiet(self):
        """Turn NVDA back on when the app closes, if it was quieted."""
        if _NVDA_QUIET:
            set_nvda_quiet(False)
            try:
                self._nvda_quiet_menu_item.Check(False)
            except Exception:
                pass

    def _on_toggle_nvda_quiet(self, event=None):
        """Flip NVDA quiet mode from the menu or Ctrl+Shift+Q."""
        global _NVDA_QUIET
        if _NVDA_QUIET:
            self._nvda_quiet_wanted = False
            set_nvda_quiet(False)
            try:
                self._nvda_quiet_menu_item.Check(False)
            except Exception:
                pass
            speak("NVDA is back on. I will talk in Audio Vault TV again.")
        else:
            self._nvda_quiet_wanted = True
            if NVDA_AVAILABLE and nvda:
                try:
                    nvda.nvdaController_cancelSpeech()
                except Exception:
                    pass
            set_nvda_quiet(True)
            try:
                self._nvda_quiet_menu_item.Check(True)
            except Exception:
                pass
            # No speak() here on purpose — NVDA is quiet now, and
            # Samantha's voice and the shows are unaffected.

    # ---- OneDrive "free up space" (online-only) support ----

    def _cloud_cleanup_enabled(self):
        """Whether downloads are automatically made online-only after download."""
        import configparser
        config = configparser.ConfigParser()
        config_path = Path(__file__).parent / "config.ini"
        try:
            config.read(config_path)
            return config.getboolean("settings", "cloud_cleanup_enabled", fallback=False)
        except Exception:
            return False

    def _toggle_cloud_cleanup(self, event=None):
        """Toggle automatic 'free up space' (online-only) for downloads."""
        import configparser
        config_path = Path(__file__).parent / "config.ini"
        config = configparser.ConfigParser()
        config.read(config_path)
        if "settings" not in config:
            config["settings"] = {}
        new_value = not config.getboolean("settings", "cloud_cleanup_enabled", fallback=False)
        config["settings"]["cloud_cleanup_enabled"] = str(new_value)
        with open(config_path, "w") as f:
            config.write(f)
        if new_value:
            msg = ("Automatic cloud cleanup turned on. After each download, files will be "
                   "set to online-only to free local disk space. They stay playable and "
                   "download on demand when you play them.")
        else:
            msg = "Automatic cloud cleanup turned off. Downloads will keep full local copies."
        self.status_label.SetLabel("Cloud cleanup " + ("on" if new_value else "off"))
        speak(msg)
        wx.MessageBox(msg, "Cloud Cleanup", wx.OK | wx.ICON_INFORMATION)

    def _free_up_space(self, folder):
        """Mark everything in `folder` as online-only in OneDrive, reclaiming
        local disk space. Uses the same mechanism as right-click > Free up space.
        Safe no-op if the folder isn't in OneDrive or Files On-Demand is off.
        Returns (success, message)."""
        self.logger.log_playback("CLOUD", f"--- Free up space requested for: {folder}")

        if not folder or not os.path.isdir(folder):
            self.logger.log_error(f"CLOUD: folder not found: {folder}")
            return False, "Folder not found."
        if os.name != "nt":
            self.logger.log_error("CLOUD: not Windows, online-only not supported")
            return False, "Online-only files are only supported on Windows."

        # Diagnostic: is this folder actually inside a OneDrive path?
        onedrive_env = os.environ.get("OneDrive", "") or os.environ.get("OneDriveConsumer", "")
        in_onedrive = ("onedrive" in folder.lower()) or (onedrive_env and onedrive_env.lower() in folder.lower())
        self.logger.log_playback("CLOUD", f"OneDrive env='{onedrive_env}', folder in OneDrive={in_onedrive}")
        if not in_onedrive:
            self.logger.log_error(
                f"CLOUD: folder is NOT under OneDrive — 'free up space' only works inside "
                f"the OneDrive folder. folder={folder}"
            )
            return False, ("This folder is not inside OneDrive, so it can't be made online-only. "
                           "Set your download folder to a location inside OneDrive.")

        # Count files up front so we can tell if anything was even present
        mp3_count = 0
        for _root, _dirs, files in os.walk(folder):
            mp3_count += sum(1 for f in files if f.lower().endswith(".mp3"))
        self.logger.log_playback("CLOUD", f"Found {mp3_count} mp3 file(s) under folder")

        try:
            # attrib +U (unpinned / online-only) -P (remove pinned) recursively.
            result = subprocess.run(
                ["attrib", "+U", "-P", "/s", os.path.join(folder, "*")],
                capture_output=True, text=True, timeout=300,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            out = (result.stdout or "").strip()
            err = (result.stderr or "").strip()
            self.logger.log_playback("CLOUD", f"attrib rc={result.returncode}")
            if out:
                self.logger.log_playback("CLOUD", f"attrib stdout: {out[:500]}")
            if err:
                self.logger.log_error(f"CLOUD: attrib stderr: {err[:500]}")

            # Verify: check a sample of files for the 'U' (unpinned/online-only)
            # attribute so we know whether it actually took effect.
            verified = self._verify_online_only(folder)
            self.logger.log_playback("CLOUD", f"Verification: {verified}")

            return True, f"Freed local space: {folder} is now online-only. ({verified})"
        except subprocess.TimeoutExpired:
            self.logger.log_error("CLOUD: attrib timed out")
            return False, "Freeing space timed out."
        except Exception as e:
            self.logger.log_error(f"CLOUD CLEANUP ERROR: {e}")
            return False, f"Could not free space: {e}"

    def _verify_online_only(self, folder, sample=5):
        """Check a sample of files to see if they now carry the online-only
        attribute. Returns a short human-readable summary for the log."""
        try:
            checked = 0
            online_only = 0
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    if not f.lower().endswith(".mp3"):
                        continue
                    path = os.path.join(root, f)
                    try:
                        r = subprocess.run(
                            ["attrib", path],
                            capture_output=True, text=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                        )
                        line = (r.stdout or "").strip()
                        # The 'U' flag in attrib output marks unpinned/online-only
                        attrs = line.split(os.sep)[0] if line else ""
                        if "U" in attrs:
                            online_only += 1
                        checked += 1
                    except Exception:
                        pass
                    if checked >= sample:
                        break
                if checked >= sample:
                    break
            return f"{online_only}/{checked} sampled files are online-only"
        except Exception as e:
            return f"verify error: {e}"

    def _maybe_free_up_space(self, folder):
        """Run cloud cleanup on `folder` if the auto setting is enabled."""
        if self._cloud_cleanup_enabled():
            ok, msg = self._free_up_space(folder)
            if ok:
                self.status_label.SetLabel("Freed local disk space (files now online-only)")
                self.logger.log_playback("CLOUD", msg)
            else:
                self.logger.log_error(f"CLOUD: free up space did not run: {msg}")

    def _on_free_up_space_now(self, event=None):
        """Menu action: free up space on all configured download folders now."""
        folders = set()
        try:
            folders.add(av.load_download_dir(kind="movies"))
            folders.add(av.load_download_dir(kind="shows"))
            folders.add(av.load_download_dir())
        except Exception:
            pass
        try:
            folders.add(yt.load_download_dir())
        except Exception:
            pass

        freed = []
        for folder in folders:
            if folder and os.path.isdir(folder):
                ok, _ = self._free_up_space(folder)
                if ok:
                    freed.append(folder)

        if freed:
            msg = f"Freed local space on {len(freed)} download folder(s). Files are now online-only."
        else:
            msg = "No download folders were found to free up."
        self.status_label.SetLabel(msg)
        speak(msg)
        wx.MessageBox(msg, "Free Up Space", wx.OK | wx.ICON_INFORMATION)

    def _play_startup_sound(self):
        """Play startup sound if available and enabled"""
        if not self._sounds_enabled():
            return
        startup_file = Path(__file__).parent / "sounds" / "startup.mp3"
        if startup_file.exists() and self.player is not None:
            try:
                self.player.load(str(startup_file))
                self.player.play()
            except Exception as e:
                print(f"Could not play startup sound: {e}")

    def _samantha_busy(self):
        """True while one of Samantha's clips is still playing.

        Shows are never counted: they play through the
        AudioPlayer music stream, clips through the separate
        clip player (see audio_player.ClipPlayer), so a show
        playing in the background never makes this say "busy".
        """
        try:
            from audio_player import clip_player
            return clip_player().busy()
        except Exception:
            return False

    def _clip_ms(self, path):
        """Length of a sound file in milliseconds.

        Read from the file's header info. Used so a next clip
        (or listening) is scheduled after this clip actually
        finishes, instead of a fixed guess that overlaps or
        cuts it off.
        """
        try:
            import soundfile as sf
            info = sf.info(str(path))
            return int(info.frames / float(info.samplerate) * 1000)
        except Exception:
            return 2000

    def _play_sound_effect(self, filename):
        """Play a Samantha clip, one at a time.

        Ashley, 2026-11-26: clips were overlapping, because a
        fresh Sound played on a fresh channel every time and
        nothing ever stopped the previous clip. Now the clip
        plays on Samantha's one dedicated clip player
        (see audio_player.ClipPlayer), which stops the old
        clip first, so a new clip cuts the old one off instead
        of talking over it. Any queued sequence (wake chimes,
        greeting) is cancelled too — it belonged to the turn
        this clip interrupts. Shows are untouched: they play
        through the AudioPlayer music stream, not the clips.
        Returns the clip length in milliseconds, so callers can
        schedule what comes next after it finishes.
        """
        sound_file = Path(__file__).parent / "sounds" / filename
        if not sound_file.exists():
            return 0
        self._cancel_samantha_queue()
        try:
            from audio_player import clip_player
            clip_player().play_file(str(sound_file))
            return self._clip_ms(sound_file)
        except Exception as e:
            print(f"Could not play sound effect {filename}: {e}")
            return 0

    def _cancel_samantha_queue(self):
        """Drop any Samantha clips still waiting their turn.

        If a dropped clip was keeping _samantha_reading up
        (a "not ready" clip, or an "I'm on it" while the
        reading voice installed), clear that flag too — nothing
        is reading any more, so listening must not wait forever
        for a clip that will never play. Next-step callbacks
        (the greeting after "Audio Vault TV") are NOT run: the
        turn they belonged to was interrupted.
        """
        queue = getattr(self, "_samantha_queue", None) or []
        for _path, after in queue:
            try:
                if after is not None and after == self._clear_samantha_reading:
                    self._samantha_reading = False
            except Exception:
                pass
        self._samantha_queue = []
        timer = getattr(self, "_samantha_pump_timer", None)
        self._samantha_pump_timer = None
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass

    def _queue_samantha_sound(self, filename_or_path, after=None):
        """Play a Samantha clip after the one playing now finishes.

        Ashley, 2026-11-26: sequences — wake chimes, the
        greeting, "I'm on it" then the answer, the guide intro
        then the reading — were all starting together and
        talking over each other. Queued clips wait their turn:
        each one plays on Samantha's dedicated channel only
        once the channel is idle, then the next one starts.
        A new _play_sound_effect cancels the queue (see above),
        so a fresh command still cuts in at once. `after` runs
        on the main thread once this clip has finished.
        `filename_or_path` is a file in sounds/, or a full path
        (a synthesised reading file).
        """
        path = Path(str(filename_or_path))
        if not path.is_absolute():
            path = Path(__file__).parent / "sounds" / filename_or_path
        self._samantha_queue.append((str(path), after))
        if getattr(self, "_samantha_pump_timer", None) is None:
            self._pump_samantha_queue()

    def _play_samantha_sequence(self, filenames, after=None):
        """Play clips one after another, then run `after`.

        The wake chimes (high, then low) and the startup greeting
        use this, so each clip is heard whole before the next one
        starts — never at the same time, never twice.
        """
        for filename in filenames:
            self._queue_samantha_sound(filename)
        if after is not None:
            self._samantha_queue.append((None, after))
            if getattr(self, "_samantha_pump_timer", None) is None:
                self._pump_samantha_queue()

    def _pump_samantha_queue(self):
        """Play the next queued Samantha clip, when the channel is free."""
        self._samantha_pump_timer = None
        if not getattr(self, "_samantha_queue", None):
            return
        if self._samantha_busy():
            self._samantha_pump_timer = wx.CallLater(
                200, self._pump_samantha_queue)
            return
        path, after = self._samantha_queue.pop(0)
        if path is None:
            if after is not None:
                try:
                    after()
                except Exception:
                    pass
            self._pump_samantha_queue()
            return
        ms = 0
        try:
            from audio_player import clip_player
            clip_player().play_file(str(path))
            ms = self._clip_ms(path)
        except Exception as e:
            print(f"Could not play queued sound {path}: {e}")
        if after is not None:
            wx.CallLater(ms + 150, after)
        self._samantha_pump_timer = wx.CallLater(
            ms + 150, self._pump_samantha_queue)

    def _answer_in_samantha_voice(self, text, fallback_clip="samantha_im_on_it.wav"):
        """Answer a command so Ashley actually hears it.

        Ashley, 2026-11-26: typing a command and pressing Enter
        ran it, but she heard nothing back. The old code answered
        most commands with speak(), which is NVDA — and NVDA quiet
        mode (on by default in the app) makes speak() say nothing
        at all. So every command answer now goes through
        Samantha's reading voice when it is ready; when it is not
        ready yet, she hears a short recorded clip instead of
        silence — "I'm on it" for an action that was done, or the
        clip the caller names (for example "Excuse me" when she
        was not understood). Never NVDA, never Microsoft.

        Ashley, 2026-11-27: the fallback clip used to be
        "samantha_reading_not_ready.wav" for about thirty
        answers — every list, search, and download result.
        That clip says the reading voice is not ready, so the
        moment the startup install failed fast (pip failing in
        seconds — no internet, pip in another Python), her
        very first ask, "Doctor Who", answered with "not
        ready" even though the app was about to retry by
        itself in a minute. A caller may still pass that clip
        for the one case where it is true (the reading voice
        really did fail), but it is NEVER played here while
        the install is still running or has never been tried:
        then the answer is "I'm on it" and the words are kept
        as a pending reading, to be read when the voice is
        ready (see _say_in_samantha_voice). When a try has
        really failed, the failure itself already said "not
        ready" once (see _on_edge_install_failed), so this
        answers "I'm on it" too and the retry reads the words
        — she is never told "not ready" twice for one ask.
        """
        try:
            self.status_label.SetLabel(text)
        except Exception:
            pass
        if self._samantha_voice_mode() == "edge":
            self._say_in_samantha_voice(text)
            return
        if fallback_clip == "samantha_reading_not_ready.wav":
            state = getattr(self, "_edge_install_state", "unknown")
            if state in ("installing", "checking") or (
                    state == "unknown"
                    and getattr(self, "_edge_install_running", False)):
                # Nothing has failed — the voice is still on
                # its way. Say "I'm on it", keep the words,
                # read them when it is ready.
                self._pending_reading_text = text
                self._queue_samantha_sound(
                    "samantha_im_on_it.wav",
                    after=self._clear_samantha_reading)
                return
            if state == "failed":
                # A try really did fail. The failure already
                # said "not ready" once; do not say it again
                # for this same ask. Keep the words for the
                # retry instead, and say "I'm on it" so she
                # knows she was heard.
                self._pending_reading_text = text
                self._queue_samantha_sound(
                    "samantha_im_on_it.wav",
                    after=self._clear_samantha_reading)
                return
        self._queue_samantha_sound(fallback_clip)

    def _play_wake_chimes(self):
        """Wake chimes: high chime once, then low chime once.

        Ashley, 2026-11-26: "make it go on the high chime and
        then two seconds later have it on a low chime" — using
        the chimes she already has, nothing new. The high chime
        is start_of_request.wav (one long high C, about 4.6
        seconds), the low chime is end_of_request.wav (medium G
        to medium C). A fixed 2-second wait started the low
        chime while the high chime was still ringing, so they
        played at the same time; and the low chime also rang
        again at the end of the request. Now the two chimes are
        a sequence (see _play_samantha_sequence): the low chime
        waits until the high chime has actually finished, each
        plays once only, and _play_end_chime still skips the low
        chime once the chimes have played. Listening stays open
        the whole time — 20 seconds one-time, 15 seconds after a
        wake word — so the low chime does not cut her off; she
        still has plenty of time to speak.
        """
        if self._wake_chimes_played:
            return
        self._wake_chimes_played = True
        self._play_samantha_sequence(
            ["start_of_request.wav", "end_of_request.wav"])

    def _play_end_chime(self):
        """End-of-request chime, once only.

        The low chime (end_of_request.wav) already played as
        part of the wake chimes 2 seconds after listening
        started, so it is not played again at the end of the
        request — that was the double. If the wake chimes did
        not play for this session, the end chime plays as
        before.

        Ashley, 2026-11-26: start of request once, then end
        of request once. In wake-word mode (Ctrl+Shift+W) the
        listening session stays open for many commands, so
        the flag is NOT cleared here — otherwise the low
        chime would ring again after the second command,
        and the third, and so on. It is cleared when wake
        word mode stops, so the next time she calls Samantha
        the chimes play again, once each. In one-time mode
        (Ctrl+Shift+B) the session ends with the request,
        so the flag is cleared here.
        """
        if self._wake_chimes_played:
            if not self.wake_word_mode:
                self._wake_chimes_played = False
            return
        self._play_sound_effect("end_of_request.wav")
    
    def _show_greeting_dialog(self):
        """Startup greeting, in Samantha's voice, step by step.

        Ashley, 2026-11-26: "I want her to say Audio Vault TV
        then greet me and then ask me what channels and then
        name the channel lists and then that's it." So when the
        app opens (or she says hello), Samantha does exactly
        that, one thing at a time:
        1. "Audio Vault TV" in Samantha's own recorded voice
           (sounds/audio_vault_tv.wav, about 2 seconds).
        2. The greeting, "Hi Sweetie! How are you doing? What
           do you want to watch?" (about 5 seconds) — that is
           also the ask about what channels she wants.
        3. Samantha listens right away for her answer. If
           Ashley says "I'm good", Samantha says "That's
           wonderful" and then names the channels and what
           comes up next. If she names a show, it plays. If
           she says nothing, the channel list is read anyway
           and Samantha listens again so she can pick one.
           Listening starts as soon as the greeting finishes
           because she answers "I'm good" right away — an
           earlier version read the list first and only
           listened after it, so her answer was never heard
           and Samantha kept saying "Excuse me".

        NVDA kept saying "Greeting dialogue" (and "pane")
        when this pop-up opened, and she does not want NVDA
        to say anything here. So there is no dialog any more:
        NVDA speech is cancelled first so it does not talk
        over her, and nothing is spoken through NVDA. The
        current channel is already loaded at startup, so she
        can just press Space to play, or use a voice command
        to pick a channel — no typing in a dialog is needed.
        """
        # Stop any NVDA speech in progress, so Samantha is the
        # only voice she hears for the greeting.
        if NVDA_AVAILABLE and nvda:
            try:
                nvda.nvdaController_cancelSpeech()
            except Exception:
                pass
        # Step 1: "Audio Vault TV" in Samantha's voice, then
        # the greeting — one after the other, never overlapping
        # (see _play_samantha_sequence).
        self.status_label.SetLabel("Audio Vault TV")
        self._play_samantha_sequence(
            ["audio_vault_tv.wav"], after=self._startup_greeting)

    def _startup_greeting(self):
        """Startup step 2: the greeting, then listen for her answer.

        Ashley, 2026-11-26: "It's not responding when I say
        good." The greeting asks "How are you doing?", and she
        answers "I'm good" right away — but nobody was listening
        yet, because the channel list was read first and
        listening only started after the list finished. Her
        answer was lost, and after 20 seconds of silence
        Samantha said "Excuse me, I didn't hear you." So now
        Samantha listens as soon as the greeting finishes. If
        Ashley answers "I'm good", Samantha says "That's
        wonderful" and then reads the list and the guide
        (see feeling_good). If she names a show, it plays.
        If she says nothing, the list is read anyway (see
        _voice_no_command) and Samantha listens again.
        """
        self._startup_list_pending = True
        greeting_ms = self._play_sound_effect("samantha_how_are_you_doing.wav")
        self.status_label.SetLabel(
            "Hi Sweetie! How are you doing? What do you want to watch?")
        # Listen as soon as the greeting actually finishes, so
        # her answer is heard — the wait is the clip's own
        # length, not a fixed guess.
        wx.CallLater(greeting_ms + 300, self._listen_after_greeting)

    def _startup_show_list(self):
        """Startup step 3: read the shows, then let her pick one.

        Used when she said nothing after the greeting: the list
        is read so she still hears her options, and Samantha
        then listens for the show she wants, so she can just say
        it (see _start_selection_listening).
        """
        self._startup_list_pending = False
        self._speak_and_requiet(self._speak_show_list)
        self._start_selection_listening()

    def _listen_after_greeting(self):
        """After the startup greeting: do NOT start listening.

        Press-to-talk only, Ashley 2026-11-27: Samantha must
        wait for a button press before she tries to understand
        anything. This used to start one-time listening by
        itself as soon as the greeting finished — so the app
        was listening in the background while a show played,
        heard the show as commands, and paused it. Now the
        greeting ends quietly: she presses Ctrl+Shift+B when
        she wants to talk (one turn), or Ctrl+Shift+W for
        wake-word mode (always listening, until she turns it
        off). The one thing this still does: if listening is
        not available at all, say so once, in Samantha's own
        voice, so she is not left wondering why pressing B
        does nothing — the model install is already running
        by itself, and _on_vosk_model_ready announces when
        it is ready.
        """
        if not self.voice_available:
            self._say_listening_not_ready()
            return
        return
    
    def _start_selection_listening(self, _waited_ms=0):
        """After the list: open the mic so she can just say it.

        Ashley, 2026-11-28: "before it plays it should let me
        select the shows I want ... or let me tell it what I
        want". At this moment nothing is playing yet — she is
        still choosing — so listening here is safe, which is
        exactly the one moment the press-to-talk rule
        (2026-11-27) does not block: the microphone opens
        before any show sound, the one-time window ends with
        her command or after 20 seconds of silence, and it
        never re-arms, so a show playing afterwards is never
        heard as a command. Waits until Samantha has finished
        every reading (the list, the guide) — up to two
        minutes — so the microphone is never open while she
        is still talking.
        """
        if (getattr(self, "_samantha_reading", False)
                or self._samantha_busy()) and _waited_ms < 120000:
            wx.CallLater(1000, self._start_selection_listening,
                         _waited_ms + 1000)
            return
        self._start_listening(chimes=False)

    def _ask_channel_to_play(self, prompt_message):
        """Ask which channel to play"""
        channels = self.channels.get_channel_list()
        
        if not channels:
            # No local channels at all: fall back to Live TV instead
            # of stopping here. Live TV needs no external drive.
            if self._livetv_fallback("No channels are available"):
                return
            msg = "No channels available. Press Ctrl+T to create one."
            wx.MessageBox(msg, "No Channels", wx.OK | wx.ICON_INFORMATION)
            speak(msg)
            return
        
        # Show available channels
        channel_list = ", ".join(channels)
        full_prompt = f"{prompt_message}\n\nAvailable channels: {channel_list}"
        
        dlg = wx.TextEntryDialog(
            self,
            full_prompt,
            "Channel Selection",
            ""
        )
        
        result = dlg.ShowModal()
        channel_name = dlg.GetValue().strip()
        dlg.Destroy()
        
        if result == wx.ID_CANCEL:
            return
        
        if channel_name:
            # Find matching channel (case insensitive)
            matching_channel = None
            for ch in channels:
                if ch.lower() == channel_name.lower():
                    matching_channel = ch
                    break
            
            if matching_channel:
                # Switch to channel and start playing
                self._switch_to_channel(matching_channel)
                if self.playlist.get_current():
                    self.player.play()
                    msg = f"Now playing: {matching_channel}"
                    self.status_label.SetLabel(msg)
                    speak(msg)
            else:
                msg = f"Channel '{channel_name}' not found. Available channels: {channel_list}"
                wx.MessageBox(msg, "Channel Not Found", wx.OK | wx.ICON_WARNING)
                speak(f"Channel {channel_name} not found")
    
    def _auto_advance_to_next_channel(self):
        """Auto-advance to next channel after current finishes"""
        self.logger.log_playback("AUTO-ADVANCE", "Executing auto-advance to next channel")
        
        # Track how many empty channels we've skipped to avoid infinite loop
        if not hasattr(self, '_advance_attempts'):
            self._advance_attempts = 0
        
        total_channels = len(self.channels.get_channel_list())
        if self._advance_attempts >= total_channels:
            self._advance_attempts = 0
            self.player.is_playing = False
            self.is_switching_channels = False
            self.logger.log_error("All channels empty or drive disconnected")
            # Every local channel is empty - or the external drive is
            # not connected - so play Live TV instead. Live TV streams
            # over the internet, so it plays even without the drive,
            # and with the drive too, whenever no local show is available.
            if self._livetv_fallback("No channels with files found"):
                self.status_label.SetLabel("No channels with files found. Playing live TV instead.")
                return
            msg = "No channels with files found. Check if your external drive is connected."
            self.status_label.SetLabel(msg)
            speak(msg)
            return
        
        old_channel = self.channels.current_channel
        next_ch = self.channels.next_channel()
        
        if next_ch and next_ch != old_channel:
            self.logger.log_channel("AUTO-SWITCH", next_ch, f"from {old_channel}")
            self._play_sound_effect("remote.mp3")
            msg = f"Switching to: {next_ch}"
            self.status_label.SetLabel(msg)
            speak(msg)
            
            # Load the new channel
            self.player.stop()
            self.player.is_playing = False
            self.playlist = PlaylistManager()
            self._load_current_channel()
            self._update_title()
            
            # Wait for channel to load, then start playing
            wx.CallLater(1000, self._auto_start_playback)
        else:
            self.player.is_playing = False
            self.is_switching_channels = False
            self.logger.log_playback("FINISHED", "All channels completed")
            msg = "All channels finished"
            self.status_label.SetLabel(msg)
            speak(msg)
    
    def _auto_start_playback(self):
        """Start playback after auto-advancing to next channel"""
        if self.playlist.get_current():
            self.logger.log_playback("AUTO-PLAY", "Starting playback after channel switch")
            self._advance_attempts = 0
            # _start_playback already says this channel's own name, so
            # do not say it a second time here.
            self._start_playback()
            self.is_switching_channels = False
        else:
            self.logger.log_error("No files in channel after auto-advance")
            self._advance_attempts += 1
            msg = f"Channel {self.channels.current_channel} is empty, trying next..."
            self.status_label.SetLabel(msg)
            speak(msg)
            self.is_switching_channels = False
            # Try next channel
            wx.CallLater(500, self._auto_advance_to_next_channel)
    
    # ---- AudioVault Methods ----
    
    def _on_set_default_folder(self, kind):
        """Set default download folder for movies or shows"""
        current = av.load_download_dir(kind=kind)
        dlg = wx.DirDialog(self, f"Set default folder for {kind}", current)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            av.save_download_dir(path, kind=kind)
            msg = f"Default {kind} folder set to: {path}"
            self.status_label.SetLabel(msg)
            speak(msg)
        dlg.Destroy()
    
    def _on_check_updates(self, event=None):
        """Manually check for updates, show results, and install if the user agrees."""
        msg = "Checking for updates..."
        self.status_label.SetLabel(msg)
        speak(msg)
        threading.Thread(target=self._check_updates_thread, daemon=True).start()

    def _check_updates_thread(self):
        try:
            from auto_updater import check_for_updates
            available = check_for_updates()
            wx.CallAfter(self._check_updates_result, available, None)
        except Exception as e:
            self.logger.log_error(f"UPDATE CHECK ERROR: {e}")
            wx.CallAfter(self._check_updates_result, None, str(e))

    def _check_updates_result(self, available, error):
        if error:
            msg = f"Could not check for updates: {error}"
            self.status_label.SetLabel(msg)
            speak(msg)
            wx.MessageBox(msg, "Update Check Failed", wx.OK | wx.ICON_ERROR)
            return
        if not available:
            msg = "You are up to date. No updates available."
            self.status_label.SetLabel(msg)
            speak(msg)
            wx.MessageBox(msg, "No Updates", wx.OK | wx.ICON_INFORMATION)
            return

        count = len(available)
        listing = "\n".join(available[:20]) + ("\n..." if count > 20 else "")
        result = wx.MessageBox(
            f"{count} update(s) available:\n{listing}\n\nDownload and install now?",
            "Updates Available",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result != wx.YES:
            self.status_label.SetLabel("Update cancelled")
            return

        self.status_label.SetLabel("Downloading updates...")
        speak("Downloading updates, please wait")
        threading.Thread(target=self._apply_updates_thread, args=(available,), daemon=True).start()

    def _apply_updates_thread(self, available):
        try:
            from auto_updater import apply_updates
            updated = apply_updates(available)
            wx.CallAfter(self._apply_updates_result, updated, None)
        except Exception as e:
            self.logger.log_error(f"UPDATE APPLY ERROR: {e}")
            wx.CallAfter(self._apply_updates_result, None, str(e))

    def _apply_updates_result(self, updated, error):
        if error:
            msg = f"Update failed: {error}"
            self.status_label.SetLabel(msg)
            speak(msg)
            wx.MessageBox(msg, "Update Failed", wx.OK | wx.ICON_ERROR)
            return
        count = len(updated or [])
        self.logger.log_playback("UPDATE", f"Applied {count} file(s): {', '.join(updated or [])}")
        msg = (f"Updated {count} file(s). Please close and reopen AudioVault TV "
               f"completely for the changes to take effect.")
        self.status_label.SetLabel("Update complete - please restart the app")
        speak(msg)
        wx.MessageBox(msg, "Update Complete", wx.OK | wx.ICON_INFORMATION)

    def _on_upload_log(self, event):
        """Upload the log file to GitHub"""
        msg = "Uploading log to GitHub..."
        self.status_label.SetLabel(msg)
        speak(msg)
        
        try:
            self.logger.upload_log()
            msg = "Log uploaded to GitHub"
            self.status_label.SetLabel(msg)
            speak(msg)
            wx.MessageBox(msg, "Upload Complete", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            msg = f"Log upload failed: {e}"
            self.status_label.SetLabel(msg)
            speak("Log upload failed")
            wx.MessageBox(msg, "Upload Failed", wx.OK | wx.ICON_ERROR)
    
    def _vault_auto_login(self):
        """Try auto-login with saved credentials in background"""
        email, password = av.load_credentials()
        if email and password:
            threading.Thread(target=self._vault_auto_login_thread, args=(email, password), daemon=True).start()

    def _vault_auto_login_thread(self, email, password):
        """Background thread for auto-login"""
        try:
            if av.login(email, password, log_file=str(self.logger.log_file)):
                wx.CallAfter(self._vault_login_success)
        except Exception as e:
            self.logger.log_error(f"VAULT AUTO-LOGIN ERROR: {e}")

    def _vault_login_success(self):
        """Called on main thread after successful auto-login"""
        self.vault_logged_in = True
        try:
            self.vault_login_item.SetItemLabel("Logout\tCtrl+Shift+L")
        except Exception:
            pass
    
    def _on_vault_login_toggle(self, event):
        """Toggle between login and logout"""
        if self.vault_logged_in:
            self.vault_logged_in = False
            self.vault_login_item.SetItemLabel("Login\tCtrl+Shift+L")
            msg = "Logged out of AudioVault"
            self.status_label.SetLabel(msg)
            speak(msg)
        else:
            self._on_vault_login(None)
    
    def _on_vault_login(self, event):
        """Show login dialog"""
        dlg = wx.Dialog(self, title="AudioVault Login", size=(350, 200))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(panel, label="Email:"), 0, wx.ALL, 5)
        email_ctrl = wx.TextCtrl(panel)
        sizer.Add(email_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        sizer.Add(wx.StaticText(panel, label="Password:"), 0, wx.ALL, 5)
        pass_ctrl = wx.TextCtrl(panel, style=wx.TE_PASSWORD)
        sizer.Add(pass_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        
        remember_cb = wx.CheckBox(panel, label="Remember me")
        remember_cb.SetValue(True)
        sizer.Add(remember_cb, 0, wx.ALL, 5)
        
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Login")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        panel.SetSizer(sizer)
        
        # Pre-fill saved credentials
        email, password = av.load_credentials()
        if email:
            email_ctrl.SetValue(email)
        if password:
            pass_ctrl.SetValue(password)
        
        if dlg.ShowModal() == wx.ID_OK:
            email = email_ctrl.GetValue().strip()
            password = pass_ctrl.GetValue().strip()
            
            if email and password:
                msg = "Logging in..."
                self.status_label.SetLabel(msg)
                speak(msg)
                
                try:
                    self.logger.log_channel("VAULT", "LOGIN", f"Attempting login for {email}")
                    if av.login(email, password, log_file=str(self.logger.log_file)):
                        self.vault_logged_in = True
                        self.vault_login_item.SetItemLabel("Logout\tCtrl+Shift+L")
                        if remember_cb.GetValue():
                            av.save_credentials(email, password)
                        msg = "AudioVault login successful"
                        self.logger.log_channel("VAULT", "LOGIN", "Success")
                        self.status_label.SetLabel(msg)
                        speak(msg)
                    else:
                        msg = "Login failed. Check email and password."
                        self.logger.log_error(f"VAULT LOGIN FAILED for {email}")
                        wx.MessageBox(msg, "Login Failed", wx.OK | wx.ICON_ERROR)
                        speak(msg)
                except Exception as e:
                    msg = f"Login error: {e}"
                    self.logger.log_error(f"VAULT LOGIN ERROR: {e}")
                    wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)
                    speak("Login error")
        
        dlg.Destroy()
    
    def _vault_ensure_login(self):
        """Ensure user is logged in. Returns True if logged in."""
        if self.vault_logged_in:
            return True
        self._on_vault_login(None)
        return self.vault_logged_in
    
    def _on_vault_search(self, event, kind):
        """Search AudioVault"""
        if not self._vault_ensure_login():
            return
        
        dlg = wx.TextEntryDialog(self, f"Search {kind}:", f"Search AudioVault {kind.capitalize()}")
        if dlg.ShowModal() == wx.ID_OK:
            query = dlg.GetValue().strip()
            dlg.Destroy()
            if query:
                msg = f"Searching for {query}..."
                self.status_label.SetLabel(msg)
                speak(msg)
                
                # Search in background thread
                thread = threading.Thread(target=self._vault_search_thread, args=(query, kind), daemon=True)
                thread.start()
        else:
            dlg.Destroy()
    
    def _vault_voice_search(self, query, kind):
        """Search AudioVault directly from voice command with extracted query"""
        if not self._vault_ensure_login():
            return
        msg = f"Searching for {query}..."
        self.status_label.SetLabel(msg)
        speak(msg)
        thread = threading.Thread(target=self._vault_search_thread, args=(query, kind), daemon=True)
        thread.start()

    def _vault_voice_download(self, query, kind):
        """Voice download: search AudioVault for a named show/movie and
        download the top result in the background, with no checklist
        to pick from by hand. Honey asked for this 2026-11-23."""
        if not self._vault_ensure_login():
            return
        # Ashley, 2026-11-26: Samantha tells her in her own
        # recorded voice that she is downloading the show,
        # so Ashley hears it even with NVDA quiet on.
        self._play_sound_effect("samantha_downloading.wav")
        msg = f"Searching AudioVault for {query} to download..."
        self.status_label.SetLabel(msg)
        thread = threading.Thread(
            target=self._vault_voice_download_thread, args=(query, kind),
            daemon=True)
        thread.start()

    def _vault_voice_download_thread(self, query, kind):
        """Background thread for a voice download search"""
        try:
            results = av.search(query, kind=kind)
            wx.CallAfter(self._vault_voice_download_results, results, kind, query)
        except Exception as e:
            wx.CallAfter(self._vault_error, f"Search error: {e}")

    def _pick_best_voice_result(self, results, query):
        """Pick the exact show/movie Honey named, not the first
        alphabetical result. Honey asked 2026-11-23 that this work
        for every show she mentions, not just Friends.

        AudioVault search returns every title containing the words,
        in alphabetical order, so "friends" came back with
        "A Killer Among Friends" first and the real Friends seasons
        further down. This scores each result instead:
        exact title first, then a title starting with the name,
        then season 1 when no season was named, then a New
        Description version, then US over UK. Falls back to the
        first result when nothing matches at all.
        """
        import re
        if not results:
            return None
        q = (query or "").lower().strip()
        q = re.sub(r"\s+(?:us\s+)?new\s+description\s*$", "", q)
        q = re.sub(r"\s+(?:the\s+)?(?:sitcom|tv\s+show|tv\s+series)\s*$", "", q)
        q = re.sub(r"\s+(?:us\s+)?new\s+description\s*$", "", q)
        q = q.strip(" .,")
        if not q:
            return results[0]
        season_wanted = None
        m = re.search(r"season\s*0*(\d+)", q)
        if m:
            season_wanted = int(m.group(1))
            q = re.sub(r"\s*season\s*0*\d+\s*", " ", q).strip()
        best = None
        best_score = -1
        for result in results:
            name = (result[1] or "").lower()
            score = 0
            base = re.split(r"\s+-\s+season|\s+-\s+|\s*\(", name, 1)[0].strip()
            if base == q:
                score += 100
            elif name.startswith(q + " -"):
                score += 80
            elif name.startswith(q + " "):
                score += 40
            elif q in name:
                score += 10
            else:
                continue
            sm = re.search(r"season\s*0*(\d+)", name)
            if sm:
                season = int(sm.group(1))
                if season_wanted is not None:
                    score += 50 if season == season_wanted else -20
                elif season == 1:
                    score += 30
                else:
                    score -= season
            if "new description" in name:
                score += 20
            if "[us" in name:
                score += 5
            if score > best_score:
                best_score = score
                best = result
        return best if best is not None else results[0]

    def _exact_show_results(self, results, query):
        """Only the actual show Honey named, or None.

        Honey, 2026-11-23: a voice search should find the actual
        show she asks for, not every title containing the words.
        "friends" used to come back with 54 results, starting
        with "A Killer Among Friends". If any result's base title
        is exactly the name she said, return only those results
        - all seasons of that exact show, season 1 first, or
        only the season she named - and nothing else.
        """
        import re
        if not results or not query:
            return None
        q = (query or "").lower().strip()
        q = re.sub(r"\s+(?:us\s+)?new\s+description\s*$", "", q)
        q = re.sub(r"\s+(?:the\s+)?(?:sitcom|tv\s+show|tv\s+series)\s*$", "", q)
        q = re.sub(r"\s+(?:us\s+)?new\s+description\s*$", "", q)
        q = q.strip(" .,")
        if not q:
            return None
        season_wanted = None
        m = re.search(r"season\s*0*(\d+)", q)
        if m:
            season_wanted = int(m.group(1))
            q = re.sub(r"\s*season\s*0*\d+\s*", " ", q).strip()
        exact = []
        for result in results:
            name = (result[1] or "").lower()
            base = re.split(r"\s+-\s+season|\s+-\s+|\s*\(", name, 1)[0].strip()
            if base != q:
                continue
            if season_wanted is not None:
                sm = re.search(r"season\s*0*(\d+)", name)
                if not sm or int(sm.group(1)) != season_wanted:
                    continue
            exact.append(result)
        if not exact:
            return None
        def _season_key(result):
            sm = re.search(r"season\s*0*(\d+)", (result[1] or "").lower())
            return int(sm.group(1)) if sm else 0
        exact.sort(key=_season_key)
        return exact

    def _vault_voice_download_results(self, results, kind, query):
        """Queue the best AudioVault result for a voice download"""
        if not results:
            msg = f"I could not find {query} on AudioVault."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        self._queue_voice_download(
            self._pick_best_voice_result(results, query), kind)

    def _vault_voice_download_first(self):
        """Download the first result from the last voice/menu search.
        Used by "Samantha, download it" after Honey has heard the results.
        If the last search was on YouTube, download that first
        YouTube result instead of an AudioVault one."""
        if getattr(self, "_last_search_source", "audiovault") == "youtube":
            yt_results = getattr(self, "_last_yt_search_results", None) or []
            if yt_results:
                self._queue_yt_voice_download(yt_results[0])
                return
        results = getattr(self, "_last_search_results", None) or []
        if not results:
            msg = "There is no search to download from yet. Search for a show first."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        kind = getattr(self, "_last_search_kind", "shows")
        query = getattr(self, "_last_search_query", "") or ""
        best = self._pick_best_voice_result(results, query) if query else results[0]
        self._queue_voice_download(best, kind)

    # ---- YouTube voice search and download ----
    # Mirrors the AudioVault voice flow above: search by voice, hear
    # the first few titles, then "download it" for the first one, or
    # "download X from YouTube" to download the top result straight
    # away. Honey asked for this 2026-11-23.

    def _yt_voice_search(self, query):
        """Search YouTube directly from a voice command."""
        if not YT_AVAILABLE:
            msg = "YouTube is not available right now."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        msg = f"Searching YouTube for {query}..."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
        thread = threading.Thread(
            target=self._yt_voice_search_thread, args=(query,), daemon=True)
        thread.start()

    def _yt_voice_search_thread(self, query):
        """Background thread for a voice YouTube search."""
        try:
            results = yt.search(query)
            wx.CallAfter(self._yt_voice_search_results, results, query)
        except Exception as e:
            wx.CallAfter(self._yt_error_dialog, f"YouTube search error:\n\n{e}")

    def _yt_voice_search_results(self, results, query):
        """Remember a voice YouTube search, then show the results."""
        if not results:
            msg = f"I could not find {query} on YouTube."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        # The actual video first: exact title, then a title
        # starting with the name she said, then the rest in
        # YouTube's own order. "download it" downloads the first
        # one, so it should be the actual one she asked for.
        q = (query or "").lower().strip()
        if q:
            def _yt_rank(r):
                t = (r.get("title") or "").lower().strip()
                if t == q:
                    return 0
                if t.startswith(q):
                    return 1
                if q in t:
                    return 2
                return 3
            results = sorted(results, key=_yt_rank)
        self._last_yt_search_results = list(results)
        self._last_search_source = "youtube"
        # _yt_show_results speaks the first few titles and shows the
        # checklist, so Honey can pick from the list or say
        # "download it" for the first one.
        self._yt_show_results(results)

    def _yt_voice_download(self, query):
        """Voice download: search YouTube for a named video and
        download the top result in the background, with no checklist
        to pick from by hand."""
        if not YT_AVAILABLE:
            msg = "YouTube is not available right now."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        # Ashley, 2026-11-26: Samantha tells her in her own
        # recorded voice that she is downloading the show.
        self._play_sound_effect("samantha_downloading.wav")
        msg = f"Searching YouTube for {query} to download..."
        self.status_label.SetLabel(msg)
        thread = threading.Thread(
            target=self._yt_voice_download_thread, args=(query,),
            daemon=True)
        thread.start()

    def _yt_voice_download_thread(self, query):
        """Background thread for a voice YouTube download search."""
        try:
            results = yt.search(query)
            wx.CallAfter(self._yt_voice_download_results, results, query)
        except Exception as e:
            wx.CallAfter(self._yt_error_dialog, f"YouTube search error:\n\n{e}")

    def _yt_voice_download_results(self, results, query):
        """Queue the top YouTube result for a voice download."""
        if not results:
            msg = f"I could not find {query} on YouTube."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        self._queue_yt_voice_download(results[0])

    def _queue_yt_voice_download(self, result):
        """Queue one YouTube result for a background download, with
        no pop-up. The existing YouTube queue and progress reporting
        are reused, so Download Status and Cancel Downloads work
        for it just as they do for a menu download."""
        title = result.get("title", "Unknown")
        url = result.get("url", "")
        if not url:
            msg = f"I could not download {title} from YouTube."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        # Honey, 2026-11-23: a voice YouTube download goes in
        # its own folder named after the show, so a channel can be
        # made from it when the download finishes.
        import audiovault_client as _av
        subfolder = _av.sanitize_filename(self._suggest_channel_name(title))
        dest = yt.load_download_dir()
        if subfolder:
            dest = os.path.join(dest, subfolder)
        os.makedirs(dest, exist_ok=True)
        self._yt_download_queue = [(title, url)]
        self._yt_download_dest = dest
        self._yt_download_idx = 0
        self._yt_download_subfolder = subfolder if subfolder else None
        # Voice downloads make their channel by themselves,
        # with no pop-up question.
        self._auto_create_channel = True
        self._bg_cancel_requested = False
        self._yt_cancel_requested = False
        self._bg_yt_percent = 0
        msg = f"Downloading {title} from YouTube in the background."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
        self._yt_download_next()

    def _queue_voice_download(self, result, kind):
        """Queue one AudioVault result for a background download, with
        no pop-up. Puts it in its own subfolder, named after the show,
        so a channel can be offered from it afterwards, as with a
        single download picked from the results list."""
        av_id, name, link = result
        dest = av.load_download_dir(kind=kind)
        subfolder = av.sanitize_filename(self._suggest_channel_name(name))
        if subfolder:
            dest = os.path.join(dest, subfolder)
            self.download_subfolder = subfolder
        else:
            self.download_subfolder = None
        os.makedirs(dest, exist_ok=True)
        self.download_queue = [(name, link)]
        self.download_create_channel = False
        # Honey, 2026-11-23: a voice download makes its channel
        # by itself when it finishes, with no pop-up question.
        self._auto_create_channel = True
        self.download_dest = dest
        self.download_queue_index = 0
        self._bg_cancel_requested = False
        self._bg_vault_percent = 0
        msg = f"Downloading {name} in the background."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
        self._vault_download_next()

    def _vault_search_thread(self, query, kind):
        """Background thread for search.

        Honey, 2026-11-23: a voice search should do live shows
        too, as well as AudioVault search and download. So this
        also looks for live channels with the same name, and
        _vault_show_results speaks them first. A live lookup
        failure never blocks the AudioVault results.
        """
        self._last_search_query = query
        live_results = []
        try:
            if LIVETV_AVAILABLE and livetv is not None:
                try:
                    livetv.refresh_catalog()
                    live_results = livetv.search_channels(query) or []
                except Exception:
                    live_results = []
        except Exception:
            live_results = []
        self._last_live_search_results = list(live_results)
        try:
            results = av.search(query, kind=kind)
            wx.CallAfter(self._vault_show_results, results, kind,
                         live_results)
        except Exception as e:
            wx.CallAfter(self._vault_error, f"Search error: {e}")
    
    def _on_vault_recents(self, event, kind):
        """View recent additions"""
        if not self._vault_ensure_login():
            return
        
        msg = f"Loading recent {kind}..."
        self.status_label.SetLabel(msg)
        speak(msg)
        
        thread = threading.Thread(target=self._vault_recents_thread, args=(kind,), daemon=True)
        thread.start()
    
    def _vault_recents_thread(self, kind):
        """Background thread for recents"""
        self._last_search_query = ""
        try:
            results = av.get_recents(kind)
            wx.CallAfter(self._vault_show_results, results, kind)
        except Exception as e:
            wx.CallAfter(self._vault_error, f"Error loading recents: {e}")
    
    # ---- Background downloads: status and cancel ----
    def _bg_download_status_text(self):
        """Plain-words status of any downloads running in the background.

        Reads the Audio Vault and YouTube queues only; it never starts,
        stops or changes a download, so it is safe to call any time,
        including while something is playing.
        """
        parts = []
        queue = getattr(self, "download_queue", None) or []
        idx = getattr(self, "download_queue_index", 0)
        if idx < len(queue):
            name = queue[idx][0]
            waiting = len(queue) - idx - 1
            text = (f"Audio Vault is downloading {name} in the background, "
                    f"{getattr(self, '_bg_vault_percent', 0):.0f} percent done")
            if waiting:
                text += f", with {waiting} more waiting"
            parts.append(text)
        yt_queue = getattr(self, "_yt_download_queue", None) or []
        yt_idx = getattr(self, "_yt_download_idx", 0)
        if yt_idx < len(yt_queue):
            title = yt_queue[yt_idx][0]
            waiting = len(yt_queue) - yt_idx - 1
            text = (f"YouTube is downloading {title} in the background, "
                    f"{getattr(self, '_bg_yt_percent', 0):.0f} percent done")
            if waiting:
                text += f", with {waiting} more waiting"
            parts.append(text)
        if not parts:
            return "No downloads are running right now."
        return ". ".join(parts) + ". You can keep listening while they download."

    def _on_download_status(self, event=None):
        """Speak (and show) what is downloading in the background."""
        msg = self._bg_download_status_text()
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")

    def _on_cancel_downloads(self, event=None):
        """Stop any background downloads.

        Sets the cancel flag the download threads check, and clears both
        queues so nothing new starts. The download already in progress
        stops shortly after, on its own, and says so out loud.
        """
        self._bg_cancel_requested = True
        self._yt_cancel_requested = True
        if getattr(self, "download_queue", None):
            self.download_queue_index = len(self.download_queue)
        if getattr(self, "_yt_download_queue", None):
            self._yt_download_idx = len(self._yt_download_queue)
        msg = "Cancelling downloads. The one already downloading will stop shortly."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)

    def _vault_show_results(self, results, kind, live_results=None):
        """Show search/recent results and allow multiple downloads"""
        # Remember these for a voice "download it" afterwards.
        self._last_search_results = list(results) if results else []
        self._last_search_kind = kind
        self._last_search_source = "audiovault"
        if not results:
            msg = "No results found"
            self.status_label.SetLabel(msg)
            speak(msg)
            return

        # Put the exact show Honey named first, for every show, so
        # the first names she hears are the right show, not the
        # first alphabetical title containing the words.
        query = getattr(self, "_last_search_query", "") or ""
        exact_only = False
        if query:
            # The actual show first: if she named a show exactly,
            # show only that show, so "A Killer Among Friends"
            # never comes up when she asked for Friends.
            exact = self._exact_show_results(results, query)
            if exact:
                results = exact
                self._last_search_results = list(results)
                exact_only = True
            else:
                best = self._pick_best_voice_result(results, query)
                if best is not None and best is not results[0]:
                    results = [best] + [r for r in results if r is not best]
                    self._last_search_results = list(results)

        items = [f"{name} ({av_id})" for av_id, name, link in results]
        # Speak the first few names, so Honey can hear them without
        # navigating the checklist, then say "download it" for the
        # first one, or pick from the list as before.
        spoken_names = "; ".join(
            f"{i + 1}. {name}" for i, (_, name, _) in enumerate(results[:3]))
        if exact_only:
            msg = (f"Found the actual show you asked for. "
                   f"{spoken_names}.")
        else:
            msg = f"Found {len(items)} results. {spoken_names}."
        # Live shows found by the same voice search, spoken first
        # so Honey hears them too. Say "play <name> live" to
        # watch one live; "download it" still downloads the first
        # AudioVault result, not a live channel.
        live_results = live_results or getattr(
            self, "_last_live_search_results", None) or []
        if live_results:
            live_names = "; ".join(
                c["name"] for c in live_results[:3])
            msg = (f"Found live too: {live_names}. "
                   f"Say play one of those live to watch it live. " + msg)
        self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
        
        # Custom dialog with CheckListBox for NVDA accessibility
        dlg = wx.Dialog(self, title="AudioVault Results", size=(500, 400))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        
        sizer.Add(wx.StaticText(panel, label=f"Check items to download ({len(items)} results):"), 0, wx.ALL, 5)
        
        checklist = wx.CheckListBox(panel, choices=items)
        sizer.Add(checklist, 1, wx.ALL | wx.EXPAND, 5)
        
        # Select All / Deselect All buttons
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        select_all_btn = wx.Button(panel, label="Select All")
        deselect_all_btn = wx.Button(panel, label="Deselect All")
        select_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, True) for i in range(len(items))])
        deselect_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, False) for i in range(len(items))])
        btn_row.Add(select_all_btn, 0, wx.ALL, 5)
        btn_row.Add(deselect_all_btn, 0, wx.ALL, 5)
        sizer.Add(btn_row, 0, wx.ALIGN_CENTER)
        
        # OK / Cancel
        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Download")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        panel.SetSizer(sizer)
        checklist.SetFocus()
        
        if dlg.ShowModal() == wx.ID_OK:
            selections = [i for i in range(len(items)) if checklist.IsChecked(i)]
            dlg.Destroy()
            if not selections:
                return
            
            # Use kind-specific default folder
            dest = av.load_download_dir(kind=kind)
            os.makedirs(dest, exist_ok=True)
            
            self.download_queue = [(results[i][1], results[i][2]) for i in selections]
            self.download_create_channel = False
            self.download_subfolder = None
            self._bg_cancel_requested = False
            self._bg_vault_percent = 0
            
            # If multiple items, offer subfolder grouping
            if len(selections) > 1:
                result = wx.MessageBox(
                    "Put all selected items into their own subfolder?",
                    "Group Downloads",
                    wx.YES_NO | wx.ICON_QUESTION
                )
                if result == wx.YES:
                    name_dlg = wx.TextEntryDialog(self, "Name for the subfolder:", "Subfolder Name")
                    if name_dlg.ShowModal() == wx.ID_OK:
                        subfolder = name_dlg.GetValue().strip()
                        name_dlg.Destroy()
                        if subfolder:
                            dest = os.path.join(dest, subfolder)
                            os.makedirs(dest, exist_ok=True)
                            self.download_subfolder = subfolder
                    else:
                        name_dlg.Destroy()
            else:
                # Single item: still give it its own subfolder so we can offer
                # to make a channel from it. Default the name to the show name
                # (with the season/year suffix trimmed off), editable by the user.
                single_name = results[selections[0]][1]
                suggested = self._suggest_channel_name(single_name)
                name_dlg = wx.TextEntryDialog(
                    self,
                    "Folder/channel name for this download:",
                    "Create Channel",
                    suggested
                )
                if name_dlg.ShowModal() == wx.ID_OK:
                    subfolder = name_dlg.GetValue().strip()
                    name_dlg.Destroy()
                    if subfolder:
                        subfolder = av.sanitize_filename(subfolder)
                        dest = os.path.join(dest, subfolder)
                        os.makedirs(dest, exist_ok=True)
                        self.download_subfolder = subfolder
                else:
                    name_dlg.Destroy()
            
            self.download_dest = dest
            self.download_queue_index = 0
            self._answer_in_samantha_voice(f"Queued {len(self.download_queue)} downloads")
            self._vault_download_next()
        else:
            dlg.Destroy()

    def _suggest_channel_name(self, name):
        """Derive a clean show name from a season title for use as a channel name.
        e.g. 'Law and Order - Season 23 (2024)' -> 'Law and Order'."""
        import re
        cleaned = name
        # Strip a trailing year in parentheses, e.g. "(2024)"
        cleaned = re.sub(r"\s*\(\d{4}\)\s*$", "", cleaned)
        # Strip trailing "- Season N" / "Season N" / "- S01" style suffixes
        cleaned = re.sub(r"\s*[-–]?\s*Season\s*\d+\s*$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*[-–]?\s*S\d{1,2}\s*$", "", cleaned, flags=re.IGNORECASE)
        # Strip trailing bracketed notes like "[Not Described]"
        cleaned = re.sub(r"\s*\[[^\]]*\]\s*$", "", cleaned)
        cleaned = cleaned.strip(" -–")
        return cleaned if cleaned else name
    
    def _vault_start_download(self, name, download_url):
        """Start downloading a single file"""
        default_dir = av.load_download_dir()
        os.makedirs(default_dir, exist_ok=True)
        dlg = wx.DirDialog(self, "Choose download folder", default_dir)
        if dlg.ShowModal() == wx.ID_OK:
            dest = dlg.GetPath()
            dlg.Destroy()
            av.save_download_dir(dest)
            self.download_queue = [(name, download_url)]
            self.download_dest = dest
            self.download_queue_index = 0
            self._bg_cancel_requested = False
            self._bg_vault_percent = 0
            self._vault_download_next()
        else:
            dlg.Destroy()
    
    def _vault_already_downloaded(self, name):
        """Return True if this item was already downloaded & extracted in a
        previous run (its extraction folder exists and contains MP3 files).
        Used to skip completed items when retrying a failed batch."""
        try:
            dest = self.download_dest
            if not dest:
                return False
            safe_name = av.sanitize_filename(name)
            # _vault_extract_zip extracts into <dest>/<safe_name>
            extract_dir = os.path.join(dest, safe_name)
            if os.path.isdir(extract_dir):
                for root, dirs, files in os.walk(extract_dir):
                    if any(f.lower().endswith('.mp3') for f in files):
                        return True
            return False
        except Exception:
            return False

    def _vault_download_next(self):
        """Download next item in queue, in the background.

        Returns right away after starting the worker thread: there is no
        pop-up window any more, so playback, Live TV and the menus keep
        working while the download runs. Progress is shown in the status
        line and can be heard with Download Status.
        """
        if self.download_queue_index >= len(self.download_queue):
            total = len(self.download_queue)
            if getattr(self, "_bg_cancel_requested", False):
                self._bg_cancel_requested = False
                msg = "Downloads cancelled"
                self.status_label.SetLabel(msg)
                speak(msg)
                return
            msg = f"All {total} download(s) complete"
            self.status_label.SetLabel(msg)
            speak(msg)

            # If enabled, free local disk space by making the downloaded files
            # online-only in OneDrive (they stay playable, download on demand).
            self._maybe_free_up_space(self.download_dest)

            # Voice downloads make their channel by themselves,
            # with no pop-up question. Anything else still gets
            # the Yes/No offer, as before.
            if getattr(self, "_auto_create_channel", False):
                self._auto_create_channel = False
                if self.download_subfolder:
                    self._create_channel_from_download(
                        self.download_subfolder, self.download_dest,
                        source="VAULT")
            elif self.download_subfolder:
                self._vault_offer_channel_creation()
            return

        name, url = self.download_queue[self.download_queue_index]
        current = self.download_queue_index + 1
        total = len(self.download_queue)

        # Skip items that were already successfully downloaded & extracted in a
        # previous run, so retrying a failed batch only fetches what's missing.
        if self._vault_already_downloaded(name):
            self.logger.log_channel("VAULT", "SKIP", f"Already downloaded: {name}")
            self.status_label.SetLabel(f"Already downloaded, skipping: {name}")
            speak(f"Already have {name}, skipping")
            self.download_queue_index += 1
            # Move to the next item immediately
            wx.CallLater(50, self._vault_download_next)
            return

        # No pop-up window: the download runs in the background and the
        # status line shows its progress instead.
        self.download_progress = None
        self._bg_vault_percent = 0
        self.status_label.SetLabel(f"Downloading in the background ({current}/{total}): {name}")
        if current == 1:
            speak(f"Downloading {current} of {total}: {name}. Downloading in the background, so you can keep listening.")
        else:
            speak(f"Downloading {current} of {total}: {name}")

        thread = threading.Thread(
            target=self._vault_download_thread,
            args=(name, url, self.download_dest),
            daemon=True
        )
        thread.start()
    
    def _vault_download_thread(self, name, download_url, destination, _retry=False):
        """Background thread for download"""
        try:
            self.logger.log_channel("VAULT", "DOWNLOAD", f"Starting download: {name} from {download_url} to {destination}")

            # Verify the destination drive is actually connected and writable
            # before we start. External drives (e.g. D:) sometimes disconnect.
            drive_ok, drive_msg = self._check_destination_writable(destination)
            if not drive_ok:
                self.logger.log_error(f"VAULT DOWNLOAD ABORTED: {drive_msg}")
                wx.CallAfter(self._vault_download_failed, drive_msg)
                return

            def progress(percent, total_size, filename):
                if getattr(self, "_bg_cancel_requested", False):
                    raise _BackgroundDownloadCancelled()
                self._bg_vault_percent = percent
                wx.CallAfter(self._vault_update_progress, percent, total_size, filename)

            filepath = av.download(download_url, destination=destination, progress_callback=progress)

            if filepath:
                self.logger.log_channel("VAULT", "DOWNLOAD", f"Complete: {filepath}")
                # Extract ZIPs here, in this background thread, so a big
                # extraction does not freeze playback or the menus either.
                # Only plain file work happens here; the spoken result is
                # given on the main thread by _vault_download_complete.
                extracted = None
                if filepath.lower().endswith('.zip'):
                    extracted = self._vault_extract_zip_files(name, filepath)
                wx.CallAfter(self._vault_download_complete, name, filepath, extracted)
            else:
                self.logger.log_error(f"VAULT DOWNLOAD FAILED: {name} - returned None")
                self.vault_logged_in = False
                wx.CallAfter(self._vault_download_failed, f"Download failed for {name}. Session may have expired.")
        except _BackgroundDownloadCancelled:
            self.logger.log_channel("VAULT", "CANCEL", f"Download cancelled: {name}")
            self._cleanup_partial_download(name, destination)
            wx.CallAfter(self._vault_download_cancelled)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.logger.log_error(f"VAULT DOWNLOAD ERROR: {name} - {e}")
            self.logger.log_error(f"VAULT DOWNLOAD TRACEBACK: {tb}")
            # Clean up any partial .zip left behind by the failed write
            self._cleanup_partial_download(name, destination)

            # If this failed because the disk is full, automatically free up
            # space (make OneDrive files online-only) and retry once.
            if self._is_low_disk_error(e) and not _retry:
                self.logger.log_error("VAULT DOWNLOAD: low disk space — attempting auto free-up-space then retry")
                wx.CallAfter(self.status_label.SetLabel, "Disk full — freeing up space and retrying...")
                speak("Disk is full. Freeing up space and trying again.")
                freed = self._free_up_space_all_onedrive()
                self.logger.log_playback("CLOUD", f"Auto free-up before retry freed: {freed}")
                # Retry the same download once
                self._vault_download_thread(name, download_url, destination, _retry=True)
                return

            # Give a plain-English message for the common drive/network faults
            friendly = self._explain_download_error(e, destination)
            if self._is_low_disk_error(e) and _retry:
                friendly = ("Still out of disk space after freeing up room. Your drive is full. "
                            "Delete some files or move your download folder into OneDrive so it can "
                            "be made online-only.")
            wx.CallAfter(self._vault_download_failed, friendly)

    def _is_low_disk_error(self, e):
        """Detect whether an exception indicates the disk ran out of space."""
        text = str(e).lower()
        markers = [
            "no space left",          # Linux/general
            "errno 28",               # ENOSPC
            "not enough space",       # Windows
            "disk is full",
            "there is not enough space on the disk",
            "winerror 112",           # ERROR_DISK_FULL
        ]
        return any(m in text for m in markers)

    def _free_up_space_all_onedrive(self):
        """Run free-up-space on all configured download folders that live in
        OneDrive. Returns a short summary string for logging."""
        folders = set()
        try:
            folders.add(av.load_download_dir(kind="movies"))
            folders.add(av.load_download_dir(kind="shows"))
            folders.add(av.load_download_dir())
        except Exception:
            pass
        try:
            folders.add(yt.load_download_dir())
        except Exception:
            pass
        results = []
        for folder in folders:
            if folder and os.path.isdir(folder):
                ok, msg = self._free_up_space(folder)
                results.append(f"{folder}: {'ok' if ok else msg}")
        return "; ".join(results) if results else "no folders"

    def _check_destination_writable(self, destination):
        """Return (ok, message). Verifies the destination drive exists and we
        can write to it — catches a disconnected external drive early."""
        try:
            # Check the drive root (e.g. 'D:\\') exists
            drive = os.path.splitdrive(os.path.abspath(destination))[0]
            if drive and not os.path.exists(drive + os.sep):
                return False, (f"The {drive} drive is not available. Please check that your "
                               f"external drive is plugged in and powered on, then try again.")
            os.makedirs(destination, exist_ok=True)
            # Try an actual tiny write to confirm the drive accepts writes
            test_file = os.path.join(destination, ".write_test.tmp")
            with open(test_file, "wb") as f:
                f.write(b"ok")
            os.remove(test_file)
            return True, ""
        except Exception as e:
            drive = os.path.splitdrive(os.path.abspath(destination))[0] or "the download"
            return False, (f"Cannot write to {drive} drive ({e}). The external drive may be "
                           f"disconnected or full. Please check it and try again.")

    def _cleanup_partial_download(self, name, destination):
        """Remove a partial/corrupt .zip left behind by a failed download."""
        try:
            safe_name = av.sanitize_filename(name)
            for candidate in (name, safe_name):
                p = os.path.join(destination, f"{candidate}.zip")
                if os.path.exists(p):
                    os.remove(p)
                    self.logger.log_channel("VAULT", "CLEANUP", f"Removed partial file: {p}")
        except Exception:
            pass

    def _explain_download_error(self, e, destination):
        """Turn a raw exception into a clear message for common drive/network faults."""
        text = str(e)
        drive = os.path.splitdrive(os.path.abspath(destination))[0] or "the drive"
        if "10054" in text or "Connection broken" in text or "forcibly closed" in text:
            return ("The download was interrupted by a network drop. Check your internet "
                    "connection and try again.")
        if "Errno 22" in text or "WinError 3" in text or "cannot find the path" in text:
            return (f"The {drive} drive became unavailable during the download. External drives "
                    f"can disconnect if the cable is loose or the drive sleeps. Reconnect it and "
                    f"try again.")
        if "No space" in text or "28" in text and "Errno" in text:
            return f"The {drive} drive is out of space. Free up space and try again."
        return f"Download error: {e}"
    
    def _vault_update_progress(self, percent, total_size, filename):
        """Show background download progress in the status line only.

        There is no pop-up window any more, and nothing is spoken here:
        speaking every percent would talk over whatever Honey is
        listening to. Start, finish and failure are spoken instead.
        """
        self._bg_vault_percent = percent
        current = self.download_queue_index + 1
        total = len(self.download_queue)
        msg = f"Downloading in the background ({current}/{total}) {filename}: {percent:.0f}% of {av.bytes2human(total_size)}"
        self.status_label.SetLabel(msg)

    def _vault_download_cancelled(self):
        """A background Audio Vault download was cancelled by Honey."""
        self.download_progress = None
        self._bg_cancel_requested = False
        self.status_label.SetLabel("Download cancelled")
        speak("Download cancelled")

    def _vault_download_complete(self, name, filepath, extracted=None):
        """Handle completed download, extract if ZIP, move to next in queue.

        `extracted` is True/False when the background thread already
        extracted a ZIP; None means no ZIP was involved (or an older
        caller did not extract yet, in which case extract here).
        """
        self.download_progress = None

        # Check if ZIP and extract
        if filepath and filepath.lower().endswith('.zip'):
            if extracted is None:
                extracted = self._vault_extract_zip(name, filepath)
            if extracted:
                msg = f"Extracted: {name}"
            else:
                msg = f"Downloaded (extraction failed): {name}"
        else:
            msg = f"Downloaded: {name}"

        self.status_label.SetLabel(msg)
        speak(msg)
        self.download_queue_index += 1

        # Download next in queue
        self._vault_download_next()
    
    def _vault_extract_zip_files(self, name, zip_path):
        """Filesystem-only ZIP extraction. Returns True on success.

        No speaking and no window updates happen here, so it is safe to
        call from the background download thread. The spoken result is
        given by _vault_download_complete on the main thread.
        """
        import zipfile
        import shutil

        try:
            if not zipfile.is_zipfile(zip_path):
                self.logger.log_error(f"VAULT: Not a valid ZIP: {zip_path}")
                return False

            # Extract to folder named after the show (sanitize illegal chars
            # like ':' so Windows doesn't reject the folder name)
            safe_name = av.sanitize_filename(name)
            extract_dir = os.path.join(os.path.dirname(zip_path), safe_name)
            os.makedirs(extract_dir, exist_ok=True)

            self.logger.log_channel("VAULT", "EXTRACT", f"Extracting {zip_path} to {extract_dir}")

            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)

            # Handle nested ZIPs
            for root, dirs, files in os.walk(extract_dir):
                for f in files:
                    nested_path = os.path.join(root, f)
                    if f.lower().endswith('.zip') and zipfile.is_zipfile(nested_path):
                        nested_dir = os.path.splitext(nested_path)[0]
                        os.makedirs(nested_dir, exist_ok=True)
                        with zipfile.ZipFile(nested_path, 'r') as nzf:
                            nzf.extractall(nested_dir)
                        os.remove(nested_path)

            # Flatten duplicate nested folders (e.g., Season 1/Season 1/ -> Season 1/)
            for root, dirs, files in os.walk(extract_dir, topdown=False):
                for d in dirs:
                    dir_path = os.path.join(root, d)
                    contents = os.listdir(dir_path)
                    if len(contents) == 1:
                        inner = os.path.join(dir_path, contents[0])
                        if os.path.isdir(inner):
                            # Flatten if same name OR inner folder name contains parent name
                            if contents[0] == d or contents[0].lower().startswith(d.lower()) or d.lower().startswith(contents[0].lower()):
                                for item in os.listdir(inner):
                                    shutil.move(os.path.join(inner, item), dir_path)
                                os.rmdir(inner)
                                self.logger.log_channel("VAULT", "EXTRACT", f"Flattened: {d}/{contents[0]}")

            # Delete original ZIP
            os.remove(zip_path)

            self.logger.log_channel("VAULT", "EXTRACT", f"Extraction complete: {extract_dir}")
            return True

        except Exception as e:
            self.logger.log_error(f"VAULT EXTRACT ERROR: {name} - {e}")
            return False

    def _vault_extract_zip(self, name, zip_path):
        """Extract ZIP file on the main thread, speaking the result.

        Kept for callers that run on the main thread; the background
        download thread uses _vault_extract_zip_files instead.
        """
        self.status_label.SetLabel(f"Extracting: {name}...")
        speak(f"Extracting {name}")
        ok = self._vault_extract_zip_files(name, zip_path)
        if ok:
            speak(f"Extracted {name}")
        else:
            speak("Extraction failed")
        return ok
    
    def _vault_offer_channel_creation(self):
        """Offer to create a channel from downloaded content"""
        result = wx.MessageBox(
            f"Create a channel '{self.download_subfolder}' from the downloaded files?",
            "Create Channel",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result != wx.YES:
            return
        
        channel_name = self.download_subfolder
        dest = self.download_dest
        
        # Flatten any double-nested folders before scanning
        import shutil
        for root, dirs, files in os.walk(dest, topdown=False):
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    contents = os.listdir(dir_path)
                    if len(contents) == 1:
                        inner = os.path.join(dir_path, contents[0])
                        if os.path.isdir(inner):
                            if contents[0] == d or contents[0].lower().startswith(d.lower()) or d.lower().startswith(contents[0].lower()):
                                for item in os.listdir(inner):
                                    shutil.move(os.path.join(inner, item), dir_path)
                                os.rmdir(inner)
                except Exception:
                    pass
        
        # Find all folders with MP3 files at any depth, sorted naturally
        from playlist_manager import natural_sort_key
        folders = []
        
        for root, dirs, files in os.walk(dest):
            dirs.sort(key=natural_sort_key)
            mp3s = [f for f in files if f.lower().endswith('.mp3')]
            if mp3s:
                folders.append(root)
        
        if not folders:
            wx.MessageBox("No MP3 files found in downloaded content.", "No Files", wx.OK | wx.ICON_WARNING)
            return
        
        # Handle existing channel
        if channel_name in self.channels.channels:
            choice = wx.MessageBox(
                f"Channel '{channel_name}' already exists.\n\nYes = Replace it\nNo = Add folders to it",
                "Channel Exists",
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
            )
            if choice == wx.CANCEL:
                return
            elif choice == wx.YES:
                # Replace - delete and recreate
                self.channels.delete_channel(channel_name)
                self.channels.create_channel(channel_name)
                self.channels.update_current_channel(folders=folders)
            else:
                # Add to existing
                existing = self.channels.channels[channel_name].get('folders', [])
                combined = existing + [f for f in folders if f not in existing]
                self.channels.switch_channel(channel_name)
                self.channels.update_current_channel(folders=combined)
        else:
            # Create new channel
            self.channels.create_channel(channel_name)
            self.channels.update_current_channel(folders=folders)
        
        # Load the channel
        self.playlist = PlaylistManager()
        self._load_current_channel()
        self._update_title()
        self._update_display()
        
        msg = f"Channel '{channel_name}' created with {len(folders)} folder(s)"
        self.status_label.SetLabel(msg)
        speak(msg)
        self.logger.log_channel("VAULT", "CHANNEL-CREATE", f"{channel_name} with {len(folders)} folders")
        self._start_playback()
    
    def _vault_download_failed(self, message):
        """Handle a failed download without stopping the whole queue.

        No pop-up window any more: the failure is spoken in plain words,
        shown in the status line, and the queue moves on to the next
        download so one bad item does not stall everything.
        """
        self.download_progress = None
        self.status_label.SetLabel(f"Download failed: {message}")
        speak(f"Sorry, that download did not work. {message} Moving on to the next one.")
        self.download_queue_index += 1
        self._vault_download_next()
    
    def _vault_error(self, message):
        """Handle AudioVault errors"""
        self.status_label.SetLabel(message)
        self._answer_in_samantha_voice(message, "samantha_reading_not_ready.wav")
    
    # ---- YouTube Methods ----

    def _on_yt_set_folder(self, event):
        """Set default YouTube download folder"""
        current = yt.load_download_dir()
        dlg = wx.DirDialog(self, "Set YouTube download folder", current)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            yt.save_download_dir(path)
            msg = f"YouTube download folder set to: {path}"
            self.status_label.SetLabel(msg)
            speak(msg)
        dlg.Destroy()

    def _on_yt_update(self, event):
        """Update yt-dlp to the latest version"""
        current_version = yt.get_ytdlp_version()
        self.status_label.SetLabel("Checking for updates...")
        speak("Checking for latest version")
        # Check latest version in background so the UI doesn't freeze
        threading.Thread(target=self._yt_check_version_thread, args=(current_version,), daemon=True).start()

    def _yt_check_version_thread(self, current_version):
        latest = yt.get_latest_ytdlp_version()
        wx.CallAfter(self._yt_prompt_update, current_version, latest)

    def _yt_prompt_update(self, current_version, latest_version):
        if latest_version:
            if yt.versions_match(current_version, latest_version):
                msg = f"YouTube downloader is already up to date (version {current_version})."
                self.status_label.SetLabel(msg)
                speak(msg)
                wx.MessageBox(msg, "Up To Date", wx.OK | wx.ICON_INFORMATION)
                return
            prompt = (
                f"Current version: {current_version}\n"
                f"Latest version:  {latest_version}\n\n"
                f"Update now? (Requires internet, may take a minute.)"
            )
        else:
            prompt = (
                f"Current version: {current_version}\n"
                f"Latest version:  could not be checked (no internet?)\n\n"
                f"Attempt update anyway?"
            )
        confirm = wx.MessageBox(prompt, "Update YouTube Downloader", wx.YES_NO | wx.ICON_QUESTION)
        if confirm != wx.YES:
            self.status_label.SetLabel("Update cancelled")
            return
        msg = "Updating YouTube downloader, please wait..."
        self.status_label.SetLabel(msg)
        speak(msg)
        self.logger.log_playback("YOUTUBE-UPDATE", f"Starting update from {current_version} to {latest_version}")
        threading.Thread(target=self._yt_update_thread, daemon=True).start()

    def _yt_update_thread(self):
        success, message = yt.update_ytdlp()
        wx.CallAfter(self._yt_update_done, success, message)

    def _yt_update_done(self, success, message):
        self.status_label.SetLabel(message)
        speak(message)
        self.logger.log_playback("YOUTUBE-UPDATE", f"Result: {message}")
        icon = wx.ICON_INFORMATION if success else wx.ICON_ERROR
        wx.MessageBox(message, "Update Complete" if success else "Update Failed", wx.OK | icon)

    def _on_yt_url(self, event):
        """Download from a YouTube URL"""
        dlg = wx.TextEntryDialog(self, "Paste YouTube URL:", "Download from URL")
        if dlg.ShowModal() == wx.ID_OK:
            url = dlg.GetValue().strip()
            dlg.Destroy()
            if url:
                msg = "Checking URL..."
                self.status_label.SetLabel(msg)
                speak(msg)
                threading.Thread(target=self._yt_detect_url_thread, args=(url,), daemon=True).start()
        else:
            dlg.Destroy()

    def _yt_detect_url_thread(self, url):
        try:
            info = yt.detect_url(url)
            wx.CallAfter(self._yt_handle_detected_url, url, info)
        except Exception as e:
            wx.CallAfter(self._yt_error, f"URL detection error: {e}")

    def _yt_handle_detected_url(self, url, info):
        dest = yt.load_download_dir()
        self._yt_download_subfolder = None

        if info["is_playlist"]:
            count = info["count"]
            title = info["title"]
            result = wx.MessageBox(
                f"This is a playlist: \"{title}\" ({count} items).\n\nDownload all {count} items?",
                "Playlist Detected",
                wx.YES_NO | wx.ICON_QUESTION
            )
            if result != wx.YES:
                return

            # Use playlist title as subfolder
            subfolder = "".join(c for c in title if c.isalnum() or c in " _-").strip()
            if subfolder:
                dest = os.path.join(dest, subfolder)
                os.makedirs(dest, exist_ok=True)
                self._yt_download_subfolder = subfolder

            self._yt_download_queue = [(e["title"], e["url"]) for e in info["entries"]]
        else:
            self._yt_download_queue = [(info["title"], url)]

        self._yt_download_dest = dest
        self._yt_download_idx = 0
        self._bg_cancel_requested = False
        self._bg_yt_percent = 0
        speak(f"Queued {len(self._yt_download_queue)} download{'s' if len(self._yt_download_queue) > 1 else ''}")
        self._yt_download_next()

    def _on_yt_search(self, event):
        """Search YouTube with options for full episodes and sorting."""
        dlg = wx.Dialog(self, title="YouTube Search", size=(440, 260))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(panel, label="Search YouTube:"), 0, wx.ALL, 8)
        query_ctrl = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        sizer.Add(query_ctrl, 0, wx.ALL | wx.EXPAND, 8)

        full_ep_cb = wx.CheckBox(panel, label="Full episodes only (hide short clips)")
        sizer.Add(full_ep_cb, 0, wx.ALL, 8)

        sizer.Add(wx.StaticText(panel, label="Sort results by:"), 0, wx.LEFT | wx.TOP, 8)
        sort_choice = wx.Choice(panel, choices=["Relevance (default)", "Longest first", "Shortest first"])
        sort_choice.SetSelection(0)
        sizer.Add(sort_choice, 0, wx.ALL | wx.EXPAND, 8)

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Search")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        panel.SetSizer(sizer)
        query_ctrl.SetFocus()
        query_ctrl.Bind(wx.EVT_TEXT_ENTER, lambda e: dlg.EndModal(wx.ID_OK))

        if dlg.ShowModal() == wx.ID_OK:
            query = query_ctrl.GetValue().strip()
            full_episodes = full_ep_cb.GetValue()
            sort_map = {0: "relevance", 1: "longest", 2: "shortest"}
            sort_by = sort_map.get(sort_choice.GetSelection(), "relevance")
            dlg.Destroy()
            if query:
                extra = " (full episodes only)" if full_episodes else ""
                msg = f"Searching YouTube for {query}{extra}..."
                self.status_label.SetLabel(msg)
                speak(msg)
                threading.Thread(
                    target=self._yt_search_thread,
                    args=(query, full_episodes, sort_by),
                    daemon=True
                ).start()
        else:
            dlg.Destroy()

    def _yt_search_thread(self, query, full_episodes_only=False, sort_by="relevance"):
        self.logger.log_playback("YOUTUBE", f"Search start: query='{query}' full_only={full_episodes_only} sort={sort_by}")
        try:
            results = yt.search(query, full_episodes_only=full_episodes_only, sort_by=sort_by)
            self.logger.log_playback("YOUTUBE", f"Search returned {len(results) if results else 0} result(s)")
            if not results:
                if full_episodes_only:
                    wx.CallAfter(self._yt_error_dialog,
                        f"No full episodes found for '{query}'. Try unchecking "
                        f"'Full episodes only' to see shorter videos.")
                else:
                    wx.CallAfter(self._yt_error_dialog,
                        f"No results found for '{query}'. YouTube may be temporarily blocking "
                        f"searches, or the downloader needs updating (YouTube menu > Update "
                        f"YouTube Downloader).")
                return
            wx.CallAfter(self._yt_show_results, results)
        except Exception as e:
            self.logger.log_error(f"YOUTUBE: Search error for '{query}': {e}")
            wx.CallAfter(self._yt_error_dialog, f"YouTube search error:\n\n{e}")

    def _yt_error_dialog(self, message):
        """Show a visible error dialog (not just a spoken status line, which
        can be missed) and speak it, for YouTube problems."""
        self.status_label.SetLabel(message)
        self._answer_in_samantha_voice(message, "samantha_reading_not_ready.wav")
        self.logger.log_error(f"YOUTUBE: {message}")
        wx.MessageBox(message, "YouTube", wx.OK | wx.ICON_WARNING)


    def _yt_show_results(self, results):
        if not results:
            self._yt_error_dialog("No results found.")
            return

        items = [f"{r['title']} [{r['duration']}] - {r['channel']}" for r in results]
        # Remember these for a voice "download it" afterwards, and
        # speak the first few titles, as the AudioVault results do.
        self._last_yt_search_results = list(results)
        self._last_search_source = "youtube"
        spoken_names = "; ".join(
            f"{i + 1}. {r['title']}" for i, r in enumerate(results[:3]))
        self._answer_in_samantha_voice(f"Found {len(items)} results. {spoken_names}.", "samantha_reading_not_ready.wav")

        dlg = wx.Dialog(self, title="YouTube Results", size=(600, 400))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)

        sizer.Add(wx.StaticText(panel, label=f"Check items to download ({len(items)} results):"), 0, wx.ALL, 5)
        checklist = wx.CheckListBox(panel, choices=items)
        sizer.Add(checklist, 1, wx.ALL | wx.EXPAND, 5)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        select_all_btn = wx.Button(panel, label="Select All")
        deselect_all_btn = wx.Button(panel, label="Deselect All")
        select_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, True) for i in range(len(items))])
        deselect_all_btn.Bind(wx.EVT_BUTTON, lambda e: [checklist.Check(i, False) for i in range(len(items))])
        btn_row.Add(select_all_btn, 0, wx.ALL, 5)
        btn_row.Add(deselect_all_btn, 0, wx.ALL, 5)
        sizer.Add(btn_row, 0, wx.ALIGN_CENTER)

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, wx.ID_OK, "Download")
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(wx.Button(panel, wx.ID_CANCEL))
        btn_sizer.Realize()
        sizer.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        panel.SetSizer(sizer)
        checklist.SetFocus()

        if dlg.ShowModal() == wx.ID_OK:
            selections = [i for i in range(len(items)) if checklist.IsChecked(i)]
            dlg.Destroy()
            if not selections:
                return

            dest = yt.load_download_dir()
            self._yt_download_subfolder = None

            # Offer subfolder grouping for multiple items
            if len(selections) > 1:
                result = wx.MessageBox("Put all downloads into a subfolder?", "Group Downloads", wx.YES_NO | wx.ICON_QUESTION)
                if result == wx.YES:
                    name_dlg = wx.TextEntryDialog(self, "Subfolder name:", "Subfolder")
                    if name_dlg.ShowModal() == wx.ID_OK:
                        subfolder = name_dlg.GetValue().strip()
                        name_dlg.Destroy()
                        if subfolder:
                            dest = os.path.join(dest, subfolder)
                            os.makedirs(dest, exist_ok=True)
                            self._yt_download_subfolder = subfolder
                    else:
                        name_dlg.Destroy()

            self._yt_download_queue = [(results[i]["title"], results[i]["url"]) for i in selections]
            self._yt_download_dest = dest
            self._yt_download_idx = 0
            self._bg_cancel_requested = False
            self._bg_yt_percent = 0
            speak(f"Queued {len(self._yt_download_queue)} downloads")
            self._yt_download_next()
        else:
            dlg.Destroy()

    def _yt_download_next(self):
        """Download next item in YouTube queue, in the background.

        Returns right away after starting the worker thread: there is no
        pop-up window any more, so playback, Live TV and the menus keep
        working while the download runs.
        """
        if self._yt_download_idx >= len(self._yt_download_queue):
            total = len(self._yt_download_queue)
            self._yt_close_progress_dialog()
            if getattr(self, "_bg_cancel_requested", False):
                self._bg_cancel_requested = False
                msg = "Downloads cancelled"
                self.status_label.SetLabel(msg)
                speak(msg)
                return
            msg = f"All {total} YouTube download(s) complete"
            self.status_label.SetLabel(msg)
            speak(msg)
            # Free local disk space if the auto cloud-cleanup setting is on
            self._maybe_free_up_space(self._yt_download_dest)
            # Voice downloads make their channel by themselves,
            # with no pop-up question. Anything else still gets
            # the Yes/No offer, as before.
            if getattr(self, "_auto_create_channel", False):
                self._auto_create_channel = False
                if getattr(self, "_yt_download_subfolder", None):
                    self._create_channel_from_download(
                        self._yt_download_subfolder,
                        self._yt_download_dest, source="YOUTUBE")
            elif getattr(self, "_yt_download_subfolder", None):
                self._yt_offer_channel_creation()
            return

        title, url = self._yt_download_queue[self._yt_download_idx]
        current = self._yt_download_idx + 1
        total = len(self._yt_download_queue)

        # Background progress only: no pop-up window, so the download
        # does not steal focus while Honey keeps listening.
        self._yt_show_progress_dialog(current, total, title)
        msg = f"Downloading {current} of {total}: {title}..."
        self.status_label.SetLabel(msg)
        speak(f"Downloading {current} of {total}: {title}. Downloading in the background, so you can keep listening.")
        self.logger.log_playback("YOUTUBE", f"Starting download {current}/{total}: {title}")
        threading.Thread(target=self._yt_download_thread, args=(title, url), daemon=True).start()

    def _yt_offer_channel_creation(self):
        """Offer to create/update a channel from the downloaded YouTube files."""
        subfolder = self._yt_download_subfolder
        dest = self._yt_download_dest

        result = wx.MessageBox(
            f"Create a channel '{subfolder}' from the downloaded episodes?",
            "Create Channel",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result != wx.YES:
            wx.MessageBox("Downloads complete.", "Done", wx.OK | wx.ICON_INFORMATION)
            return

        channel_name = subfolder

        # Find all folders that contain MP3 files, sorted naturally
        from playlist_manager import natural_sort_key
        folders = []
        for root, dirs, files in os.walk(dest):
            dirs.sort(key=natural_sort_key)
            if any(f.lower().endswith('.mp3') for f in files):
                folders.append(root)

        if not folders:
            wx.MessageBox("No MP3 files found in downloaded content.", "No Files", wx.OK | wx.ICON_WARNING)
            return

        # Handle existing channel
        if channel_name in self.channels.channels:
            choice = wx.MessageBox(
                f"Channel '{channel_name}' already exists.\n\nYes = Replace it\nNo = Add folders to it",
                "Channel Exists",
                wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION
            )
            if choice == wx.CANCEL:
                return
            elif choice == wx.YES:
                self.channels.delete_channel(channel_name)
                self.channels.create_channel(channel_name)
                self.channels.update_current_channel(folders=folders)
            else:
                existing = self.channels.channels[channel_name].get('folders', [])
                combined = existing + [f for f in folders if f not in existing]
                self.channels.switch_channel(channel_name)
                self.channels.update_current_channel(folders=combined)
        else:
            self.channels.create_channel(channel_name)
            self.channels.update_current_channel(folders=folders)

        # Load the new channel
        self.playlist = PlaylistManager()
        self._load_current_channel()
        self._update_title()
        self._update_display()

        msg = f"Channel '{channel_name}' created with {len(folders)} folder(s)"
        self.status_label.SetLabel(msg)
        speak(msg)
        self.logger.log_channel("YOUTUBE", "CHANNEL-CREATE", f"{channel_name} with {len(folders)} folders")

    def _yt_show_progress_dialog(self, current, total, title):
        """Record background YouTube progress without opening a window.

        The old pop-up progress window is gone on purpose: it stole
        focus while Honey was listening. Progress now lives in the
        status line (see _yt_update_progress) and can be heard any time
        with Download Status. Kept under this name so existing callers
        do not change.
        """
        self._bg_yt_percent = 0
        self._yt_progress_dlg = None
        self.status_label.SetLabel(f"Downloading in the background {current} of {total}: {title} - 0%")

    def _yt_close_progress_dialog(self):
        """Destroy the progress dialog if one exists (none is shown now)."""
        dlg = getattr(self, "_yt_progress_dlg", None)
        if dlg:
            dlg.Destroy()
            self._yt_progress_dlg = None

    def _on_yt_cancel_download(self, event):
        """User cancelled the download (kept for compatibility)."""
        self._on_cancel_downloads(event)

    def _yt_download_thread(self, title, url, _retry=False):
        try:
            def progress(percent, filename):
                if getattr(self, "_yt_cancel_requested", False) or getattr(self, "_bg_cancel_requested", False):
                    raise _YTDownloadCancelled()
                wx.CallAfter(self._yt_update_progress, percent, title)

            filepath = yt.download(url, destination=self._yt_download_dest, progress_callback=progress)
            if filepath == "ALREADY":
                self.logger.log_playback("YOUTUBE", f"Already downloaded, skipped: {title}")
                wx.CallAfter(self._yt_download_skipped, title)
            elif filepath:
                wx.CallAfter(self._yt_download_complete, title, filepath)
            else:
                wx.CallAfter(self._yt_error, f"Download failed (no file produced): {title}")
        except _YTDownloadCancelled:
            self.logger.log_playback("YOUTUBE", f"Download cancelled during: {title}")
        except yt.VideoUnavailableError:
            wx.CallAfter(
                self._yt_error,
                f"'{title}' can't be downloaded. It may be DRM-protected, removed, made "
                f"private, age-restricted, or region-locked. This is a restriction on "
                f"YouTube's side, not a problem with the app. Skipping it."
            )
        except RuntimeError as e:
            # ffmpeg missing or similar setup problem
            self.logger.log_error(f"YOUTUBE: {e} | tools dir: {yt.TOOLS_DIR} | exists: {yt.TOOLS_DIR.exists()}")
            wx.CallAfter(self._yt_error, str(e))
        except Exception as e:
            self.logger.log_error(f"YOUTUBE: Download error for {title}: {e}")
            # If the disk is full, free up OneDrive space and retry once.
            if self._is_low_disk_error(e) and not _retry:
                self.logger.log_error("YOUTUBE: low disk space — auto free-up-space then retry")
                wx.CallAfter(self.status_label.SetLabel, "Disk full — freeing up space and retrying...")
                speak("Disk is full. Freeing up space and trying again.")
                freed = self._free_up_space_all_onedrive()
                self.logger.log_playback("CLOUD", f"Auto free-up before YT retry freed: {freed}")
                self._yt_download_thread(title, url, _retry=True)
                return
            if self._is_low_disk_error(e):
                wx.CallAfter(self._yt_error,
                             "Still out of disk space after freeing up room. Free space or move "
                             "your YouTube download folder into OneDrive to make files online-only.")
            else:
                wx.CallAfter(self._yt_error, f"Download error for {title}: {e}")

    def _yt_update_progress(self, percent, title):
        # Update the status line only; there is no pop-up window any more.
        # Nothing is spoken here, so progress does not talk over playback.
        self._bg_yt_percent = percent
        current = self._yt_download_idx + 1
        total = len(self._yt_download_queue)
        self.status_label.SetLabel(f"Downloading in the background {current} of {total}: {title} - {percent:.0f}%")

    def _yt_download_complete(self, title, filepath):
        self.status_label.SetLabel(f"Downloaded: {title}")
        speak(f"Downloaded {title}")
        self.logger.log_playback("YOUTUBE", f"Complete: {title} -> {filepath}")
        self._yt_download_idx += 1
        self._yt_download_next()

    def _yt_download_skipped(self, title):
        """A video that was already downloaded before — skipped, not an error."""
        self.status_label.SetLabel(f"Already have: {title}")
        speak(f"Already have {title}, skipping")
        self._yt_download_idx += 1
        self._yt_download_next()

    def _yt_error(self, message):
        self.status_label.SetLabel(message)
        speak(message)
        self.logger.log_error(f"YOUTUBE: {message}")
        # Move past the failed item and continue. Always route back through
        # _yt_download_next so that when the queue is finished it still runs the
        # completion logic (which offers to create a channel).
        self._yt_download_idx += 1
        wx.CallLater(1000, self._yt_download_next)

    # ---- Samantha voice: live TV by voice ----
    def _livetv_voice_play(self, query):
        """Play a live channel by voice, in the background.

        Honey, 2026-11-23: "Samantha, play Game Show Network live"
        and other channels. No name = a favourite live channel
        first, otherwise the first live channel. With a name, the
        exact channel name wins, then a name that starts with it,
        then any channel containing it, then the closest channel
        name (fuzzy, Ashley 2026-11-26 — Vosk mishears names).
        """
        def work():
            try:
                if not LIVETV_AVAILABLE or livetv is None:
                    wx.CallAfter(self._livetv_voice_play_done, None, query,
                                 "Live TV is not available.")
                    return
                livetv.refresh_catalog()
                channels = livetv.get_all_channels()
                if not channels:
                    wx.CallAfter(self._livetv_voice_play_done, None, query,
                                 "No live channels were found.")
                    return
                if not query:
                    channel = self._livetv_pick_fallback_channel(channels)
                    wx.CallAfter(self._livetv_voice_play_done, channel, query, None)
                    return
                q = str(query).strip().lower()
                channel = None
                for c in channels:
                    if c["name"].lower() == q:
                        channel = c
                        break
                if channel is None:
                    for c in channels:
                        if c["name"].lower().startswith(q):
                            channel = c
                            break
                if channel is None:
                    for c in channels:
                        if q in c["name"].lower():
                            channel = c
                            break
                if channel is None:
                    # Ashley, 2026-11-26: Vosk hears live channel
                    # names wrong ("p b s kids", "game show net
                    # work"), and exact matching found nothing, so
                    # she had to try six times. Fall back to the
                    # closest channel name instead of giving up.
                    channel = livetv.best_live_match(q, channels)
                wx.CallAfter(self._livetv_voice_play_done, channel, query, None)
            except Exception as e:
                wx.CallAfter(self._livetv_voice_play_done, None, query, str(e))
        threading.Thread(target=work, daemon=True).start()

    def _livetv_voice_play_done(self, channel, query, error):
        if error:
            msg = error
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        if not channel:
            msg = (f"I couldn't find a live channel called {query}."
                   if query else "I couldn't find a live channel to play.")
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        self._livetv_play(channel)

    def _livetv_voice_search(self, query):
        """Search live channels by voice, then show the list to pick from."""
        def work():
            try:
                if not LIVETV_AVAILABLE or livetv is None:
                    wx.CallAfter(self._livetv_error, "Live TV is not available.")
                    return
                livetv.refresh_catalog()
                results = livetv.search_channels(query) if query else livetv.get_all_channels()
                wx.CallAfter(self._livetv_show_channel_list, results,
                             f"Live TV search: {query}" if query else "Live TV channels")
            except Exception as e:
                wx.CallAfter(self._livetv_error, f"Live channel search error: {e}")
        threading.Thread(target=work, daemon=True).start()

    def _fix_mixed_channels(self):
        """Unmix shows that are in the wrong channel.

        Honey, 2026-11-23: some shows she already has are still
        mixed up with other shows. This runs the unmix repair
        over every channel and speaks what moved out of where.
        Files are never deleted from disk by this - they are
        taken out of the wrong channel, and moved to the right
        channel when one matches their name.
        """
        try:
            report = self.channels.unmix_channels()
        except Exception as e:
            msg = f"I could not fix the mixed up shows: {e}"
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        if not report:
            msg = "I checked every channel, and no shows are mixed up."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        parts = []
        total = 0
        for channel, files in report.items():
            total += len(files)
            parts.append(f"{len(files)} from {channel}")
        msg = (f"Fixed the mixed up shows. Took out {total} file(s): "
               + "; ".join(parts) + ".")
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
        # Reload the current channel so what she hears next is
        # the unmixed playlist, not the old one.
        try:
            self.playlist = PlaylistManager()
            self._load_current_channel()
            self._update_display()
        except Exception:
            pass

    @staticmethod
    def _spoken_file_base(value):
        """Bare file name, no folder, no extension, no underscores.

        Ashley, 2026-11-27: the guide was reading full Windows
        paths out loud — "C colon backslash Users backslash
        Ashley M backslash audio TV backslash ..." — because
        show names were taken from full paths. Every spoken
        name goes through here first, so no path, drive letter,
        backslash or ".mp3" is ever spoken again.
        "C:\\Users\\Ashley M\\audio TV\\Friends\\Friends - S01E01.mp3"
        -> "Friends - S01E01". Both \\ and / count as separators,
        so this works even when the code runs on another system.
        """
        import re
        name = re.split(r"[\\/]", str(value))[-1].strip()
        if "." in name:
            name = name.rsplit(".", 1)[0]
        name = re.sub(r"\s+", " ", name.replace("_", " ")).strip()
        return name

    @staticmethod
    def _parse_spoken_episode(value):
        """(show, season, episode, title) from a file name or full path.

        "Classic Doctor Who - S01E02 - The Daleks.mp3" ->
        ("Classic Doctor Who", 1, 2, "The Daleks").
        "Friends - S01E01.mp3" -> ("Friends", 1, 1, "").
        "Friends - Season 02 (1994).mp3" -> ("Friends", 2, None, "").
        "Classic Doctor Who - An Unearthly Child.mp3" ->
        ("Classic Doctor Who", None, None, "An Unearthly Child").
        "Friends.mp3" -> ("Friends", None, None, "").
        The show name is kept as written, so Samantha says it
        the way Ashley named it.
        """
        import re
        base = PlayerFrame._spoken_file_base(value)
        parts = [p.strip() for p in base.split(" - ") if p.strip()]
        if not parts:
            return ("", None, None, "")
        show = re.sub(r"\s*\([^)]*\)\s*$", "", parts[0]).strip()
        season = None
        episode = None
        title = ""
        rest = parts[1:]
        for i, part in enumerate(rest):
            m = re.search(r"[Ss](\d+)[Ee](\d+)", part)
            if m:
                season = int(m.group(1))
                episode = int(m.group(2))
                title = ", ".join(rest[i + 1:]).strip()
                break
            m = re.search(r"[Ss]eason\s+(\d+)", part, re.I)
            if m:
                season = int(m.group(1))
                title = ", ".join(rest[i + 1:]).strip()
                break
            m = re.search(r"[Ee]pisode\s+(\d+)", part, re.I)
            if m:
                episode = int(m.group(1))
                title = ", ".join(rest[i + 1:]).strip()
                break
        else:
            title = ", ".join(rest).strip()
        title = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
        return (show, season, episode, title)

    @staticmethod
    def _spoken_show(value):
        """Just the show name from a file name or full path.

        "C:\\...\\Classic Doctor Who - S01E01.mp3" ->
        "Classic Doctor Who". Never a path, never an extension.
        """
        return PlayerFrame._parse_spoken_episode(value)[0]

    @staticmethod
    def _spoken_episode(value, said_show=None):
        """One episode in plain spoken words: no path, no extension,
        no file codes like S01E02 or ".mp3".

        "Classic Doctor Who - S01E02 - The Daleks.mp3" ->
        "Classic Doctor Who, season 1, episode 2, The Daleks".
        said_show is a show name spoken just before this one:
        when it is the same show, the name is said once, not
        twice — "episode 2, The Daleks" instead of repeating
        "Classic Doctor Who" again.
        """
        show, season, episode, title = \
            PlayerFrame._parse_spoken_episode(value)
        if not show:
            return "Unknown show"
        bits = []
        if said_show is None or show.lower() != str(said_show).lower():
            bits.append(show)
        if season is not None and episode is not None:
            bits.append(f"season {season}, episode {episode}")
        elif episode is not None:
            bits.append(f"episode {episode}")
        elif season is not None:
            bits.append(f"season {season}")
        if title:
            bits.append(title)
        return ", ".join(bits)

    def _smooth_advance_text(self, now_file, channel_name=""):
        """One smooth announcement for when a new file starts.

        Ashley, 2026-11-27: "Make the TV guide more smoother."
        The old auto-advance spoke in three separate bits, one
        after another — "Playing: ...", then "Coming up next: ...",
        then "A marathon of ... is starting." — with a gap and a
        fresh start each time, and the marathon came last, after
        the next episode had already been named. This builds the
        whole thing as ONE flowing announcement, in the order
        she hears it: what is playing now, then the marathon
        (so the next episode is framed as part of it), then
        what comes up next. One speak() call, no repeats, no
        file paths, no ".mp3", no S01E02 codes, and the show
        name is said once for the episode, not again for the
        marathon — "It's a marathon" does not need the name
        a second time.
        """
        show = self._spoken_show(now_file)
        episode = self._spoken_episode(now_file)
        parts = [f"Now playing {episode}."]
        if self._marathon_starting():
            parts.append(
                "It's a marathon, so it will keep playing "
                "through the whole series.")
        coming = self.playlist.peek_next_file_name()
        if coming:
            parts.append(
                "Coming up next is "
                f"{self._spoken_episode(coming, show)}.")
        else:
            nxt_ch = self.channels.peek_next_channel()
            if nxt_ch and nxt_ch != channel_name:
                parts.append(
                    f"After this, the next channel is {nxt_ch}.")
        return " ".join(parts)

    @staticmethod
    def _spoken_playing_msg(file_name, channel_name=""):
        """'Playing: ...' in plain words, the show name said once.

        "Classic Doctor Who - S01E02 - The Daleks.mp3" on channel
        "Classic Doctor Who" -> "Playing: Classic Doctor Who,
        season 1, episode 2, The Daleks" — not "Classic Doctor
        Who. Playing: Classic Doctor Who - S01E02 - The Daleks.mp3".
        """
        show = PlayerFrame._spoken_show(file_name)
        spoken = PlayerFrame._spoken_episode(file_name)
        if channel_name and show.lower() == channel_name.lower():
            return f"Playing: {spoken}"
        if channel_name:
            return f"{channel_name}. Playing: {spoken}"
        return f"Playing: {spoken}"

    @staticmethod
    def _show_base(file_name):
        """The show a file belongs to, for marathon detection.

        "Doctor Who - S01E02.mp3" -> "doctor who";
        "Friends - Season 02 (1994).mp3" -> "friends".
        Works on a full path too: the folder is stripped first.
        Before this, a full path came back as the whole path
        ("c:\\users\\ashley m\\audio tv\\classic doctor who\\
        classic doctor who"), so marathon detection only worked
        by accident — files in one folder happened to share the
        same path prefix — and marathon names were spoken as
        full paths.
        """
        import re
        base = PlayerFrame._spoken_file_base(file_name)
        base = re.split(r"\s+-\s+|\s*\(|\s+S\d+E\d+", base, 1)[0].strip().lower()
        base = re.sub(r"^(?:a|the)\s+", "", base)
        return base

    @staticmethod
    def _folders_with_mp3_files(dest):
        """Every folder under dest that holds MP3 files, sorted
        naturally. Pure file work, so it is easy to test."""
        from playlist_manager import natural_sort_key
        folders = []
        for root, dirs, files in os.walk(dest):
            dirs.sort(key=natural_sort_key)
            if any(f.lower().endswith(".mp3") for f in files):
                folders.append(root)
        return folders

    def _create_channel_from_download(self, channel_name, dest, source="VAULT"):
        """Make (or add to) a channel from downloaded files, with no
        pop-up question. Honey, 2026-11-23: when Samantha searches
        and downloads a show, the channel should just be made.
        If the channel already exists, the new folders are added to
        it - nothing is ever replaced or deleted here. Returns True
        when a channel was made or added to."""
        import shutil
        # Flatten any double-nested folders first, as the manual
        # channel offer does.
        for root, dirs, files in os.walk(dest, topdown=False):
            for d in dirs:
                dir_path = os.path.join(root, d)
                try:
                    contents = os.listdir(dir_path)
                    if len(contents) == 1:
                        inner = os.path.join(dir_path, contents[0])
                        if os.path.isdir(inner):
                            if contents[0] == d or contents[0].lower().startswith(d.lower()) or d.lower().startswith(contents[0].lower()):
                                for item in os.listdir(inner):
                                    shutil.move(os.path.join(inner, item), dir_path)
                                os.rmdir(inner)
                except Exception:
                    pass
        folders = self._folders_with_mp3_files(dest)
        if not folders:
            msg = f"Downloaded {channel_name}, but I found no MP3 files, so I could not make a channel for it."
            self.status_label.SetLabel(msg)
            speak(msg)
            return False
        if channel_name in self.channels.channels:
            existing = self.channels.channels[channel_name].get("folders", [])
            combined = existing + [f for f in folders if f not in existing]
            self.channels.switch_channel(channel_name)
            self.channels.update_current_channel(folders=combined)
            made = False
        else:
            self.channels.create_channel(channel_name)
            self.channels.update_current_channel(folders=folders)
            made = True
        self.playlist = PlaylistManager()
        self._load_current_channel()
        self._update_title()
        self._update_display()
        if made:
            msg = f"Channel {channel_name} created, with {len(folders)} folder{'s' if len(folders) != 1 else ''}."
        else:
            msg = f"Added the new files to your {channel_name} channel."
        self.status_label.SetLabel(msg)
        speak(msg)
        self.logger.log_channel(source, "CHANNEL-CREATE", f"{channel_name} with {len(folders)} folders")
        return True

    def _marathon_ahead(self, count=3):
        """A marathon coming up in this channel, or None.

        A marathon is three or more files of the same show in a
        row, starting with the next file. Returns the show name
        as written on the files, e.g. "Doctor Who".
        """
        playlist = getattr(self, "playlist", None)
        if not playlist or not playlist.playlist:
            return None
        idx = playlist.current_index
        upcoming = playlist.playlist[idx + 1: idx + 1 + count]
        if len(upcoming) < count:
            return None
        bases = [self._show_base(str(fp.name)) for _, fp in upcoming]
        if len(set(bases)) == 1 and bases[0]:
            return self._spoken_show(str(upcoming[0][1].name))
        return None

    def _marathon_starting(self, count=3):
        """True if the file playing now starts a marathon: this
        file and the next two are the same show, and the file
        before it was a different show (or there was none)."""
        playlist = getattr(self, "playlist", None)
        if not playlist or not playlist.playlist:
            return False
        idx = playlist.current_index
        run = playlist.playlist[idx: idx + count]
        if len(run) < count:
            return False
        bases = [self._show_base(str(fp.name)) for _, fp in run]
        if len(set(bases)) != 1 or not bases[0]:
            return False
        if idx > 0:
            before = self._show_base(str(playlist.playlist[idx - 1][1].name))
            if before == bases[0]:
                return False
        return True

    def _livetv_guide_text(self, channel_name=None):
        """A guide for one live channel, e.g. Game Show Network.

        Honey, 2026-11-23: "have her give me another guide
        for the game show network too so that I know what's
        coming up next." Live TV has no programme schedule in
        its catalogue - only channel names - so this guide
        names the live channel and the live channels coming
        up after it. It cannot name the actual game shows
        playing on Game Show Network, because the live
        catalogue carries no programme listings.
        """
        try:
            all_ch = livetv.get_all_channels() if LIVETV_AVAILABLE else []
        except Exception:
            all_ch = []
        if not all_ch:
            return "I could not load the live channels right now."
        wanted = (channel_name or "game show network").strip().lower()
        match = None
        for c in all_ch:
            if wanted in c["name"].lower() or c["name"].lower() in wanted:
                match = c
                break
        if not match:
            return f"I could not find {channel_name or 'that live channel'}."
        name = match["name"]
        names = [c["name"] for c in all_ch]
        i = names.index(name)
        nxt = [names[(i + 1 + k) % len(names)] for k in range(min(3, len(names) - 1))]
        live = getattr(self, "_livetv_last_channel", None)
        if live and live.get("name", "").lower() == name.lower():
            text = f"Now on live TV: {name}."
        else:
            text = f"{name} is on live TV now."
        if nxt:
            text += " Coming up next on live: " + ", ".join(nxt) + "."
        return text

    def _speak_livetv_guide(self, channel_name=None):
        """Read one live channel's guide, Samantha first."""
        self._play_sound_effect("samantha_coming_up_next.wav")
        text = self._livetv_guide_text(channel_name)
        self.status_label.SetLabel(text)
        # Samantha reads it herself, like the main guide: the old
        # speak() here is NVDA, silent while NVDA quiet is on, so
        # the live guide was never heard at all.
        self._say_in_samantha_voice(text)

    def _channel_file_names(self, channel_name):
        """File names in one channel, without switching to it.

        Uses that channel's cached playlist when it has one,
        otherwise scans its folders once, the same way
        _load_current_channel does for the current channel.
        Files unmixed out of the channel stay out.
        """
        data = self.channels.channels.get(channel_name)
        if not data:
            return []
        removed = set(data.get("mixed_files_removed") or [])
        cached = data.get("cached_playlist")
        if cached:
            names = [str(fp) for _, fp in cached]
        else:
            folders = data.get("folders") or []
            tmp = PlaylistManager()
            try:
                tmp.add_folders(folders)
            except Exception:
                return []
            names = [str(fp) for _, fp in tmp.playlist]
        if removed:
            names = [n for n in names
                     if self._show_base(n) not in
                     {self._show_base(r) for r in removed}
                     and n not in removed]
        return names

    @staticmethod
    def _find_marathon_in_names(names, count=3):
        """First show with 3 or more files in a row, or None.

        Names are file names like "Friends - S01E01.mp3".
        Returns the show name as written, e.g. "Friends".
        """
        if len(names) < count:
            return None
        for i in range(len(names) - count + 1):
            run = names[i:i + count]
            bases = [PlayerFrame._show_base(n) for n in run]
            if len(set(bases)) == 1 and bases[0]:
                # Clean show name only: run[0] can be a full path,
                # and splitting it on " - " used to return the
                # whole path, backslashes and all.
                return PlayerFrame._spoken_show(run[0])
        return None

    def _marathons_in_other_channels(self):
        """Marathons coming up on channels other than the current one.

        Ashley, 2026-11-26: when Samantha tells her what comes
        up next, she should say if it is a marathon of Classic
        Doctor Who, or Two and a Half Men, or Friends, or
        Frasier, or whatever channels she has — not only a
        marathon on the channel playing right now. Returns a
        list of (channel, show), at most 5, in channel order.
        """
        found = []
        current = self.channels.current_channel
        for name in self.channels.get_channel_list():
            if name == current or len(found) >= 5:
                continue
            show = self._find_marathon_in_names(
                self._channel_file_names(name))
            if show:
                found.append((name, show))
        return found

    def _up_next_text(self):
        """The whole TV guide as one spoken text.

        Honey, 2026-11-23: "give me like the whole TV guide
        of what's coming up next." What is playing now, what
        comes up next in this channel, and what channel comes
        after this one. Live TV has no programme schedule in
        its catalogue - only channel names - so for live the
        guide names the live channel now and the next live
        channels after it.
        """
        parts = []
        live = getattr(self, "_livetv_last_channel", None)
        if live:
            parts.append(f"Now on live TV: {live.get('name', 'live TV')}.")
            try:
                favs = livetv.get_favorite_channels() if LIVETV_AVAILABLE else []
                all_ch = livetv.get_all_channels() if LIVETV_AVAILABLE else []
                pool = [c["name"] for c in favs] or [c["name"] for c in all_ch]
                cur = live.get("name")
                if cur in pool:
                    i = pool.index(cur)
                    nxt = [pool[(i + 1 + k) % len(pool)] for k in range(min(3, len(pool) - 1))]
                else:
                    nxt = pool[:3]
                if nxt:
                    parts.append("Coming up next on live: " + ", ".join(nxt) + ".")
            except Exception:
                pass
            return " ".join(parts)
        channel = self.channels.current_channel or ""
        current = self.playlist.get_current_file_name()
        # said_show tracks the last show name spoken in this guide,
        # so the same show is never said twice in a row: the next
        # episode is "episode 2, The Daleks", not
        # "Classic Doctor Who" all over again. Ashley, 2026-11-27:
        # the old guide said the channel, then the whole file name
        # with the show in it again, then ".mp3" and "S01E01".
        said_show = None
        if channel and current:
            show = self._spoken_show(current)
            if show and show.lower() == channel.lower():
                parts.append(
                    f"Now playing {self._spoken_episode(current)}.")
            else:
                parts.append(
                    f"Now playing on {channel}: "
                    f"{self._spoken_episode(current)}.")
            said_show = show
        elif channel:
            parts.append(f"Now on {channel}.")
        else:
            return "Nothing is playing right now."
        marathon = self._marathon_ahead()
        nxt_file = self.playlist.peek_next_file_name()
        handled_next = False
        if marathon and nxt_file:
            # Ashley, 2026-11-27, smoother TV guide: do not say
            # "coming up next" twice in a row — once for the
            # marathon and once for the next episode. Fold them
            # into one flowing sentence instead.
            parts.append(
                f"Coming up next is a marathon of {marathon}, "
                f"starting with "
                f"{self._spoken_episode(nxt_file, marathon)}.")
            said_show = marathon
            handled_next = True
            nxt_ch = self.channels.peek_next_channel()
            if nxt_ch and nxt_ch != channel:
                parts.append(f"After that, the next channel is {nxt_ch}.")
        elif marathon:
            parts.append(f"A marathon of {marathon} is coming up next.")
            said_show = marathon
        if not handled_next and nxt_file:
            parts.append(
                "Coming up next: "
                f"{self._spoken_episode(nxt_file, said_show)}.")
            nxt_ch = self.channels.peek_next_channel()
            if nxt_ch and nxt_ch != channel:
                parts.append(f"After that, the next channel is {nxt_ch}.")
        elif not handled_next:
            nxt_ch = self.channels.peek_next_channel()
            if nxt_ch:
                parts.append(
                    f"That is the last one on {channel}. "
                    f"Coming up next: {nxt_ch}.")
        # Ashley, 2026-11-26: marathons on her other channels
        # too — Classic Doctor Who, Two and a Half Men, Friends,
        # Frasier, or whatever channels she has — not only a
        # marathon on the channel playing right now.
        others = self._marathons_in_other_channels()
        if others:
            bits = [f"on {ch}, a marathon of {show}"
                    for ch, show in others]
            parts.append("Later, marathons coming up: "
                         + "; ".join(bits) + ".")
        return " ".join(parts)

    def _speak_channel_list(self):
        """Read out all the channels Ashley has.

        Ashley, 2026-11-26: after she says "I am good", Samantha
        reads the list of channels, without Ashley having to ask
        for it, so she can tell Samantha which channel she wants.
        The names change as channels are added, so they are read
        in Samantha's reading voice (see _say_in_samantha_voice),
        not NVDA's — NVDA stays quiet.
        """
        channels = self.channels.get_channel_list()
        if not channels:
            msg = "No channels available. Press Ctrl+T to create one."
        else:
            names = ", ".join(channels)
            msg = (f"Here are your channels: {names}. "
                   "Tell me which one you want to watch.")
        self.status_label.SetLabel(msg)
        self._say_in_samantha_voice(msg)

    def _current_reading_voice_name(self):
        """The voice name the Voice menu should show checked.

        Whatever config.ini says for samantha_fish_voice, the
        Fish name it holds, or the Edge option when the stored
        value is not a Fish voice.
        """
        import configparser
        try:
            config = configparser.ConfigParser()
            config_path = Path(__file__).parent / "config.ini"
            config.read(config_path)
            voice = config.get("settings", "samantha_fish_voice",
                               fallback="Ariana Grande").strip()
        except Exception:
            voice = "Ariana Grande"
        if voice in _FISH_VOICES:
            return voice
        return _EDGE_VOICE_OPTION

    def _set_reading_voice(self, name):
        """Save the chosen reading voice in config.ini."""
        import configparser
        config = configparser.ConfigParser()
        config_path = Path(__file__).parent / "config.ini"
        config.read(config_path)
        if not config.has_section("settings"):
            config["settings"] = {}
        config.set("settings", "samantha_fish_voice", name)
        with open(config_path, "w") as f:
            config.write(f)
        # The mode may have changed (fish <-> edge): re-evaluate
        # it on the next reading instead of trusting the cache.
        self._samantha_voice_mode_cache = "unset"

    def _update_voice_menu_checks(self):
        """Put the check on the voice config.ini currently uses."""
        selected = self._current_reading_voice_name()
        for item, name in self._voice_menu_items.values():
            item.Check(name == selected)

    def _on_voice_menu_open(self, event):
        self._update_voice_menu_checks()

    def _on_voice_select(self, event):
        """A Fish or Edge voice was picked from the Voice menu."""
        item_and_name = self._voice_menu_items.get(event.GetId())
        if item_and_name is None:
            return
        name = item_and_name[1]
        self._set_reading_voice(name)
        self._update_voice_menu_checks()
        has_key = self._fish_settings()[0] is not None
        if name == _EDGE_VOICE_OPTION:
            msg = "Reading voice: Aria, the Edge reading voice."
        elif has_key:
            msg = f"Reading voice: {name}."
        else:
            msg = (f"{name} is saved, but no Fish Audio key was "
                   "found, so I will read with the Edge voice for now.")
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)

    def _on_voice_sample(self, event):
        """Read a short line in the currently selected voice."""
        selected = self._current_reading_voice_name()
        self._say_in_samantha_voice(
            f"Hi. This is my reading voice, {selected}. "
            "Let me know if you like it.")

    def _fish_settings(self):
        """(api_key, reference_id) for Fish Audio, or (None, None).

        Ashley, 2026-11-28: she wants the reading voice to be the
        same Fish Audio voice that greets her, not Edge TTS's
        Aria. The API key already lives in her NVDA fishy
        settings (the fishy addon she uses for NVDA's own
        speech), so it is read from there first — she has to
        type nothing. Fallback: config.ini fish_api_key. The
        voice name (or a raw 32-hex reference id) comes from
        config.ini samantha_fish_voice, defaulting to the
        custom "Ariana Grande" voice, the one closest to her
        recording in pitch (measured 2026-11-28).
        """
        import configparser
        import re
        key = None
        try:
            nvda_cfg = (Path.home() / "AppData" / "Roaming" / "NVDA"
                        / "fishy" / "settings.json")
            if nvda_cfg.exists():
                key = str(json.load(open(nvda_cfg))
                          .get("api_key", "")).strip() or None
        except Exception:
            pass
        try:
            config = configparser.ConfigParser()
            config_path = Path(__file__).parent / "config.ini"
            config.read(config_path)
            if not key:
                key = config.get("settings", "fish_api_key",
                                 fallback="").strip() or None
            voice = config.get("settings", "samantha_fish_voice",
                               fallback="Ariana Grande").strip()
        except Exception:
            voice = "Ariana Grande"
        if not key:
            return None, None
        ref = _FISH_VOICES.get(voice)
        if ref is None and re.fullmatch(r"[0-9a-f]{32}", voice.lower()):
            # A raw reference id, not a name — use it directly.
            ref = voice.lower()
        if ref is None:
            return None, None
        return key, ref

    def _fish_synthesize(self, key, ref_id, text, out_mp3):
        """One Fish Audio TTS request (stdlib urllib).

        The same call the fishy NVDA addon makes
        (api.fish.audio/v1/tts, s2.1-pro-free). MP3 only
        supports 32000 or 44100 Hz — 24000 (the addon's PCM
        rate) is rejected for MP3, which is why it is 32000
        here. soundfile decodes the MP3 in the player.
        """
        import urllib.request
        payload = json.dumps({
            "text": text,
            "reference_id": ref_id,
            "format": "mp3",
            "sample_rate": 32000,
            "prosody": {"speed": 1, "volume": 0},
            "latency": "balanced",
            "chunk_length": 150,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.fish.audio/v1/tts", data=payload,
            headers={
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "model": "s2.1-pro-free",
            }, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            open(out_mp3, "wb").write(r.read())

    def _samantha_voice_mode(self):
        """Which voice can read dynamic text out loud, if any.

        Ashley, 2026-11-26: "I want her to have the list of
        shows. I don't want NVDA reading that list of shows.
        I want her to." Samantha's recorded voice cannot read
        show names she never recorded, so dynamic text needs
        a reading voice that can say any words. Two sources,
        in priority order, and it is NEVER Microsoft:
        - "fish": the Fish Audio voice — the SAME voice that
          greets her (Ashley, 2026-11-28: "the same voice that
          greets me should read the list"). No install needed:
          ready the moment the app opens, with her API key
          read from her NVDA fishy settings and the voice set
          in config.ini (samantha_fish_voice, see
          _fish_settings). When a Fish call fails, that one
          reading falls back to edge (see _fish_tts_read).
        - "edge": the edge-tts library is installed (vendored
          with the app), so text is spoken with the Edge
          reading voice over the internet. Voice and pitch in
          config.ini (samantha_reading_voice /
          samantha_reading_pitch, see _reading_voice). Used
          when Fish is not configured, or as the fallback for
          a failed Fish call.
        - None: neither is available (no Fish key and edge-tts
          not installed yet); readings fall back to the
          "not ready" flow, as before, until edge installs.
        Microsoft's own built-in speech was tried once and is
        GONE — Ashley said "I didn't tell you to add Microsoft"
        and "I don't like Microsoft Sierra", so it is never
        used, not even as a fallback. Only a working reading
        voice is cached.
        """
        cached = getattr(self, "_samantha_voice_mode_cache", "unset")
        if cached == "fish" or cached == "edge":
            return cached
        # Ashley, 2026-11-28: the Fish Audio voice (the same
        # voice that greets her) wins when it is configured —
        # no install needed, it is ready the moment the app
        # opens. Nothing configured falls through to the edge
        # logic below, exactly as before.
        if self._fish_settings()[1] is not None:
            self._samantha_voice_mode_cache = "fish"
            return "fish"
        # Ashley, 2026-11-26: "not ready" must never be cached
        # for the whole run. The old code cached None too, so
        # once the voice was missing at the first ask, every ask
        # after that said "not ready" even after the install had
        # finished — until the app was restarted. Now only a
        # working reading voice is cached; a missing one is
        # checked again on every ask, so the first ask after the
        # install finishes hears the list.
        mode = None
        try:
            import edge_tts  # noqa: F401
            mode = "edge"
        except Exception:
            mode = None
        if mode == "edge":
            self._samantha_voice_mode_cache = "edge"
        return mode

    def _clear_samantha_reading(self):
        """Mark Samantha's reading finished (queue callback)."""
        self._samantha_reading = False

    def _edge_import_ok(self, force_recheck=False):
        """True when the reading-voice library imports right now.

        With force_recheck=True (used right after a pip
        install), drop any cached copy first and clear the
        import caches, so a library that pip has just put on
        disk is really found in this same process — a plain
        `import edge_tts` after a failed import can otherwise
        keep answering from the old, failed attempt instead
        of seeing the newly installed files.
        """
        if force_recheck:
            try:
                sys.modules.pop("edge_tts", None)
            except Exception:
                pass
            try:
                import importlib
                importlib.invalidate_caches()
            except Exception:
                pass
        try:
            import edge_tts  # noqa: F401
            return True
        except Exception:
            return False

    def _edge_install_should_retry(self, force=False):
        """True when a new install attempt may start.

        Never while one is already running (the old code could
        start two pip installs at once — one at startup, one
        from asking for the list — and they fought each other),
        and not within a minute of the last try, so asking
        three times in a row does not start three installs.
        force=True (an explicit "install my reading voice")
        skips the 60-second gap — she asked for it now — but
        still never starts a second install while one runs.
        """
        if getattr(self, "_edge_install_running", False):
            return False
        if getattr(self, "_vosk_model_running", False):
            return False
        if force:
            return True
        try:
            last = float(getattr(self, "_edge_install_last_try", 0) or 0)
        except Exception:
            last = 0
        return (time.time() - last) > 60

    def _write_edge_flag(self, ok):
        """Record today's install result, so a failure is retried tomorrow."""
        try:
            flag = Path(tempfile.gettempdir()) / "audiovault_edge_tts_tried.txt"
            today = time.strftime("%Y-%m-%d")
            flag.write_text(today + (":ok" if ok else ":fail"))
        except Exception:
            pass

    def _say_in_samantha_voice(self, text):
        """Read dynamic text in Samantha's reading voice, not NVDA's.

        Used for the show list, the channel list, the TV guide,
        and the "you have it / you don't have it" answer — the
        readings Ashley asked Samantha herself to do. NVDA
        NEVER reads the list: Ashley, 2026-11-26, "I don't
        want NVDA to use the list. I want her to use the
        list." So when the reading voice is not installed yet,
        Samantha says so herself in her own recorded voice
        (sounds/samantha_reading_not_ready.wav) instead of
        falling back to NVDA. NVDA quiet stays on the whole
        time. Returns after starting the reading (it plays in
        the background); the _samantha_reading flag stays up
        while it plays so listening does not hear Samantha's
        own voice as a command, and so nothing else talks
        over her. The "not ready" clip itself is queued behind
        any clip still playing, so it never talks over her
        either, and it is said once per failed install — the
        old code replayed it on every single ask.
        """
        if not text:
            return
        mode = self._samantha_voice_mode()
        if mode in ("fish", "edge"):
            # Set the flag here, on the main thread, before the
            # synthesis thread starts: the old code only set it
            # inside the thread, so a check a moment later (the
            # guide waiting for the list, listening re-arming)
            # could see it clear and talk over the reading.
            self._samantha_reading = True
            target = (self._fish_tts_read
                      if mode == "fish" else self._edge_tts_read)
            threading.Thread(target=target,
                             args=(text,), daemon=True).start()
            return
        # No reading voice yet. Never NVDA, never Microsoft.
        self._samantha_reading = True
        state = getattr(self, "_edge_install_state", "unknown")
        if state in ("installing", "checking") or (
                state == "unknown"
                and getattr(self, "_edge_install_running", False)):
            # Ashley, 2026-11-27: the install thread starts in
            # __init__ but the state is still "unknown" for the
            # first moment — it only becomes "installing" once
            # the thread runs. An ask in that moment used to
            # fall through to the "not ready" clip below, even
            # though nothing had failed yet: that is what she
            # heard on her first ask after opening the app.
            # While ANY install is running, whatever the state
            # says, remember what she asked for and read it
            # when the voice is ready (see
            # _on_edge_install_ready), instead of saying "not
            # ready" for something that is about to be ready.
            # "I'm on it" tells her Samantha heard her.
            # The install is already running — she asked in the
            # middle of it. Remember what she asked for and read
            # it when the voice is ready (see
            # _on_edge_install_ready), instead of saying "not
            # ready" for something that is about to be ready.
            # "I'm on it" tells her Samantha heard her.
            self._pending_reading_text = text
            self._queue_samantha_sound(
                "samantha_im_on_it.wav",
                after=self._clear_samantha_reading)
            return
        if self._edge_install_should_retry():
            # Nothing is installing and the last try was a while
            # ago (or there never was one): try again now, in
            # the background, and read her the list when it is
            # ready. The old code only ever retried once per run
            # and then said "not ready" for the rest of the run.
            self._pending_reading_text = text
            threading.Thread(target=self._ensure_edge_tts,
                             daemon=True).start()
            self._queue_samantha_sound(
                "samantha_im_on_it.wav",
                after=self._clear_samantha_reading)
            return
        # A try just failed, very recently: say so once for
        # that failure, in her own recorded voice, and then
        # stay quiet until the next try. Only a real failed
        # try says "not ready" — never "unknown" (no try has
        # run yet) and never while an install is still
        # running: those are covered above, and saying "not
        # ready" for them is the bug Ashley heard on open.
        if state == "failed" and (
                getattr(self, "_edge_install_not_ready_said", 0)
                != getattr(self, "_edge_install_fail_count", 0)):
            self._edge_install_not_ready_said = \
                self._edge_install_fail_count
            self._play_samantha_sequence(
                ["samantha_reading_not_ready.wav"],
                after=self._clear_samantha_reading)
        else:
            wx.CallLater(1000, self._clear_samantha_reading)

    def _reading_voice(self):
        """(voice, pitch) Samantha's reading voice uses.

        Ashley, 2026-11-27: she wants the voice that greets her
        (her recorded voice) to be the same voice that reads
        the channel list. The recordings are around 340 Hz
        pitch; the Edge voices are around 200-220 Hz, so the
        reading voice is picked to sound as much like the
        recording as possible, with a pitch lift if needed.
        Whatever she picks after listening to the audition
        file (Samantha_reading_voice_audition.wav) goes here,
        in config.ini, so it can be changed without touching
        code:
            [settings]
            samantha_reading_voice = en-US-AriaNeural
            samantha_reading_pitch = +100Hz
        With no settings, the voice is today's default,
        en-US-AriaNeural at normal pitch. Only one reading
        voice at a time — never NVDA, never Microsoft.
        """
        import configparser
        import re
        voice = "en-US-AriaNeural"
        pitch = "+0Hz"
        try:
            config = configparser.ConfigParser()
            config_path = Path(__file__).parent / "config.ini"
            config.read(config_path)
            voice = config.get("settings", "samantha_reading_voice",
                               fallback=voice).strip() or voice
            pitch = config.get("settings", "samantha_reading_pitch",
                               fallback=pitch).strip()
            # Edge TTS wants exactly "+10Hz" / "-20Hz"; anything
            # else makes the whole synthesis fail, so an
            # unrecognisable setting means "normal pitch".
            if not re.match(r"^[+-]\d+Hz$", pitch):
                pitch = "+0Hz"
        except Exception:
            pass
        return voice, pitch

    def _fish_tts_read(self, text):
        """Synthesize text with Fish Audio and play it (thread).

        Mirror of _edge_tts_read for the Fish Audio voice.
        Tries twice (a slow internet moment fails once and
        works seconds later). When Fish really fails, this
        one reading falls back to the edge reading so the
        list is always read — the bad day costs the voice,
        not the list.
        """
        try:
            key, ref = self._fish_settings()
            if not key:
                raise RuntimeError("no Fish Audio API key")
            path = str(Path(tempfile.gettempdir())
                       / f"samantha_read_{int(time.time() * 1000) % 100000}.mp3")
            self._samantha_reading = True
            last_error = None
            for _attempt in (1, 2):
                try:
                    self._fish_synthesize(key, ref, text, path)
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    time.sleep(3)
            if last_error is not None:
                raise last_error
            for _ in range(40):
                if not self._samantha_busy():
                    break
                time.sleep(0.2)
            words = len(str(text).split())
            wx.CallAfter(self._play_dynamic_wav, path, words)
        except Exception as e:
            try:
                self.logger.log_error(
                    "FISH TTS read failed: " + str(e)[:200])
            except Exception:
                pass
            # One reading in the backup voice, so the list is
            # still read (see _edge_tts_read's own fallback).
            self._edge_tts_read(text)

    def _edge_tts_read(self, text):
        """Synthesize text with Edge TTS and play it (thread)."""
        try:
            import asyncio
            import edge_tts
            voice, pitch = self._reading_voice()
            path = str(Path(tempfile.gettempdir())
                       / f"samantha_read_{int(time.time() * 1000) % 100000}.mp3")
            self._samantha_reading = True
            # Edge TTS synthesises over the internet, so a slow
            # moment can fail once and work a few seconds later.
            # Try twice before giving up, instead of saying "not
            # ready" on the first blip.
            last_error = None
            for _attempt in (1, 2):
                try:
                    asyncio.run(
                        edge_tts.Communicate(text, voice,
                                             pitch=pitch).save(path))
                    last_error = None
                    break
                except Exception as e:
                    last_error = e
                    time.sleep(3)
            if last_error is not None:
                raise last_error
            # A reading worked: a later failure is a new one,
            # so it may be announced once again then.
            self._edge_tts_read_failed_said = False
            # One voice at a time: wait for any Samantha
            # recording that is still playing ("I'm on it",
            # the guide intro, the greeting) to finish, so
            # the reading never talks over it. At most about
            # 8 seconds; then speak anyway.
            # Ashley, 2026-11-27: this used to wait on the
            # whole mixer's busy flag, which is True whenever
            # ANYTHING is playing — including the show itself
            # on the music stream. So while Classic Doctor Who
            # was playing, every reading waited the full 8
            # seconds for a show that was never going to stop.
            # Now it waits only on Samantha's own channel, so
            # a show playing in the background no longer holds
            # a reading back at all.
            for _ in range(40):
                if not self._samantha_busy():
                    break
                time.sleep(0.2)
            words = len(str(text).split())
            wx.CallAfter(self._play_dynamic_wav, path, words)
        except Exception as e:
            # Edge TTS failed (no internet, library problem).
            # The reason is written to the app log, in plain
            # words, so it can be found instead of vanishing.
            try:
                self.logger.log_error(
                    "EDGE-TTS read failed: " + str(e)[:200])
            except Exception:
                pass
            # Samantha says her reading voice isn't ready, in
            # her own voice — but only once for this failure.
            # The old code said it on EVERY ask while the
            # internet was down, so she heard "not ready"
            # over and over forever. Now the clip is queued
            # only the first time; later asks stay quiet until
            # a reading works again (which clears the flag
            # above) or the app retries by itself. Never NVDA
            # for the list, never Microsoft. Queued behind any
            # clip still playing, so it never talks over her,
            # and _samantha_reading stays up until the clip
            # finishes.
            if not getattr(self, "_edge_tts_read_failed_said", False):
                self._edge_tts_read_failed_said = True
                wx.CallAfter(self._play_samantha_sequence,
                             ["samantha_reading_not_ready.wav"],
                             after=self._clear_samantha_reading)
            else:
                wx.CallAfter(self._clear_samantha_reading)

    def _pip_command_candidates(self):
        """Pythons that can run `python -m pip install`, in order.

        Ashley, 2026-11-27: the install kept failing silently
        on her PC, and one way that happens is sys.executable
        not being a Python at all. When the app runs as a
        frozen program (a .exe built from the code), its
        sys.executable IS that .exe — `AudioVaultTV.exe -m pip
        install` fails, because the .exe is not Python and has
        no pip. So a frozen exe is never used here. First
        choice is still this app's own Python (sys.executable,
        when it really is a python), so the install lands in
        the same Python the app is running in — a `python -m
        pip install` typed in Command Prompt can land in a
        different Python. After that, the plain `py` launcher
        and `python` on the path, in that order.
        """
        candidates = []
        exe = sys.executable or ""
        frozen = bool(getattr(sys, "frozen", False))
        base = os.path.basename(exe).lower()
        if (exe and not frozen
                and (base.startswith("python") or base in ("py.exe", "py"))):
            candidates.append([exe])
        if os.name == "nt":
            candidates += [["py"], ["python"]]
        else:
            candidates += [["python3"], ["python"]]
        seen = set()
        out = []
        for cand in candidates:
            key = tuple(cand)
            if key not in seen:
                seen.add(key)
                out.append(cand)
        return out

    def _run_pip_install(self, packages, extra_args):
        """One pip try for the named packages; returns (ok, error_tail).

        Tries each Python from _pip_command_candidates in turn
        until one of them runs pip. If a Python has no pip at
        all ("No module named pip"), ensurepip is run once for
        that Python and the install is tried again with it,
        before moving on — pip itself missing must not end the
        whole install silently. --disable-pip-version-check
        keeps pip from spending time (and failing) on checking
        for a newer pip first. No window is shown on Windows.
        Each try gets 300 seconds.
        """
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        else:
            startupinfo = None
        last_tail = ["pip could not be run"]
        for cand in self._pip_command_candidates():
            cmd = cand + ["-m", "pip", "install",
                          "--disable-pip-version-check"] \
                + list(extra_args) + list(packages)
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300,
                    startupinfo=startupinfo)
            except subprocess.TimeoutExpired:
                return False, [
                    "pip install " + " ".join(packages)
                    + " timed out after 5 minutes"]
            except (OSError, ValueError):
                continue
            except Exception as e:
                last_tail = [f"could not run pip: {e}"]
                continue
            out = (result.stderr or result.stdout or "").strip()
            tail = out.splitlines()[-5:] if out else []
            if result.returncode == 0:
                return True, []
            last_tail = tail or ["pip failed with no message"]
            if "No module named pip" in out:
                # pip itself is missing for this Python: put
                # it there with ensurepip, then try the install
                # once more with the same Python.
                try:
                    subprocess.run(
                        cand + ["-m", "ensurepip", "--default-pip"],
                        capture_output=True, text=True, timeout=120,
                        startupinfo=startupinfo)
                    result2 = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=300,
                        startupinfo=startupinfo)
                except Exception:
                    continue
                out2 = (result2.stderr or result2.stdout or "").strip()
                if result2.returncode == 0:
                    return True, []
                last_tail = (out2.splitlines()[-5:]
                             if out2 else last_tail)
        return False, last_tail

    def _run_pip_install_edge_tts(self, extra_args):
        """One pip try for edge-tts; returns (ok, error_tail).

        Kept as a thin wrapper over _run_pip_install so the
        reading-voice install keeps working exactly as before.
        """
        return self._run_pip_install(["edge-tts"], extra_args)

    def _plain_install_reason(self, tail):
        """One short plain reason for a failed install.

        Ashley, 2026-11-27: when an install fails she should
        hear a plain reason once, not silence and not "not
        ready" forever. pip's own error lines are jargon, so
        they are turned into plain words here (the full lines
        still go to the app log). Only the reason is returned.
        """
        text = " ".join(tail or []).strip()
        low = text.lower()
        if not text:
            return "the install did not finish and gave no reason"
        if "no module named pip" in low or "no module named ensurepip" in low:
            return "the install tool itself is missing, so nothing could be installed"
        if ("no space left" in low or "disk full" in low
                or "not enough space" in low or "no space on device" in low):
            return "the disk is full, so there is nowhere to put it"
        if ("connection" in low or "failed to establish" in low
                or "name or service not known" in low
                or "temporary failure in name resolution" in low
                or "network is unreachable" in low
                or "connection refused" in low
                or "check your internet" in low):
            return "there is no internet connection right now"
        if "timed out" in low or "timeout" in low:
            return "the install took too long and gave up"
        if ("permission denied" in low or "access is denied" in low
                or "consider using the --user option" in low
                or "externally-managed-environment" in low
                or "operation not permitted" in low):
            return "Windows would not let the app write the files"
        if "could not find a version" in low:
            return "the package could not be found"
        if "no matching distribution" in low:
            return "the package could not be found for this computer"
        line = [ln.strip() for ln in (tail or []) if ln.strip()]
        if line:
            return line[-1][:120]
        return "the install did not finish"

    def _library_available(self, import_name):
        """True when the named library can be found right now.

        Uses find_spec, which only looks for the library on
        disk instead of importing it — importing some of these
        in a background thread would be slow, and a failed
        import can stick in sys.modules and hide a library
        pip has just put there.
        """
        try:
            import importlib.util
            return importlib.util.find_spec(import_name) is not None
        except Exception:
            return False

    def _install_one_library(self, import_name, pip_name):
        """Install one library if it is missing; returns (ok, reason).

        Nothing is installed when the library is already there.
        Otherwise pip is tried once normally, then once
        per-user with --user (which works when the normal one
        is blocked by permissions), and the library is only
        counted as installed after it can really be found on
        disk in this same process. The plain reason for a
        failure is returned, so Samantha can say it once.
        """
        if self._library_available(import_name):
            return True, None
        try:
            import importlib
            importlib.invalidate_caches()
        except Exception:
            pass
        ok, tail = self._run_pip_install([pip_name], [])
        if not ok:
            ok, tail2 = self._run_pip_install([pip_name], ["--user"])
            tail = tail + tail2
        if ok:
            try:
                import importlib
                importlib.invalidate_caches()
            except Exception:
                pass
            if self._library_available(import_name):
                return True, None
            ok = False
            tail = tail + ["installed, but the library still cannot be found"]
        return False, self._plain_install_reason(tail)

    def _announce_edge_install_started(self):
        """Samantha says she is installing her reading voice.

        Queued behind anything already playing (the startup
        greeting), in her own recorded voice — "I'm on it" —
        so Ashley hears the install is actually happening
        instead of wondering in silence. Said once per try.
        """
        if getattr(self, "_edge_install_state", None) != "installing":
            return
        if getattr(self, "_edge_install_started_announced", False):
            return
        self._edge_install_started_announced = True
        try:
            self._queue_samantha_sound("samantha_im_on_it.wav")
        except Exception:
            pass

    def _schedule_edge_install_retry(self):
        """Try the install again in 1 minute, on a timer.

        Ashley, 2026-11-26: a failed install used to sit
        there until she asked for the list again (or opened
        Command Prompt). Now the app retries by itself every
        minute while the voice is not ready, so she
        only has to open the app and wait. Only one timer
        is ever scheduled at a time.
        """
        if getattr(self, "_samantha_voice_mode_cache", None) == "edge":
            return
        if getattr(self, "_edge_install_state", None) == "ready":
            return
        timer = getattr(self, "_edge_install_retry_timer", None)
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass
        try:
            self._edge_install_retry_timer = wx.CallLater(
                60000, self._edge_install_retry_tick)
        except Exception:
            pass

    def _edge_install_retry_tick(self):
        """The 1-minute retry timer fired: try again, once."""
        self._edge_install_retry_timer = None
        if self._samantha_voice_mode() == "edge":
            return
        if getattr(self, "_edge_install_running", False):
            self._schedule_edge_install_retry()
            return
        threading.Thread(target=self._ensure_edge_tts,
                         daemon=True).start()

    def _edge_tts_is_vendored(self):
        """True when edge-tts imports from the vendor/ folder
        shipped with the app (not from a pip install).

        Ashley, 2026-11-27: the reading voice ships in the
        app folder now, so on a normal open it is already
        there. This tells the diagnostic (see
        _say_reading_voice_status) and the log which copy is
        in use, so a vendored library is never mistaken for a
        failed pip install.
        """
        try:
            import importlib.util
            spec = importlib.util.find_spec("edge_tts")
        except Exception:
            return False
        if spec is None or not getattr(spec, "origin", None):
            return False
        vendor = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "vendor")
        try:
            return os.path.abspath(spec.origin).startswith(
                os.path.abspath(vendor) + os.sep)
        except Exception:
            return False

    def _ensure_edge_tts(self, force=False):
        """Get Samantha's reading voice ready, in the background.

        Ashley, 2026-11-27: the reading voice now ships WITH
        the app in the vendor/ folder (see the top of this
        file), so on a normal open the library already imports
        and nothing is installed at all — the first check below
        finds it and marks the voice ready at once. pip is only
        a fallback for a computer where vendor/ is missing.
        The last failure's plain reason is kept in
        _edge_install_last_reason, so Ashley can ask "why is
        my reading voice not ready" and be told it (see
        _say_reading_voice_status) instead of us guessing.

        Ashley, 2026-11-26: she kept hearing "My reading voice
        isn't ready yet" instead of the list, and she does not
        know how to get that voice set up — and she should
        never have to use Command Prompt for it. The install
        the app does itself:
        - If edge-tts already imports, nothing is installed at
          all — the old code re-ran pip on nearly every start.
        - The startup thread used to start before the install
          lock even existed, so it could return silently and
          no install ever happened. The lock is now defined
          before the thread starts, and if it is somehow
          missing here a lock is created instead of returning
          silently.
        - Samantha says "I'm on it" in her own recorded voice
          while it installs, so Ashley hears it happening.
          When it is ready she says so in the reading voice
          (see _on_edge_install_ready), and any list she asked
          for is read then — she does not have to ask again.
        - If a try fails, Samantha says "not ready" once for
          that failure (see _on_edge_install_failed), and the
          app retries by itself every 1 minute while the
          voice is not ready — no asking again, no Command
          Prompt. A failed try is never cached as "not ready"
          for the run, and the pip error tail is written to
          the app log (mp3_player_log.txt, "EDGE-TTS install
          failed: ...") instead of vanishing.
        - pip is tried twice per attempt: first normally, then
          once with --user (a per-user install, which works
          when the normal one is blocked by permissions).
          An install only counts as ready after edge-tts is
          re-imported in this same process (see
          _edge_import_ok(force_recheck=True)). No NVDA and
          no Microsoft voice is ever used instead.
        force=True (an explicit "install my reading voice")
        skips the 60-second gap between tries.
        """
        if getattr(self, "_vosk_model_running", False):
            # The listening-model download is running: do not
            # start a pip install at the same time. Retry by
            # ourselves in a minute instead.
            self._schedule_edge_install_retry()
            return
        lock = getattr(self, "_edge_install_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._edge_install_lock = lock
        attempted = False
        with lock:
            if getattr(self, "_edge_install_running", False):
                return
            self._edge_install_running = True
            attempted = True
        try:
            self._edge_install_state = "checking"
            if self._edge_import_ok():
                self._edge_install_state = "ready"
                # Ashley, 2026-11-28: when the Fish Audio voice
                # is configured, edge is only the backup, so
                # the reading voice must not flip to edge.
                if self._samantha_voice_mode_cache != "fish":
                    self._samantha_voice_mode_cache = "edge"
                # Vendored (shipped with the app) or pip: the
                # diagnostic says which, and a past failure's
                # reason is cleared now the voice is ready.
                self._edge_install_source = (
                    "vendor" if self._edge_tts_is_vendored() else "pip")
                self._edge_install_last_reason = None
                self._write_edge_flag(True)
                wx.CallAfter(self._on_edge_install_ready)
                return
            self._edge_install_state = "installing"
            self._edge_install_started_announced = False
            self._edge_install_last_try = time.time()
            wx.CallAfter(self._announce_edge_install_started)
            pip_ok, pip_tail = self._run_pip_install_edge_tts([])
            if not (pip_ok and self._edge_import_ok(force_recheck=True)):
                # The normal install did not work (or pip said
                # it worked but the library still does not
                # import): try once per-user before giving up.
                pip_ok2, pip_tail2 = self._run_pip_install_edge_tts(
                    ["--user"])
                pip_tail = pip_tail + pip_tail2
                pip_ok = pip_ok2
            if pip_ok and self._edge_import_ok(force_recheck=True):
                self._edge_install_state = "ready"
                # Fish, when configured, stays the reading
                # voice — edge here is the backup only.
                if self._samantha_voice_mode_cache != "fish":
                    self._samantha_voice_mode_cache = "edge"
                self._edge_install_source = "pip"
                self._edge_install_last_reason = None
                self._edge_install_started_announced = False
                self._write_edge_flag(True)
                wx.CallAfter(self._on_edge_install_ready)
                return
            self._edge_install_state = "failed"
            self._edge_install_started_announced = False
            # Keep the plain reason for this failure, so
            # "why is my reading voice not ready" can say it.
            self._edge_install_last_reason = \
                self._plain_install_reason(pip_tail)
            self._edge_install_fail_count = \
                getattr(self, "_edge_install_fail_count", 0) + 1
            self._write_edge_flag(False)
            try:
                self.logger.log_error(
                    "EDGE-TTS install failed: " + " | ".join(pip_tail))
            except Exception:
                pass
            wx.CallAfter(self._on_edge_install_failed)
        except Exception as e:
            # Something unexpected went wrong inside the
            # install itself (not pip failing — for example a
            # wx call before the main loop was ready). The old
            # code had no handler here at all: the background
            # thread just died, the state stayed stuck on
            # "installing" forever, Samantha kept saying "I'm
            # on it" and never said "not ready", and nothing
            # ever retried. Now it counts as a failed try
            # instead: the reason is logged, Samantha says
            # "not ready" once, and the app retries by itself
            # in 1 minute. A try that already counted as ready
            # is never re-marked as failed by this.
            if getattr(self, "_edge_install_state", None) != "ready":
                self._edge_install_state = "failed"
                self._edge_install_fail_count = \
                    getattr(self, "_edge_install_fail_count", 0) + 1
                self._edge_install_last_reason = \
                    "the install ran into a problem before it could finish"
                try:
                    self._write_edge_flag(False)
                except Exception:
                    pass
                try:
                    self.logger.log_error(
                        "EDGE-TTS install error: " + str(e)[:200])
                except Exception:
                    pass
                try:
                    wx.CallAfter(self._on_edge_install_failed)
                except Exception:
                    pass
        finally:
            self._edge_install_running = False
            if attempted:
                # The reading voice is dealt with (ready or
                # failed): go on to every other library the
                # app needs, in the background, one at a time
                # (see _ensure_requirements). This is also how
                # the 1-minute retry covers all of them, not
                # just the reading voice.
                threading.Thread(target=self._ensure_requirements,
                                 daemon=True).start()

    def _on_edge_install_ready(self):
        """The reading voice is ready (main thread).

        Ashley, 2026-11-26: "have her tell me when the
        install is finished." So Samantha ALWAYS says so
        now, in the reading voice itself, when the install
        finishes — not only when Ashley asked for the voice
        or for a list. If she asked for a reading while it
        installed, read it to her now — she should not have
        to ask again. Otherwise say plainly that the reading
        voice is ready now, so she knows the moment it is
        finished, right when she opens the program.
        """
        pending = getattr(self, "_pending_reading_text", None)
        self._pending_reading_text = None
        self._edge_install_explicit = False
        # No more retries are needed once the voice is ready.
        timer = getattr(self, "_edge_install_retry_timer", None)
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass
        self._edge_install_retry_timer = None
        if pending:
            self._say_in_samantha_voice(pending)
            return
        # Ashley, 2026-11-28: with the Fish Audio voice
        # configured, the reading voice is ready the moment
        # the app opens — nothing was installed for it, so
        # announcing "the reading voice is ready" about the
        # backup voice (edge) would only be confusing.
        if self._samantha_voice_mode() == "fish":
            return
        self._say_in_samantha_voice(
            "My reading voice is ready now. "
            "Ask me to list your shows.")

    def _on_edge_install_failed(self):
        """The install failed (main thread).

        Samantha says so herself, in her own recorded voice —
        "My reading voice isn't ready yet. Give me a moment,
        then ask me again." — once for this failure, whether
        or not she was waiting for a reading. She does NOT
        just go silent afterwards: the app also schedules
        another try by itself in 1 minute (see
        _schedule_edge_install_retry), so Ashley does not
        have to ask again or open Command Prompt. Never NVDA,
        never Microsoft. The pending reading (if any) is kept
        out of the way — it will be asked for again, or the
        retry will make the voice ready first.
        """
        self._edge_install_explicit = False
        pending = getattr(self, "_pending_reading_text", None)
        self._pending_reading_text = None
        # Retry by itself in 1 minute, even if she says
        # nothing — this is what makes Command Prompt
        # unnecessary.
        self._schedule_edge_install_retry()
        if pending:
            self._edge_install_not_ready_said = \
                getattr(self, "_edge_install_fail_count", 0)
            self._samantha_reading = True
            self._play_samantha_sequence(
                ["samantha_reading_not_ready.wav"],
                after=self._clear_samantha_reading)
            return
        if (getattr(self, "_edge_install_not_ready_said", 0)
                != getattr(self, "_edge_install_fail_count", 0)):
            self._edge_install_not_ready_said = \
                getattr(self, "_edge_install_fail_count", 0)
            self._samantha_reading = True
            self._play_samantha_sequence(
                ["samantha_reading_not_ready.wav"],
                after=self._clear_samantha_reading)

    def _say_reading_voice_status(self):
        """Say why the reading voice is or is not ready.

        Ashley, 2026-11-27: "why is my reading voice not
        ready" / "what happened to my reading voice". She
        kept hearing "not ready" with no reason, and nobody
        could tell her why without guessing. This is the
        checkable diagnostic: it reports the last install
        state and the plain reason for the last failure, in
        her own voice when the reading voice is up — and the
        full pip error tail is always in the app log
        (mp3_player_log.txt, "EDGE-TTS install failed: ..." /
        "REQUIREMENTS install failed: ..."). Never NVDA,
        never Microsoft, no new voice files.
        Honest limit: when the reading voice itself is down,
        there is no voice that can speak the reason out loud
        — Samantha's recorded clips cannot say words she
        never recorded. Then she hears the "not ready" clip
        once (it is the only voice available) and the plain
        reason is on the status line and in the log, so it can
        be read back to her. When the voice is up, she hears
        the whole reason spoken.
        """
        # Ashley, 2026-11-28: with the Fish Audio voice
        # configured there is no install to diagnose — the
        # voice is ready the moment the app opens.
        if self._samantha_voice_mode() == "fish":
            self._say_in_samantha_voice(
                "My reading voice is ready. It is the Fish "
                "Audio voice.")
            return
        state = getattr(self, "_edge_install_state", "unknown")
        reason = getattr(self, "_edge_install_last_reason", None)
        req_reasons = getattr(self, "_requirements_last_reason", {}) or {}
        if self._samantha_voice_mode() == "edge":
            if state == "ready":
                source = getattr(self, "_edge_install_source", None)
                where = ("shipped with the app" if source == "vendor"
                         else "installed on this computer")
                text = ("My reading voice is ready now. It is "
                        + where + ". Ask me to list your shows.")
            elif state in ("installing", "checking") or (
                    state == "unknown"
                    and getattr(self, "_edge_install_running", False)):
                text = ("I am still getting my reading voice ready. "
                        "Give me a moment, then ask me again.")
            else:
                bits = []
                if reason:
                    bits.append(reason)
                for _name, r in sorted(req_reasons.items()):
                    if r:
                        bits.append(r)
                why = (" " + " ".join(bits)) if bits else ""
                text = ("My reading voice is not ready." + why
                        + " I will try again by myself in a minute."
                        " You can also say, install everything I need.")
            self._say_in_samantha_voice(text)
            return
        # The reading voice is down, so the reason cannot be
        # spoken — but it is still shown and logged, and the
        # "not ready" clip is said once, not on every ask.
        bits = []
        if reason:
            bits.append(reason)
        for _name, r in sorted(req_reasons.items()):
            if r:
                bits.append(r)
        why = (" " + " ".join(bits)) if bits else ""
        msg = "My reading voice is not ready." + why
        try:
            self.status_label.SetLabel(msg)
        except Exception:
            pass
        try:
            self.logger.log_error("READING VOICE STATUS: " + msg)
        except Exception:
            pass
        if state == "failed":
            # A try really failed: the "not ready" clip, once
            # for that failure (see _say_in_samantha_voice).
            self._say_in_samantha_voice(msg)
            return
        # Still on its way, or never tried yet: "I'm on it".
        # The status words are NOT kept as a pending reading
        # — they say "not ready", and would be wrong by the
        # time the voice is ready and reads them.
        self._samantha_reading = True
        self._queue_samantha_sound(
            "samantha_im_on_it.wav",
            after=self._clear_samantha_reading)
        if state == "unknown" and not getattr(
                self, "_edge_install_running", False):
            threading.Thread(target=self._ensure_edge_tts,
                             daemon=True).start()

    def _on_install_reading_voice(self, event=None):
        """Menu / voice: get Samantha's reading voice ready.

        Ashley, 2026-11-26: she does not know how to get the
        reading voice set up, and the silent background install
        gave her nothing to check. This is the one checkable
        step in the app: Samantha says "I'm on it", the install
        runs in the background, and when it is ready she says
        so in the reading voice; if it fails she says her
        reading voice isn't ready yet, and the app retries by
        itself in 1 minute. An explicit ask always forces a
        fresh try right now, even if a try just failed a
        moment ago — it is not held back by the 60-second gap
        between automatic tries. If the voice is already
        ready, she just says so instead of installing again.
        No Command Prompt step is needed for any of this.
        """
        if self._samantha_voice_mode() == "edge":
            self._edge_install_explicit = False
            self._say_in_samantha_voice(
                "My reading voice is ready now. "
                "Ask me to list your shows.")
            return
        self._edge_install_explicit = True
        self._edge_install_last_try = 0.0
        self.status_label.SetLabel("Getting Samantha's reading voice ready...")
        self._play_sound_effect("samantha_im_on_it.wav")
        threading.Thread(target=self._ensure_edge_tts, args=(True,),
                         daemon=True).start()

    def _requirements_should_retry(self, force=False):
        """True when a new requirements pass may start.

        Never while a pass is already running, and not within
        a minute of the last pass, so asking twice in a row
        does not start two install loops. force=True (an
        explicit "install everything I need") skips the gap
        but still never starts a second pass while one runs.
        """
        if getattr(self, "_requirements_running", False):
            return False
        if getattr(self, "_edge_install_running", False):
            return False
        if getattr(self, "_vosk_model_running", False):
            return False
        if force:
            return True
        try:
            last = float(getattr(self, "_requirements_last_try", 0) or 0)
        except Exception:
            last = 0
        return (time.time() - last) > 60

    def _announce_requirements_started(self):
        """Samantha says she is getting things ready.

        Queued behind anything already playing (the startup
        greeting), in her own recorded voice — "I'm on it" —
        so Ashley hears the installs are actually happening
        instead of wondering in silence. Said once per pass.
        """
        if getattr(self, "_requirements_announced_started", False):
            return
        self._requirements_announced_started = True
        try:
            self._queue_samantha_sound("samantha_im_on_it.wav")
        except Exception:
            pass

    # ---- Listening model (Vosk) ----
    def _vosk_model_dir(self):
        """Folder the Vosk listening model lives in, beside main.py."""
        return Path(__file__).parent / _VOSK_MODEL_NAME

    def _vosk_model_present(self):
        """True when the listening model folder is really there.

        A folder with nothing in it (a failed unzip) does not
        count — VoiceControl would still fail on it.
        """
        try:
            d = self._vosk_model_dir()
            return d.is_dir() and any(d.iterdir())
        except Exception:
            return False

    def _vosk_model_should_retry(self, force=False):
        """True when a new model install attempt may start.

        Never within a minute of the last try, so asking
        twice in a row does not start two downloads.
        force=True (an explicit "install the listening
        model") skips the 60-second gap — she asked for it
        now. A second install while one runs is already
        prevented by _ensure_vosk_model's lock, so this
        does NOT check _vosk_model_running itself: the
        lock is set before this is called, and checking it
        here would block every try, including the first.
        Also never while a pip install is running (edge /
        requirements): one install at a time, so they cannot
        fight each other.
        """
        if (getattr(self, "_edge_install_running", False)
                or getattr(self, "_requirements_running", False)):
            return False
        if force:
            return True
        try:
            last = float(getattr(self, "_vosk_model_last_try", 0) or 0)
        except Exception:
            last = 0
        return (time.time() - last) > 60

    def _write_vosk_flag(self, ok):
        """Record today's model install result, so a failure is retried."""
        try:
            flag = Path(tempfile.gettempdir()) / "audiovault_vosk_model_tried.txt"
            today = time.strftime("%Y-%m-%d")
            flag.write_text(today + (":ok" if ok else ":fail"))
        except Exception:
            pass

    def _try_create_voice_control(self):
        """Create VoiceControl() now, if it can be created.

        Returns True when listening is available afterwards.
        Used wherever voice control is needed — the toggles,
        _reload_missing_modules, and the model install — so
        a model that appears after startup is picked up
        without restarting the app. A missing model is a
        plain FileNotFoundError from VoiceControl(); a missing
        vosk library is an ImportError. Neither is silent:
        the reason is kept for "why can't you hear me".
        """
        global VoiceControl, VOICE_CONTROL_AVAILABLE
        if getattr(self, "voice", None) is not None:
            self.voice_available = True
            return True
        if VoiceControl is None:
            try:
                import voice_control as _vc
                VoiceControl = _vc.VoiceControl
                VOICE_CONTROL_AVAILABLE = True
            except Exception as e:
                self.voice_available = False
                self._voice_last_error = str(e)[:200]
                return False
        try:
            self.voice = VoiceControl(
                model_path=str(self._vosk_model_dir()))
            self.voice_available = True
            return True
        except FileNotFoundError:
            self.voice = None
            self.voice_available = False
            if getattr(self, "_vosk_model_state", None) not in (
                    "installing", "checking"):
                self._vosk_model_last_reason = (
                    "the listening model is not downloaded yet")
            return False
        except Exception as e:
            self.voice = None
            self.voice_available = False
            self._voice_last_error = str(e)[:200]
            try:
                self.logger.log_error(
                    "VOICE CONTROL: could not start listening: "
                    + str(e)[:200])
            except Exception:
                pass
            return False

    def _announce_vosk_model_started(self):
        """Samantha says she is getting listening ready.

        Queued behind anything already playing (the startup
        greeting), in her own recorded voice — "I'm on it" —
        so Ashley hears the download is actually happening
        instead of wondering in silence. Said once per try.
        """
        if getattr(self, "_vosk_model_state", None) != "installing":
            return
        if getattr(self, "_vosk_model_started_announced", False):
            return
        self._vosk_model_started_announced = True
        try:
            self._queue_samantha_sound("samantha_im_on_it.wav")
        except Exception:
            pass

    def _schedule_vosk_model_retry(self):
        """Try the model install again in 1 minute, on a timer.

        Ashley, 2026-11-27: a failed download used to sit
        there until she asked again (or opened Command
        Prompt). Now the app retries by itself every minute
        while listening is not ready, so she only has to open
        the app and wait. Only one timer is ever scheduled
        at a time.
        """
        if getattr(self, "_vosk_model_state", None) == "ready":
            return
        timer = getattr(self, "_vosk_model_retry_timer", None)
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass
        try:
            self._vosk_model_retry_timer = wx.CallLater(
                60000, self._vosk_model_retry_tick)
        except Exception:
            pass

    def _vosk_model_retry_tick(self):
        """The 1-minute retry timer fired: try again, once."""
        self._vosk_model_retry_timer = None
        if getattr(self, "_vosk_model_state", None) == "ready":
            return
        if getattr(self, "_vosk_model_running", False):
            self._schedule_vosk_model_retry()
            return
        threading.Thread(target=self._ensure_vosk_model,
                         daemon=True).start()

    def _ensure_vosk_model(self, force=False):
        """Download and install the Vosk listening model itself.

        Ashley, 2026-11-27: "Why can't you just update the
        code to make her listen?" The listening model was the
        missing piece nobody downloaded: _ensure_requirements
        only pip-installed libraries, and VoiceControl()
        raises FileNotFoundError when the model folder is not
        beside main.py, so voice_available stayed False for
        the whole run — while the reading voice (Edge TTS)
        said it was ready, which is a different thing
        entirely. This gets the model, in the background:
        - If the model folder is already there, nothing is
          downloaded at all. VoiceControl() is created now
          (see _try_create_voice_control), so listening
          comes alive without a restart.
        - Otherwise the 40 MB zip is downloaded from
          alphacephei.com, unzipped beside main.py, and a
          double-nested folder (model folder inside a model
          folder, the usual unzip mistake) is flattened, so
          the model ends up exactly where VoiceControl()
          looks for it.
        - Disk space is checked first: under 200 MB free
          fails plainly instead of filling the disk.
        - No internet, a bad download, or a bad zip fails
          with a plain reason (see _plain_install_reason),
          Samantha says so once in her own voice (see
          _on_vosk_model_failed), and the app retries by
          itself in 1 minute.
        - One install at a time: if a pip install (edge /
          requirements) is running, this waits and retries
          later instead of starting a second install.
        - Samantha says "I'm on it" while it downloads, and
          when it is ready she says she can hear now (see
          _on_vosk_model_ready). She never starts listening
          by herself — press-to-talk only (see _rearm_listening).
          No NVDA, no Microsoft voice, no Command Prompt,
          no new voice files.
        force=True (an explicit "install the listening
        model") skips the 60-second gap between tries.
        """
        lock = getattr(self, "_vosk_model_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._vosk_model_lock = lock
        attempted = False
        with lock:
            if getattr(self, "_vosk_model_running", False):
                return
            self._vosk_model_running = True
            attempted = True
        try:
            if (getattr(self, "_edge_install_running", False)
                    or getattr(self, "_requirements_running", False)):
                # A pip install is running: wait for it, then
                # retry by ourselves in a minute, instead of
                # starting a second install at the same time.
                self._schedule_vosk_model_retry()
                return
            self._vosk_model_state = "checking"
            if self._vosk_model_present():
                was_available = getattr(self, "voice_available", False)
                if self._try_create_voice_control():
                    # Only announce (and start listening) when
                    # listening was NOT available before this
                    # check: at startup, when VoiceControl()
                    # already worked in __init__, the greeting
                    # flow owns listening and nothing extra is
                    # said. But if the model appeared after
                    # startup (dropped in by hand, or a retry
                    # after a failure), announce it now.
                    self._vosk_model_state = "ready"
                    self._vosk_model_last_reason = None
                    self._write_vosk_flag(True)
                    if not was_available:
                        wx.CallAfter(self._on_vosk_model_ready)
                    return
                # Model folder is there but listening still
                # cannot start (vosk library missing, or the
                # model cannot be loaded): count it as a
                # failed try, so it is retried, and say why.
                self._vosk_model_state = "failed"
                self._vosk_model_fail_count = \
                    getattr(self, "_vosk_model_fail_count", 0) + 1
                if VoiceControl is None:
                    self._vosk_model_last_reason = (
                        "the voice listening library is not ready yet")
                else:
                    self._vosk_model_last_reason = (
                        "the listening model could not be loaded")
                self._write_vosk_flag(False)
                try:
                    self.logger.log_error(
                        "VOSK MODEL install failed: "
                        + str(self._vosk_model_last_reason))
                except Exception:
                    pass
                wx.CallAfter(self._on_vosk_model_failed)
                return
            if not self._vosk_model_should_retry(force=force):
                return
            self._vosk_model_state = "installing"
            self._vosk_model_started_announced = False
            self._vosk_model_last_try = time.time()
            self._listening_not_ready_announced = False
            wx.CallAfter(self._announce_vosk_model_started)
            # Disk space first: the zip plus the extracted
            # model need room, and a full disk was already
            # one of her failures (2026-11-21).
            try:
                import shutil as _shutil
                free = _shutil.disk_usage(
                    str(Path(__file__).parent)).free
            except Exception:
                free = _VOSK_MODEL_MIN_FREE_BYTES
            if free < _VOSK_MODEL_MIN_FREE_BYTES:
                raise OSError("No space left on device")
            # Download the zip, in chunks, to a temp file.
            import urllib.request
            import urllib.error
            tmp_dir = Path(tempfile.gettempdir())
            zip_path = tmp_dir / (
                "vosk-model-small-en-us-0.15-"
                + str(int(time.time())) + ".zip")
            extract_dir = tmp_dir / (
                "vosk-model-extract-"
                + str(int(time.time())))
            try:
                with urllib.request.urlopen(
                        _VOSK_MODEL_URL, timeout=120) as resp, \
                        open(zip_path, "wb") as out:
                    while True:
                        chunk = resp.read(1024 * 1024)
                        if not chunk:
                            break
                        out.write(chunk)
                if not zip_path.exists() or zip_path.stat().st_size < 1_000_000:
                    raise ValueError("download did not finish")
                extract_dir.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(str(zip_path)) as zf:
                    zf.extractall(str(extract_dir))
                # Find the model folder inside the zip: it is
                # usually at the top level, but a double-nested
                # folder (model inside a model folder, the
                # usual unzip mistake) is flattened here, so
                # it ends up exactly where VoiceControl()
                # looks for it. Prefer a folder that actually
                # holds model files (am/ or conf/) — the outer
                # folder of a double-nested zip only holds the
                # inner folder, so picking the first match
                # would leave the model one level too deep
                # and VoiceControl() would still fail on it.
                cands = [c for c in extract_dir.rglob(_VOSK_MODEL_NAME)
                         if c.is_dir()]
                cands.sort(key=lambda c: len(c.parts), reverse=True)
                found = None
                for cand in cands:
                    if (cand / "am").is_dir() or (cand / "conf").is_dir():
                        found = cand
                        break
                if found is None and cands:
                    found = cands[0]
                if found is None:
                    raise ValueError(
                        "downloaded file did not contain the listening model")
                target = self._vosk_model_dir()
                if target.exists():
                    shutil.rmtree(str(target), ignore_errors=True)
                shutil.move(str(found), str(target))
                if not self._vosk_model_present():
                    raise ValueError(
                        "listening model could not be put in place")
            finally:
                try:
                    zip_path.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    shutil.rmtree(str(extract_dir), ignore_errors=True)
                except Exception:
                    pass
            self._vosk_model_state = "ready"
            self._vosk_model_last_reason = None
            self._write_vosk_flag(True)
            if self._try_create_voice_control():
                wx.CallAfter(self._on_vosk_model_ready)
            else:
                # The model is on disk now, but listening
                # still cannot start: retry, and say why.
                self._vosk_model_state = "failed"
                self._vosk_model_fail_count = \
                    getattr(self, "_vosk_model_fail_count", 0) + 1
                self._vosk_model_last_reason = (
                    "the listening model could not be loaded")
                try:
                    self.logger.log_error(
                        "VOSK MODEL install failed: "
                        "model downloaded but voice control "
                        "could not be created")
                except Exception:
                    pass
                wx.CallAfter(self._on_vosk_model_failed)
        except Exception as e:
            # A download / unzip failure, or the disk-space
            # check above: a plain reason, logged, said once,
            # retried by itself in a minute. A try that
            # already counted as ready is never re-marked.
            if getattr(self, "_vosk_model_state", None) != "ready":
                self._vosk_model_state = "failed"
                self._vosk_model_fail_count = \
                    getattr(self, "_vosk_model_fail_count", 0) + 1
                self._vosk_model_last_reason = \
                    self._plain_install_reason([str(e)[:200]])
                try:
                    self._write_vosk_flag(False)
                except Exception:
                    pass
                try:
                    self.logger.log_error(
                        "VOSK MODEL install failed: " + str(e)[:200])
                except Exception:
                    pass
                try:
                    wx.CallAfter(self._on_vosk_model_failed)
                except Exception:
                    pass
        finally:
            self._vosk_model_running = False

    def _on_vosk_model_ready(self):
        """The listening model is ready (main thread).

        Ashley, 2026-11-27: "have her tell me when the
        install is finished" — for listening, as for the
        reading voice. Samantha says she can hear now, in
        her own voice (the reading voice when it is up, or
        her recorded "Yes?" clip when it is not — the words
        themselves cannot be spoken without the reading
        voice), and then waits for her to press a button —
        press-to-talk only, Ashley 2026-11-27: she never
        starts listening by herself. Only announced when
        listening was NOT available before: when the model
        was already there at startup, the greeting flow owns
        listening and nothing extra is said. The
        "cannot hear yet" flag is cleared, so a later
        failure may be announced again.
        """
        timer = getattr(self, "_vosk_model_retry_timer", None)
        if timer is not None:
            try:
                timer.Stop()
            except Exception:
                pass
        self._vosk_model_retry_timer = None
        self._listening_not_ready_announced = False
        self._vosk_model_explicit = False
        if not getattr(self, "voice_available", False):
            return
        self._answer_in_samantha_voice(
            "I can hear you now. Ask me to list your shows.",
            "samantha_yes.wav")
        # Press-to-talk only, Ashley 2026-11-27: do NOT start
        # listening here. This used to call
        # _listen_after_greeting, which started listening by
        # itself the moment the model finished installing —
        # in the background, while a show was playing. Now
        # Samantha just announces she can hear, and waits
        # for Ctrl+Shift+B (one turn) or Ctrl+Shift+W
        # (wake-word mode).

    def _on_vosk_model_failed(self):
        """The model install failed (main thread).

        Samantha says so herself, in her own voice — the
        "Excuse me" clip when the reading voice is down
        (the reason itself cannot be spoken without it, so
        it is on the status line and in the log instead),
        or the full plain reason in the reading voice when
        it is up — once for this failure, whether or not she
        was waiting to listen. She does NOT just go silent:
        the app also schedules another try by itself in 1
        minute (see _schedule_vosk_model_retry), so Ashley
        does not have to ask again or open Command Prompt.
        Never NVDA, never Microsoft.
        """
        self._vosk_model_explicit = False
        self._schedule_vosk_model_retry()
        if (getattr(self, "_vosk_model_not_ready_said", 0)
                == getattr(self, "_vosk_model_fail_count", 0)):
            return
        self._vosk_model_not_ready_said = \
            getattr(self, "_vosk_model_fail_count", 0)
        reason = getattr(self, "_vosk_model_last_reason", None)
        msg = "I still cannot hear you."
        if reason:
            msg += " " + str(reason) + "."
        msg += " I will try again by myself in a minute."
        self._answer_in_samantha_voice(msg, "samantha_excuse_me.wav")

    def _listening_not_ready_reason(self):
        """Plain words for why Samantha cannot hear yet, or None."""
        if getattr(self, "voice_available", False):
            return None
        state = getattr(self, "_vosk_model_state", "unknown")
        reason = getattr(self, "_vosk_model_last_reason", None)
        if state in ("installing", "checking"):
            return "I am still getting my listening ready"
        if state == "failed":
            if reason:
                return "I cannot hear you yet. " + str(reason)
            return "I cannot hear you yet. The listening model did not install"
        if reason:
            return "I cannot hear you yet. " + str(reason)
        return "I cannot hear you yet. The listening model is not ready yet"

    def _say_listening_not_ready(self, force=False):
        """Say, in Samantha's voice, that she cannot hear yet.

        Ashley, 2026-11-27: when listening is not available,
        pressing Ctrl+Shift+B / Ctrl+Shift+W, or answering
        the greeting, used to be met with silence (NVDA
        speak() while NVDA quiet is on). Now Samantha says
        so herself: the full plain reason in her reading
        voice when it is up, or her recorded "Excuse me"
        clip when it is not (see _answer_in_samantha_voice),
        with the reason on the status line either way.
        force=False (the greeting path) says it only once
        per install attempt; force=True (an explicit press,
        or "can you hear me") always answers. Kicks the
        model install off if it is not already running.
        Returns True when something was said.
        """
        if getattr(self, "voice_available", False):
            return False
        if not force and getattr(
                self, "_listening_not_ready_announced", False):
            return False
        self._listening_not_ready_announced = True
        msg = self._listening_not_ready_reason() or (
            "I cannot hear you yet. The listening model is not ready yet")
        msg += (" I will try again by myself in a minute."
                " You can also say, install the listening model.")
        try:
            self.status_label.SetLabel(msg)
        except Exception:
            pass
        self._answer_in_samantha_voice(msg, "samantha_excuse_me.wav")
        if not getattr(self, "_vosk_model_running", False):
            try:
                threading.Thread(target=self._ensure_vosk_model,
                                 daemon=True).start()
            except Exception:
                pass
        return True

    def _say_listening_status(self):
        """Answer "why can't you hear me" honestly, in her voice."""
        if getattr(self, "voice_available", False):
            self._play_sound_effect("samantha_yes_i_can.wav")
            msg = "Yes, I can hear you."
            try:
                self.status_label.SetLabel(msg)
            except Exception:
                pass
            return
        self._say_listening_not_ready(force=True)

    def _on_install_listening_model(self, event=None):
        """Menu / voice: get Samantha listening.

        Ashley, 2026-11-27: "install the listening model" /
        "get Samantha listening" — the one checkable step in
        the app for listening, like "install my reading voice"
        is for the reading voice. Samantha says "I'm on it",
        the download runs in the background, and when it is
        ready she says she can hear now (see
        _on_vosk_model_ready); if it fails she says why, and
        the app retries by itself in 1 minute. An explicit
        ask always forces a fresh try right now, even if a
        try just failed a moment ago. If she can already
        hear, she just says so instead of downloading again.
        No Command Prompt step is needed for any of this.
        """
        if getattr(self, "voice_available", False) \
                and self._vosk_model_present():
            self._vosk_model_explicit = False
            self._answer_in_samantha_voice(
                "I can hear you now. Ask me to list your shows.",
                "samantha_yes_i_can.wav")
            return
        self._vosk_model_explicit = True
        self._vosk_model_last_try = 0.0
        self._listening_not_ready_announced = False
        try:
            self.status_label.SetLabel(
                "Getting Samantha listening ready...")
        except Exception:
            pass
        self._play_sound_effect("samantha_im_on_it.wav")
        threading.Thread(target=self._ensure_vosk_model, args=(True,),
                         daemon=True).start()

    def _reload_missing_modules(self):
        """Load the libraries that were missing at startup.

        Ashley, 2026-11-27: a library that was not there when
        the app opened used to keep the whole app from
        starting, because its import ran at the top of the
        file. Now those imports are guarded, the app opens,
        the requirements install gets the library, and this
        loads it afterwards — so the feature comes alive
        without restarting the app. Only the ones that were
        missing are tried. If one still cannot be loaded, it
        stays off and the next startup tries again.

        Ashley, 2026-11-27 (listening fix): this only ever
        retried creating self.voice when VOICE_CONTROL_AVAILABLE
        was False (the import itself had failed). When the
        import succeeded but the Vosk model was missing,
        VOICE_CONTROL_AVAILABLE was True, so it never retried
        — voice stayed None forever, even after the model
        appeared. Now it retries creating voice control
        whenever self.voice is None, whatever the import did
        (see _try_create_voice_control).
        """
        global VoiceControl, av, AudioPlayer, yt
        global VOICE_CONTROL_AVAILABLE, AV_AVAILABLE
        global AUDIO_PLAYER_AVAILABLE, YT_AVAILABLE
        try:
            if not VOICE_CONTROL_AVAILABLE:
                import voice_control as _vc
                VoiceControl = _vc.VoiceControl
                VOICE_CONTROL_AVAILABLE = True
            if getattr(self, "voice", None) is None:
                self._try_create_voice_control()
        except Exception:
            pass
        try:
            if not AV_AVAILABLE:
                import audiovault_client as _av
                av = _av
                AV_AVAILABLE = True
        except Exception:
            pass
        try:
            if not AUDIO_PLAYER_AVAILABLE:
                import audio_player as _ap
                AudioPlayer = _ap.AudioPlayer
                AUDIO_PLAYER_AVAILABLE = True
                if getattr(self, "player", None) is None:
                    try:
                        self.player = AudioPlayer()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            if not YT_AVAILABLE:
                import youtube_client as _yt
                yt = _yt
                YT_AVAILABLE = True
        except Exception:
            pass

    def _ensure_requirements(self, force=False):
        """Get every library the app needs, one at a time.

        Ashley, 2026-11-27: whatever requirements she needs
        for Command Prompt, the app should just get them and
        install them itself, so she never has to do it in
        Command Prompt. On startup (chained from
        _ensure_edge_tts, which runs first for the reading
        voice) and on the 1-minute retry, this checks every
        library in _REQUIRED_LIBRARIES and installs any that
        are missing, in the background, one at a time — never
        two pip installs at once. The reading voice itself is
        skipped here: it has its own install and retry, and
        this must never start a second install while that one
        runs. After each library, a module that was missing at
        startup is loaded (see _reload_missing_modules), so
        its feature comes alive without a restart. When a
        library fails, Samantha says the plain reason once
        (see _on_requirement_failed) and the app retries by
        itself in 1 minute. When everything required is
        ready, Samantha says so in the reading voice (see
        _on_requirements_ready). No NVDA and no Microsoft
        voice is ever used for any of this.
        """
        lock = getattr(self, "_requirements_lock", None)
        if lock is None:
            lock = threading.Lock()
            self._requirements_lock = lock
        with lock:
            if getattr(self, "_requirements_running", False):
                return
            if getattr(self, "_edge_install_running", False):
                return
            if getattr(self, "_vosk_model_running", False):
                return
            if not self._requirements_should_retry(force=force):
                return
            self._requirements_running = True
        installed_any = False
        try:
            self._requirements_last_try = time.time()
            self._requirements_announced_started = False
            missing = []
            for entry in _REQUIRED_LIBRARIES:
                import_name = entry[0]
                if import_name == "edge_tts":
                    continue
                if not self._library_available(import_name):
                    missing.append(entry)
            if not missing:
                self._reload_missing_modules()
                return
            try:
                wx.CallAfter(self._announce_requirements_started)
            except Exception:
                pass
            for import_name, pip_name, _spoken, required in missing:
                try:
                    self._requirements_state[import_name] = "installing"
                except Exception:
                    pass
                try:
                    ok, reason = self._install_one_library(
                        import_name, pip_name)
                except Exception as e:
                    ok, reason = False, "the install did not finish: " \
                        + str(e)[:100]
                if ok:
                    try:
                        self._requirements_state[import_name] = "ready"
                    except Exception:
                        pass
                    installed_any = True
                    try:
                        self.logger.log_playback(
                            "REQUIREMENTS",
                            "Installed " + pip_name)
                    except Exception:
                        pass
                    self._reload_missing_modules()
                else:
                    try:
                        self._requirements_state[import_name] = "failed"
                        counts = self._requirements_fail_count
                        counts[import_name] = counts.get(import_name, 0) + 1
                        self._requirements_last_reason[import_name] = reason
                    except Exception:
                        pass
                    try:
                        self.logger.log_error(
                            "REQUIREMENTS install failed: " + pip_name
                            + ": " + str(reason))
                    except Exception:
                        pass
                    try:
                        wx.CallAfter(self._on_requirement_failed,
                                     import_name, pip_name, reason, required)
                    except Exception:
                        pass
            if installed_any:
                self._reload_missing_modules()
            still_missing = [
                entry for entry in _REQUIRED_LIBRARIES
                if entry[3] and entry[0] != "edge_tts"
                and not self._library_available(entry[0])]
            if still_missing:
                try:
                    self._schedule_edge_install_retry()
                except Exception:
                    pass
            elif installed_any:
                try:
                    wx.CallAfter(self._on_requirements_ready)
                except Exception:
                    pass
        except Exception as e:
            try:
                self.logger.log_error(
                    "REQUIREMENTS error: " + str(e)[:200])
            except Exception:
                pass
            try:
                self._schedule_edge_install_retry()
            except Exception:
                pass
        finally:
            self._requirements_running = False
            # The libraries are dealt with (ready or failed):
            # now get the listening model itself, in the
            # background, one install at a time (see
            # _ensure_vosk_model). This is the chain that
            # makes listening work without Command Prompt:
            # reading voice -> libraries -> listening model.
            try:
                threading.Thread(target=self._ensure_vosk_model,
                                 daemon=True).start()
            except Exception:
                pass

    def _on_requirement_failed(self, import_name, pip_name, reason, required):
        """A library install failed (main thread).

        Samantha says the plain reason once for this failure,
        in her own voice — never NVDA, never Microsoft. When
        the reading voice itself is ready, she says the reason
        in that voice, so Ashley hears real words ("there is
        no internet connection right now", "the disk is full")
        instead of jargon. When the reading voice is not ready
        either, she says "not ready" once in her recorded
        voice, unless the reading voice already said it for
        its own failure — she never says it twice for the same
        failure. The app retries by itself in 1 minute either
        way (see _ensure_requirements), so she does not have
        to ask again or open Command Prompt.
        """
        if not required:
            return
        # Once per failure: the same library failing again in
        # the next pass has a higher fail count, so it is
        # announced again then — but this failure is said
        # only once, however many times it is asked about.
        try:
            key = (import_name,
                   self._requirements_fail_count.get(import_name, 0))
            said = self._requirements_failed_said
            if key in said:
                return
            said.add(key)
        except Exception:
            pass
        if self._samantha_voice_mode() == "edge":
            self._say_in_samantha_voice(
                "That did not work: " + str(reason)
                + ". I will try again by myself in a minute.")
            return
        if getattr(self, "_edge_install_state", None) == "failed" \
                and getattr(self, "_edge_install_not_ready_said", 0) \
                == getattr(self, "_edge_install_fail_count", 0) \
                and getattr(self, "_edge_install_fail_count", 0) > 0:
            return
        self._samantha_reading = True
        self._play_samantha_sequence(
            ["samantha_reading_not_ready.wav"],
            after=self._clear_samantha_reading)

    def _on_requirements_ready(self):
        """Everything the app needs is ready (main thread).

        Samantha says so in the reading voice itself, so
        Ashley knows the moment it is finished when she opens
        the program. Only announced once per run, and only
        when something was actually installed — if everything
        was already there, there is nothing new to announce,
        and the reading voice says so on its own when it
        becomes ready (see _on_edge_install_ready).
        """
        if getattr(self, "_requirements_ready_announced", False):
            return
        self._requirements_ready_announced = True
        if self._samantha_voice_mode() != "edge":
            return
        self._say_in_samantha_voice(
            "Everything is ready now. Ask me to list your shows.")

    def _on_install_requirements(self, event=None):
        """Menu / voice: get everything the app needs.

        Ashley, 2026-11-27: "install everything I need" — the
        checkable step for all of the app's requirements, not
        just the reading voice. Samantha says "I'm on it", the
        installs run in the background one at a time, and she
        says when it is all ready (see _on_requirements_ready);
        if something fails she says the plain reason once, and
        the app retries by itself in 1 minute. An explicit ask
        always forces a fresh pass right now, even if a pass
        just failed a moment ago. If everything is already
        ready, she just says so instead of installing again.
        No Command Prompt step is needed for any of this.
        """
        missing = [entry for entry in _REQUIRED_LIBRARIES
                   if not self._library_available(entry[0])]
        if not missing and getattr(self, "voice_available", False) \
                and self._vosk_model_present():
            self._say_in_samantha_voice(
                "Everything is ready now. Ask me to list your shows.")
            return
        self._requirements_last_try = 0.0
        try:
            self.status_label.SetLabel(
                "Getting everything Audio Vault TV needs ready...")
        except Exception:
            pass
        self._play_sound_effect("samantha_im_on_it.wav")
        threading.Thread(target=self._ensure_requirements, args=(True,),
                         daemon=True).start()

    def _play_dynamic_wav(self, path, words, _retry=0):
        """Play a synthesized reading file, then delete it.

        Ashley, 2026-11-26: readings talked over Samantha's
        clips, because this played on a fresh channel every
        time. Now it plays on Samantha's one dedicated channel,
        and waits until that channel is free — up to about 12
        seconds — instead of starting over a clip. Shows keep
        playing: they use the AudioPlayer music stream, not the clips.
        """
        try:
            from audio_player import clip_player
            if clip_player().busy():
                if _retry < 40:
                    wx.CallLater(300, self._play_dynamic_wav,
                                 path, words, _retry + 1)
                    return
            clip_player().play_file(path)
        except Exception:
            pass
        # Reading takes about 150 words a minute; clear the
        # flag and delete the file once it should be done.
        ms = int((words / 2.5 + 2) * 1000)
        wx.CallLater(ms, self._finish_dynamic_wav, path)

    def _finish_dynamic_wav(self, path):
        """Mark a dynamic reading done and delete its file."""
        self._samantha_reading = False
        try:
            os.unlink(path)
        except Exception:
            pass

    def _speak_and_requiet(self, speak_fn):
        """Run speak_fn, making sure Ashley actually hears it.

        Ashley, 2026-11-26: she wants Samantha herself to read
        the list, not NVDA — "I don't want NVDA to use the
        list. I want her to use the list." So NVDA quiet is
        NEVER turned off for a reading. speak_fn reads through
        Samantha's reading voice when it is available, and
        when it is not, Samantha says so herself in her own
        recorded voice (see _say_in_samantha_voice). NVDA
        says nothing at all, either way.
        """
        speak_fn()

    def _speak_show_list(self):
        """Read out all the shows Ashley has, so she can choose
        a channel.

        Ashley, 2026-11-26: "tell me the list of shows that
        I have so that I can choose a channel" / "What are
        my options?". Ashley, 2026-11-28: the shows are her
        channel names. Her library is named after episodes,
        not shows — "01 Ruby Reborn.mp3", "[S01.E01] Glen
        Godwin...mp3", "An Unearthly Child 01 An Unearthly
        Child.mp3" — so the old code (a show name from every
        file name) came out with 1,795 "shows" for her 20
        channels. A channel is a show: she makes one channel
        per show and calls them by those names, so the list
        is the channel names — the same names she hears in
        "list channels" — read in Samantha's reading voice
        (see _say_in_samantha_voice), not NVDA's. After the
        list, she can say the show she wants, for example
        "play Friends".
        """
        channels = self.channels.get_channel_list()
        if not channels:
            msg = "No shows available. Press Ctrl+T to create one."
        else:
            names = ", ".join(channels)
            msg = (f"Here are the shows you have: {names}. "
                   "Tell me which one you want to watch.")
        self.status_label.SetLabel(msg)
        self._say_in_samantha_voice(msg)

    def _speak_channels_and_guide(self):
        """After "I'm good": shows list, then what's next.

        Both readings go through Samantha's voice (see
        _say_in_samantha_voice), and NVDA quiet is never
        turned off for a reading — NVDA never reads the list.
        The guide waits until the list reading has actually
        finished (see _speak_tv_guide_when_free): the old code
        started the list and the guide in the same breath, so
        the guide intro talked over the list.
        """
        self._speak_show_list()
        wx.CallLater(500, self._speak_tv_guide_when_free)
        # Ashley, 2026-11-28: once the list and the guide have
        # been read, she picks the show she wants by saying it
        # (see _start_selection_listening) — it waits for both
        # readings to finish before the microphone opens.
        wx.CallLater(500, self._start_selection_listening)

    def _speak_tv_guide_when_free(self, _waited_ms=0):
        """Read the TV guide once Samantha has finished the list.

        _samantha_reading stays up while a reading (or the
        "not ready" clip) is playing. Wait for it, up to a
        minute, then read the guide anyway, so she is never
        left with no guide at all.
        """
        if getattr(self, "_samantha_reading", False) and _waited_ms < 60000:
            wx.CallLater(1000, self._speak_tv_guide_when_free,
                         _waited_ms + 1000)
            return
        self._speak_tv_guide()

    def _speak_tv_guide(self, event=None):
        """Read the whole TV guide out loud.

        Samantha says "Here's what's coming up next!" in her
        own recorded voice first, then the guide itself - the
        show names, which change every time - is read in
        Samantha's reading voice (see _say_in_samantha_voice),
        not NVDA's.
        """
        self._play_sound_effect("samantha_coming_up_next.wav")
        text = self._up_next_text()
        self.status_label.SetLabel(text)
        self._say_in_samantha_voice(text)

    def _on_tv_guide(self, event=None):
        """Menu / Ctrl+Shift+G: read the TV guide.

        Heard even with NVDA quiet on (see _speak_and_requiet).
        """
        self._speak_and_requiet(self._speak_tv_guide)

    # ---- Delete a channel and its downloads ----
    def _find_local_channel(self, query):
        """Find a local channel by name: exact, then starts-with,
        then contains. "killer among friends" matches
        "A Killer Among Friends", with "amongst" normalised to "among"."""
        if not query:
            return self.channels.current_channel
        q = str(query).strip().lower().replace("amongst", "among")
        # "delete the show" / "delete this show" / "delete it" -
        # the show playing right now.
        if q in ("the show", "this show", "show", "the channel",
                 "this channel", "channel", "it", "this", "that",
                 "this episode", "the episode"):
            return self.channels.current_channel
        if q.startswith("a "):
            q = q[2:]
        names = self.channels.get_channel_list()
        for name in names:
            if name.lower() == q or name.lower() == str(query).strip().lower():
                return name
        for name in names:
            if name.lower().startswith(q):
                return name
        for name in names:
            if q in name.lower():
                return name
        # Ashley, 2026-11-27: a slightly misheard name still
        # found nothing here ("doctor who" said a little
        # differently, a dropped word), so Samantha said she
        # does not have a show she does have — Classic Doctor
        # Who included. Fall back to the closest channel name
        # (same idea as the live-TV fuzzy match), instead of
        # giving up: exact words, word overlap, and letter
        # closeness, spaceless too.
        import difflib
        q_words = set(q.split())
        best = None
        best_score = 0.0
        for name in names:
            n = name.lower()
            n_words = set(n.split())
            score = difflib.SequenceMatcher(None, q, n).ratio()
            score = max(score, difflib.SequenceMatcher(
                None, q.replace(" ", ""), n.replace(" ", "")).ratio())
            if n_words <= q_words:
                score = max(score, 0.95)
            if q_words <= n_words:
                score = max(score, 0.9)
            if q_words and n_words:
                overlap = len(q_words & n_words) / len(q_words)
                if overlap >= 0.5:
                    score = max(score, 0.55 + 0.45 * overlap)
            if score > best_score:
                best, best_score = name, score
        if best is not None and best_score >= 0.6:
            return best
        return None

    def _on_delete_channel_downloads(self, event=None):
        self._delete_channel_downloads(None)

    def _delete_channel_downloads(self, query=None, confirm=True):
        """Delete a channel's downloaded files and remove the channel.

        Honey, 2026-11-23: "A Killer Among Friends" - the wrong
        Friends download - she does not like it and wants its
        downloads gone so it stops coming up. Only files listed in
        that channel's cached playlist, or files in its folders
        whose name matches the channel, are deleted - never a whole
        shared folder. The menu version asks Yes/No first, like
        Delete File does. The voice version does not: Honey said
        "whenever I tell it to delete the show, it deletes it",
        so a voice delete deletes right away and then speaks
        what was removed.
        """
        name = self._find_local_channel(query)
        if not name:
            msg = (f"I couldn't find a channel called {query}, so I didn't delete anything."
                   if query else "No channel is selected, so I didn't delete anything.")
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg, "samantha_reading_not_ready.wav")
            return
        data = self.channels.channels.get(name, {})
        folders = data.get("folders") or []
        cached = data.get("cached_playlist") or []
        files = []
        for _idx, fp in cached:
            try:
                files.append(Path(str(fp)))
            except Exception:
                pass
        if not files and folders:
            needle = name.lower().replace("a killer among friends", "killer among friends")
            for folder in folders:
                try:
                    for fp in Path(str(folder)).rglob("*"):
                        if fp.is_file() and needle in fp.name.lower():
                            files.append(fp)
                except Exception:
                    pass
        seen = set()
        uniq = []
        for f in files:
            if str(f) not in seen and f.exists():
                seen.add(str(f))
                uniq.append(f)
        files = uniq
        if confirm:
            result = wx.MessageBox(
                f"Delete {name} and all its downloaded files?\n\n"
                f"{len(files)} file(s) will be deleted from your computer, "
                f"and the channel will be removed so it stops coming up.",
                "Delete Channel and Downloads",
                wx.YES_NO | wx.ICON_WARNING)
            if result != wx.YES:
                msg = f"Okay, I left {name} alone."
                self.status_label.SetLabel(msg)
                self._answer_in_samantha_voice(msg)
                return
        try:
            self.player.stop()
            self.player.is_playing = False
        except Exception:
            pass
        deleted = 0
        for fp in files:
            try:
                fp.unlink()
                deleted += 1
            except Exception as e:
                self.logger.log_error(f"DELETE DOWNLOADS: {fp} - {e}")
        self.channels.delete_channel(name)
        self.playlist = PlaylistManager()
        self._load_current_channel()
        self._update_display()
        self._update_title()
        msg = f"Removed {name}. Deleted {deleted} downloaded file(s)."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
        self.logger.log_channel("DELETE-DOWNLOADS", name, f"deleted {deleted} file(s)")


    # ---- Live TV fallback: play Live TV when no local show is available ----
    def _livetv_pick_fallback_channel(self, channels):
        """Pick one live channel to play automatically, with no dialog.
        Favorites first, then a familiar category, then the first channel.
        """
        if not channels:
            return None
        try:
            fav_channels = livetv.get_favorite_channels()
            fav_ids = {c.get("id") for c in fav_channels}
        except Exception:
            fav_ids = set()
        for c in channels:
            if c.get("id") in fav_ids:
                return c
        for wanted in ("general", "entertainment", "news", "movies", "series",
                       "documentary", "music", "kids", "sports"):
            for c in channels:
                if wanted in (c.get("categories") or []):
                    return c
        return channels[0]

    def _livetv_fallback(self, reason="No shows are available"):
        """Start Live TV when no local show is available.
        Works with the external drive plugged in or not: Live TV streams
        over the internet, so it needs no local files and no drive.
        Returns True if a live stream is already playing or a fallback
        attempt has started, False if Live TV is not available at all.
        """
        if not LIVETV_AVAILABLE:
            msg = "Live TV is not available. No shows are available to play."
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
            self.logger.log_error(f"LIVETV-FALLBACK: {reason} but Live TV not available")
            return False
        if getattr(self, "livetv_process", None):
            return True
        if getattr(self, "_livetv_fallback_in_progress", False):
            return True
        self._livetv_fallback_in_progress = True
        msg = "No shows are available. Playing live TV instead. Live TV does not need your external drive."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
        self.logger.log_playback("LIVETV-FALLBACK", reason)
        threading.Thread(target=self._livetv_fallback_thread, daemon=True).start()
        return True

    def _livetv_fallback_thread(self):
        try:
            livetv.refresh_catalog()
            channels = livetv.get_all_channels()
            channel = self._livetv_pick_fallback_channel(channels)
            wx.CallAfter(self._livetv_fallback_done, channel, None)
        except Exception as e:
            wx.CallAfter(self._livetv_fallback_done, None, str(e))

    def _livetv_fallback_done(self, channel, error):
        self._livetv_fallback_in_progress = False
        self._advance_attempts = 0
        self.is_switching_channels = False
        if not channel:
            msg = "Live TV is not available right now. No shows are available to play."
            if error:
                self.logger.log_error(f"LIVETV-FALLBACK failed: {error}")
            self.status_label.SetLabel(msg)
            self._answer_in_samantha_voice(msg)
            return
        # _livetv_play speaks "Tuning in to ..." and starts the stream.
        self._livetv_play(channel)

    # ---- Live TV (iptv-org) ----

    def _on_livetv_browse(self, event=None):
        """Browse live channels by category."""
        self.status_label.SetLabel("Loading live channel list...")
        speak("Loading live channels")
        threading.Thread(target=self._livetv_load_categories_thread, daemon=True).start()

    def _livetv_load_categories_thread(self):
        try:
            livetv.refresh_catalog()
            categories = livetv.get_categories()
            wx.CallAfter(self._livetv_show_categories, categories)
        except Exception as e:
            wx.CallAfter(self._livetv_error, f"Could not load live channels: {e}")

    def _livetv_show_categories(self, categories):
        if not categories:
            self._livetv_error("No live channels available.")
            return
        items = [f"{cat} ({count})" for cat, count in categories.items()]
        dlg = wx.SingleChoiceDialog(self, "Choose a category:", "Live TV Categories", items)
        if dlg.ShowModal() == wx.ID_OK:
            idx = dlg.GetSelection()
            category = list(categories.keys())[idx]
            dlg.Destroy()
            channels = livetv.get_channels_by_category(category)
            self._livetv_show_channel_list(channels, f"Live TV - {category}")
        else:
            dlg.Destroy()

    def _on_livetv_search(self, event=None):
        """Search live channels by name."""
        dlg = wx.TextEntryDialog(self, "Search live channels:", "Search Live TV")
        if dlg.ShowModal() == wx.ID_OK:
            query = dlg.GetValue().strip()
            dlg.Destroy()
            if query:
                self.status_label.SetLabel(f"Searching live channels for {query}...")
                speak("Searching")
                threading.Thread(target=self._livetv_search_thread, args=(query,), daemon=True).start()
        else:
            dlg.Destroy()

    def _livetv_search_thread(self, query):
        try:
            livetv.refresh_catalog()
            results = livetv.search_channels(query)
            wx.CallAfter(self._livetv_show_channel_list, results, f"Live TV search: {query}")
        except Exception as e:
            wx.CallAfter(self._livetv_error, f"Search error: {e}")

    def _on_livetv_favorites(self, event=None):
        """Show favorite live channels."""
        self.status_label.SetLabel("Loading favorites...")
        threading.Thread(target=self._livetv_favorites_thread, daemon=True).start()

    def _livetv_favorites_thread(self):
        try:
            livetv.refresh_catalog()
            channels = livetv.get_favorite_channels()
            wx.CallAfter(self._livetv_show_channel_list, channels, "Live TV Favorites")
        except Exception as e:
            wx.CallAfter(self._livetv_error, f"Could not load favorites: {e}")

    def _livetv_show_channel_list(self, channels, title):
        if not channels:
            self._livetv_error("No channels found.")
            return

        favs = set(livetv.get_favorites())
        items = []
        for c in channels:
            star = "* " if c["id"] in favs else ""
            cats = ", ".join(c["categories"]) if c["categories"] else ""
            items.append(f"{star}{c['name']}" + (f" ({cats})" if cats else ""))

        speak(f"Found {len(items)} channels")
        dlg = wx.Dialog(self, title=title, size=(520, 420))
        panel = wx.Panel(dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(wx.StaticText(panel, label=f"Select a channel to play ({len(items)}):"), 0, wx.ALL, 6)
        listbox = wx.ListBox(panel, choices=items, style=wx.LB_SINGLE)
        if items:
            listbox.SetSelection(0)
        sizer.Add(listbox, 1, wx.ALL | wx.EXPAND, 6)

        row = wx.BoxSizer(wx.HORIZONTAL)
        play_btn = wx.Button(panel, wx.ID_OK, "Play")
        fav_btn = wx.Button(panel, label="Toggle Favorite")
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "Close")
        row.Add(play_btn, 0, wx.RIGHT, 6)
        row.Add(fav_btn, 0, wx.RIGHT, 6)
        row.Add(cancel_btn, 0)
        sizer.Add(row, 0, wx.ALL | wx.ALIGN_CENTER, 8)
        panel.SetSizer(sizer)
        listbox.SetFocus()

        def on_fav(evt):
            i = listbox.GetSelection()
            if i == wx.NOT_FOUND:
                return
            ch = channels[i]
            now_fav = livetv.toggle_favorite(ch["id"])
            speak(f"{ch['name']} {'added to' if now_fav else 'removed from'} favorites")
        fav_btn.Bind(wx.EVT_BUTTON, on_fav)

        if dlg.ShowModal() == wx.ID_OK:
            i = listbox.GetSelection()
            dlg.Destroy()
            if i != wx.NOT_FOUND:
                self._livetv_play(channels[i])
        else:
            dlg.Destroy()

    def _livetv_play(self, channel):
        """Start playing a live channel's audio."""
        # Stop any current MP3 playback and any existing live stream
        try:
            self.player.stop()
            self.player.is_playing = False
        except Exception:
            pass
        self._livetv_stop_stream()

        name = channel["name"]
        # Remember this as the active live channel so Space can resume it.
        self._livetv_last_channel = channel
        msg = f"Tuning in to {name}..."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
        self.logger.log_playback("LIVETV", f"Play: {name} ({channel['id']}) {channel['url']}")
        try:
            self.livetv_process = livetv.start_stream(channel["url"])
            self._update_title()
            self.SetTitle(f"AudioVault TV - LIVE: {name}")
            self.status_label.SetLabel(f"Live: {name} (Space to pause, Ctrl+Shift+X to stop)")
        except FileNotFoundError as e:
            self._livetv_error(str(e))
        except Exception as e:
            self._livetv_error(f"Could not start stream: {e}")

    def _on_livetv_stop(self, event=None):
        # Explicit stop (menu / Ctrl+Shift+X) fully exits live mode, so Space
        # afterward controls local playback again — not a live resume.
        self._livetv_stop_stream()
        self._livetv_last_channel = None
        msg = "Live TV stopped"
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)
        self._update_title()

    def _livetv_stop_stream(self):
        if self.livetv_process:
            livetv.stop_stream(self.livetv_process)
            self.livetv_process = None
            # Fold the ffplay diagnostics into the main debug log so buffering
            # info rides along with the normal "Upload Log" action.
            self._livetv_capture_stream_diagnostics()

    def _livetv_capture_stream_diagnostics(self):
        """Read the ffplay stream log and summarize buffering-relevant lines
        into the main logger."""
        try:
            path = getattr(livetv, "LIVETV_STREAM_LOG", None)
            if not path or not os.path.exists(path):
                return
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            keywords = ("reconnect", "buffer", "error", "timed out", "timeout",
                        "503", "403", "404", "refused", "reset", "nal", "drop",
                        "stall", "underrun", "retry", "failed", "url:", "started")
            interesting = [ln.strip() for ln in lines
                           if any(k in ln.lower() for k in keywords)]
            if interesting:
                sample = interesting[-40:]  # cap to avoid flooding the log
                self.logger.log_playback("LIVETV-DIAG",
                                         f"ffplay diagnostics ({len(interesting)} notable lines):")
                for ln in sample:
                    self.logger.log_playback("LIVETV-DIAG", ln)
            else:
                self.logger.log_playback("LIVETV-DIAG", "ffplay reported no buffering/error lines")
        except Exception as e:
            self.logger.log_error(f"LIVETV-DIAG capture failed: {e}")

    def _on_livetv_refresh(self, event=None):
        self.status_label.SetLabel("Refreshing live channel list...")
        speak("Refreshing channel list")
        threading.Thread(target=self._livetv_refresh_thread, daemon=True).start()

    def _livetv_refresh_thread(self):
        try:
            count = livetv.refresh_catalog(force=True)
            wx.CallAfter(self._livetv_refresh_done, count)
        except Exception as e:
            wx.CallAfter(self._livetv_error, f"Refresh failed: {e}")

    def _livetv_refresh_done(self, count):
        msg = f"Live channel list refreshed: {count} channels available."
        self.status_label.SetLabel(msg)
        self._answer_in_samantha_voice(msg)

    def _livetv_error(self, message):
        self.status_label.SetLabel(message)
        self._answer_in_samantha_voice(message, "samantha_reading_not_ready.wav")
        self.logger.log_error(f"LIVETV: {message}")

    def _on_quick_quit(self, event):
        """Quit immediately without outro sound"""
        try:
            self._save_current_channel_state()
        except Exception:
            pass
        
        if self.voice_available:
            if self.is_voice_listening or self.wake_word_mode:
                self.voice.stop_listening()
                self.wake_word_mode = False
        
        self.player.stop()
        self.timer.Stop()
        self._livetv_stop_stream()
        # Ashley, 2026-11-26: NVDA talks again when the app closes.
        self._disable_nvda_quiet()
        self.Destroy()

    def _on_close(self, event):
        """Handle window close"""
        try:
            self._save_current_channel_state()
        except Exception as e:
            print(f"Error saving channel state: {e}")
        
        # Stop voice control if running
        if self.voice_available:
            if self.is_voice_listening or self.wake_word_mode:
                self.voice.stop_listening()
                self.wake_word_mode = False
        
        self.player.stop()
        self.timer.Stop()
        self._livetv_stop_stream()

        # Ashley, 2026-11-26: NVDA talks again when the app closes.
        self._disable_nvda_quiet()

        # Play outro sound and wait for it to finish
        if self._play_outro_sound():
            # Check every 100ms if outro is still playing
            self._check_outro_finished()
        else:
            # No outro or failed to play, close immediately
            self.Destroy()
    
    def _play_outro_sound(self):
        """Play outro sound on exit if enabled"""
        if not self._sounds_enabled():
            return False
        outro_file = Path(__file__).parent / "sounds" / "outro.mp3"
        if outro_file.exists() and self.player is not None:
            try:
                self.player.load(str(outro_file))
                self.player.play()
                return True
            except Exception as e:
                print(f"Could not play outro sound: {e}")
                return False
        return False
    
    def _check_outro_finished(self):
        """Check if outro is still playing, close when done"""
        if self.player is not None and self.player.is_busy():
            # Still playing, check again in 100ms
            wx.CallLater(100, self._check_outro_finished)
        else:
            # Outro finished, close now
            self.Destroy()

def main():
    app = wx.App()
    frame = PlayerFrame()
    frame.Show()

    # Check for updates in background after window is visible
    def _background_update_check():
        try:
            from auto_updater import check_for_updates
            available = check_for_updates()
            if available:
                wx.CallAfter(_offer_updates, available)
        except Exception as e:
            print(f"Update check failed: {e}")

    def _offer_updates(available):
        result = wx.MessageBox(
            f"{len(available)} update(s) available:\n" + "\n".join(available) + "\n\nUpdate now?",
            "Updates Available",
            wx.YES_NO | wx.ICON_QUESTION
        )
        if result == wx.YES:
            from auto_updater import apply_updates
            updated = apply_updates(available)
            if "main.py" in updated:
                wx.MessageBox("Main program updated. Please restart the app.", "Update Complete", wx.OK)

    threading.Thread(target=_background_update_check, daemon=True).start()

    app.MainLoop()

if __name__ == "__main__":
    main()

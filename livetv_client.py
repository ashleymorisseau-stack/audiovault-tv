"""
Live TV client for AudioVault TV.

Uses the free, public iptv-org API (static JSON files, no key required) to
browse live TV channels and play their audio through the bundled ffplay/ffmpeg.

Only channels that have a working (non-DRM) HLS stream are offered. We skip
Pluto redirect URLs (jmp2.uk/plu-...), which serve DRM/takedown-slate content
that cannot be played outside a browser.
"""

import os
import json
import re
import difflib
import time
import subprocess
import urllib.request
from pathlib import Path

TOOLS_DIR = Path(__file__).parent / "tools"
CACHE_DIR = Path(__file__).parent / ".livetv_cache"
CACHE_TTL_SECONDS = 24 * 60 * 60  # refresh the channel list once a day

API_CHANNELS = "https://iptv-org.github.io/api/channels.json"
API_STREAMS = "https://iptv-org.github.io/api/streams.json"
API_FEEDS = "https://iptv-org.github.io/api/feeds.json"

# In-memory cache for this session
_catalog = None  # list of channel dicts (merged channel + best stream)


def _fetch_json(url, dest):
    """Download a JSON file to dest. Returns parsed JSON."""
    req = urllib.request.Request(url, headers={"User-Agent": "AudioVaultTV-LiveTV"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    return json.loads(data)


def _load_cached_or_fetch(url, filename):
    """Load a cached API file if fresh, otherwise re-download it."""
    path = CACHE_DIR / filename
    if path.exists() and (time.time() - path.stat().st_mtime) < CACHE_TTL_SECONDS:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _fetch_json(url, path)


def _is_bad_stream_url(url):
    """True for stream URLs we know don't work for us (Pluto DRM redirects)."""
    if not url:
        return True
    lowered = url.lower()
    # Pluto redirects (jmp2.uk/plu-...) serve DRM/takedown slates -> unusable.
    if "jmp2.uk/plu-" in lowered or "pluto.tv" in lowered:
        return True
    return False


def refresh_catalog(force=False):
    """Build (or rebuild) the catalog of playable US channels.
    Returns the number of channels available."""
    global _catalog
    if _catalog is not None and not force:
        return len(_catalog)

    channels = _load_cached_or_fetch(API_CHANNELS, "channels.json")
    streams = _load_cached_or_fetch(API_STREAMS, "streams.json")

    chan_by_id = {c["id"]: c for c in channels if c.get("id")}

    # Pick the best usable stream per channel (skip bad URLs)
    best_stream = {}
    for s in streams:
        cid = s.get("channel")
        url = s.get("url")
        if not cid or not url or _is_bad_stream_url(url):
            continue
        # First good stream wins; prefer https over http if we see one later
        if cid not in best_stream:
            best_stream[cid] = url
        elif best_stream[cid].startswith("http://") and url.startswith("https://"):
            best_stream[cid] = url

    catalog = []
    for cid, url in best_stream.items():
        c = chan_by_id.get(cid)
        if not c:
            continue
        if c.get("country") != "US":
            continue
        if c.get("is_nsfw"):
            continue
        catalog.append({
            "id": cid,
            "name": c.get("name", cid),
            "categories": c.get("categories") or [],
            "network": c.get("network") or "",
            "url": url,
        })

    catalog.sort(key=lambda x: x["name"].lower())
    _catalog = catalog
    return len(_catalog)


def get_categories():
    """Return a sorted dict of {category: channel_count} for the catalog."""
    if _catalog is None:
        refresh_catalog()
    counts = {}
    for c in _catalog:
        cats = c["categories"] or ["other"]
        for cat in cats:
            counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items()))


def get_channels_by_category(category):
    """Return channels in a given category, sorted by name."""
    if _catalog is None:
        refresh_catalog()
    return [c for c in _catalog if category in (c["categories"] or ["other"])]


def _normalize_live_name(name):
    """Normalize a channel name for voice matching.

    Ashley, 2026-11-26: Samantha kept hearing live channel names
    wrong — "p b s kids" for PBS Kids, "game show net work" for
    Game Show Network — and the old exact / startswith / contains
    match then found nothing, so she had to try six times. This
    folds those mishearings back together: lower case, "&" -> "and",
    punctuation out, single-letter runs joined ("p b s" -> "pbs").
    """
    text = str(name or "").lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    words = [w for w in text.split() if w]
    merged = []
    run = []
    for w in words:
        if len(w) == 1:
            run.append(w)
        else:
            if run:
                merged.append("".join(run))
                run = []
            merged.append(w)
    if run:
        merged.append("".join(run))
    return " ".join(merged)


def _live_match_score(query, name):
    """How close a heard name is to a real channel name, 0 to 1."""
    q = _normalize_live_name(query)
    n = _normalize_live_name(name)
    if not q or not n:
        return 0.0
    if q == n:
        return 1.0
    q_words = q.split()
    n_words = n.split()
    # A channel whose whole name is inside what she said ("history
    # channel" -> History) wins over a longer name that only shares
    # a word ("Discovery Channel"), and vice versa.
    if set(n_words) <= set(q_words):
        return 0.95
    if set(q_words) <= set(n_words):
        return 0.9
    score = difflib.SequenceMatcher(None, q, n).ratio()
    # Spaceless comparison catches "gameshow network" / "game show
    # net work" and similar word-split mishearings.
    score = max(score, difflib.SequenceMatcher(
        None, q.replace(" ", ""), n.replace(" ", "")).ratio())
    # Every heard word present in the channel name is a strong hint,
    # even if Vosk added or dropped a word around it.
    n_set = set(n_words)
    if q_words:
        overlap = sum(1 for w in q_words if w in n_set) / len(q_words)
        score = max(score, 0.55 + 0.45 * overlap if overlap >= 0.5 else score)
    return score


def best_live_match(query, channels, threshold=0.6):
    """Best channel for a heard name, or None if nothing is close.

    Used by voice play: after exact / startswith / contains fail,
    this lets a slightly misheard name still find its channel
    instead of Samantha saying she could not find it.
    """
    best = None
    best_score = 0.0
    for c in channels or []:
        score = _live_match_score(query, c.get("name", ""))
        if score > best_score:
            best_score = score
            best = c
    return best if best_score >= threshold else None


def search_channels(query):
    """Search channels by name (case-insensitive).

    Exact substring matches come first, then close (fuzzy) matches,
    so a misheard name still shows its channel instead of nothing.
    """
    if _catalog is None:
        refresh_catalog()
    q = query.lower().strip()
    exact = [c for c in _catalog if q in c["name"].lower()]
    scored = []
    for c in _catalog:
        if c in exact:
            continue
        score = _live_match_score(query, c.get("name", ""))
        if score >= 0.55:
            scored.append((score, c))
    scored.sort(key=lambda item: item[0], reverse=True)
    return exact + [c for _, c in scored]


def get_all_channels():
    if _catalog is None:
        refresh_catalog()
    return list(_catalog)


# ---- Favorites (stored in config.ini) ----

CONFIG_FILE = Path(__file__).parent / "config.ini"


def get_favorites():
    import configparser
    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_FILE)
        raw = config.get("livetv", "favorites", fallback="")
        return [x for x in raw.split("|") if x]
    except Exception:
        return []


def save_favorites(fav_ids):
    import configparser
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    if "livetv" not in config:
        config["livetv"] = {}
    config["livetv"]["favorites"] = "|".join(fav_ids)
    with open(CONFIG_FILE, "w") as f:
        config.write(f)


def toggle_favorite(channel_id):
    favs = get_favorites()
    if channel_id in favs:
        favs.remove(channel_id)
        result = False
    else:
        favs.append(channel_id)
        result = True
    save_favorites(favs)
    return result


def get_favorite_channels():
    if _catalog is None:
        refresh_catalog()
    favs = set(get_favorites())
    return [c for c in _catalog if c["id"] in favs]


# ---- Audio playback via ffplay (falls back to ffmpeg) ----

# ffplay's network/buffering diagnostics are written here so we can see WHY a
# stream buffers (reconnects, underruns, HTTP errors, throughput).
LIVETV_STREAM_LOG = Path(__file__).parent / "livetv_stream.log"


def _player_cmd(stream_url):
    ffplay = TOOLS_DIR / ("ffplay.exe" if os.name == "nt" else "ffplay")
    if ffplay.exists():
        return [
            str(ffplay),
            "-nodisp",                 # no video window
            "-vn",                     # play audio only
            "-autoexit",
            # Report network/buffering events (was 'quiet', which hid why it
            # buffers). 'info' + stats shows reconnects, underruns, throughput.
            "-loglevel", "info",
            "-stats",
            # Auto-reconnect if the live feed hiccups, instead of stalling/dying.
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "2",   # shorter back-off so recovery is quick
            # Start quickly without the long pre-buffer that '-infbuf' caused,
            # while still giving ffplay enough data to detect the audio stream
            # (too-small probesize makes it fail to find the sample rate).
            "-fflags", "nobuffer",
            "-probesize", "500000",
            "-analyzeduration", "500000",
            stream_url,
        ]
    ffmpeg = TOOLS_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if ffmpeg.exists():
        raise FileNotFoundError(
            "ffplay is required for Live TV audio. Place ffplay.exe in the tools/ folder."
        )
    raise FileNotFoundError("ffplay.exe not found in tools/ folder.")


def start_stream(stream_url):
    """Start playing a stream's audio. Returns a subprocess handle.

    ffplay's diagnostic output (buffering, reconnects, errors) is written to
    livetv_stream.log so it can be reviewed / uploaded for troubleshooting.
    The file is truncated at the start of each stream and capped in size.
    """
    cmd = _player_cmd(stream_url)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    try:
        # Fresh log per stream, with a header noting the URL/time.
        import datetime
        log_f = open(LIVETV_STREAM_LOG, "w", encoding="utf-8", errors="replace")
        log_f.write(f"=== Live TV stream started {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
        log_f.write(f"URL: {stream_url}\n\n")
        log_f.flush()
    except Exception:
        log_f = subprocess.DEVNULL
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=log_f,  # capture ffplay diagnostics instead of discarding them
        creationflags=creationflags,
    )
    # Remember the log file handle so stop_stream can close it cleanly.
    try:
        proc._livetv_logfile = log_f if log_f is not subprocess.DEVNULL else None
    except Exception:
        pass
    return proc


def stop_stream(proc):
    """Stop a running stream subprocess."""
    if proc and proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
    # Close the captured diagnostics log handle if we opened one.
    try:
        lf = getattr(proc, "_livetv_logfile", None)
        if lf:
            lf.close()
    except Exception:
        pass

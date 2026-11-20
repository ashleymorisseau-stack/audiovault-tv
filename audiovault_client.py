"""
AudioVault client module - refactored from audiovault-downloader CLI tool
by Carter Temm (https://github.com/cartertemm/audiovault-downloader)
Adapted for GUI integration.
"""

import io
import os
import time
import configparser
from urllib.parse import urljoin
from pathlib import Path
from email.message import Message

import bs4
import requests


BASE_URL = "https://audiovault.net"
DEFAULT_DOWNLOAD_DIR = Path(__file__).parent / "Downloads"

try:
    import cloudscraper
    session = cloudscraper.create_scraper()
except ImportError:
    session = requests.session()

session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
})


def bytes2human(n):
    symbols = ('KB', 'MB', 'GB', 'TB')
    prefix = {}
    for i, s in enumerate(symbols):
        prefix[s] = 1 << (i + 1) * 10
    for s in reversed(symbols):
        if n >= prefix[s]:
            return '%.1f%s' % (float(n) / prefix[s], s)
    return "%sB" % n


def get_filename_from_header(header):
    msg = Message()
    msg["content-disposition"] = header
    return msg.get_filename()


def sanitize_filename(name):
    """Remove characters that are illegal in Windows filenames.
    Windows forbids: < > : " / \\ | ? *  and control characters.
    A colon (e.g. in 'Law and Order Toronto: Criminal Intent') otherwise
    causes [Errno 22] Invalid argument when saving."""
    if not name:
        return name
    illegal = '<>:"/\\|?*'
    for ch in illegal:
        name = name.replace(ch, "-")
    # Collapse any run of spaces/dashes created by the replacement
    name = name.strip().rstrip(". ")  # Windows also dislikes trailing dot/space
    return name


def login(email, password, log_file=None):
    """Login to AudioVault. Returns True on success."""
    def _log(msg):
        if log_file:
            try:
                with open(log_file, 'a') as f:
                    f.write(f"VAULT: {msg}\n")
            except Exception:
                pass
    
    try:
        _log(f"Fetching login page from {BASE_URL}")
        r = session.get(urljoin(BASE_URL, "login"))
        _log(f"Login page status: {r.status_code}")
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, features="html.parser")
        token = soup.find("input", {"type": "hidden", "name": "_token"})
        if not token:
            _log("ERROR: Could not find CSRF token on login page")
            return False
        token = token.get("value")
        _log("Got CSRF token, submitting login")
        r = session.post(urljoin(BASE_URL, "login"), {
            "_token": token,
            "email": email,
            "password": password,
        })
        _log(f"Login POST status: {r.status_code}, response starts with: {r.text[:100]}")
        result = not r.text.startswith('<form method="POST" action=')
        _log(f"Login result: {'success' if result else 'failed'}")
        return result
    except Exception as e:
        _log(f"Login exception: {e}")
        raise


def save_credentials(email, password, config_path="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_path)
    if "login" not in config:
        config["login"] = {}
    config["login"]["email"] = email
    config["login"]["password"] = password
    with open(config_path, "w") as f:
        config.write(f)


def load_credentials(config_path="config.ini"):
    """Returns (email, password) or (None, None)."""
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
        return config["login"]["email"], config["login"]["password"]
    except (KeyError, FileNotFoundError):
        return None, None


def save_download_dir(directory, kind=None, config_path="config.ini"):
    config = configparser.ConfigParser()
    config.read(config_path)
    if "settings" not in config:
        config["settings"] = {}
    if kind:
        config["settings"][f"download_dir_{kind}"] = str(directory)
    else:
        config["settings"]["download_dir"] = str(directory)
    with open(config_path, "w") as f:
        config.write(f)


def load_download_dir(kind=None, config_path="config.ini"):
    """Returns saved download dir for kind (movies/shows) or default."""
    config = configparser.ConfigParser()
    try:
        config.read(config_path)
        if kind and f"download_dir_{kind}" in config["settings"]:
            return config["settings"][f"download_dir_{kind}"]
        return config["settings"]["download_dir"]
    except (KeyError, FileNotFoundError):
        return str(DEFAULT_DOWNLOAD_DIR)


def search(query, kind="movies"):
    """Search for movies or shows. Returns list of [id, name, download_url]."""
    r = session.get(urljoin(BASE_URL, kind), params={"search": query})
    r.raise_for_status()
    return _parse_pages(r.text)


def get_recents(kind="movies"):
    """Get recently added content. Returns list of [id, name, download_url]."""
    r = session.get(BASE_URL)
    r.raise_for_status()
    soup = bs4.BeautifulSoup(r.text, features="html.parser")
    for tag in soup.find_all("h5"):
        text = str(tag.text.strip())
        if text.startswith("Recent") and kind.capitalize() in text:
            table = tag.find_next("tbody")
            return _parse_page(table)
    return []


def download(url, destination=None, progress_callback=None):
    """Download a file. progress_callback(percent, total_size, filename) is called during download.
    Returns the final file path on success, None on failure."""
    r = session.get(url, stream=True)

    # Check for session timeout
    if r.status_code == 302 or r.headers.get("Content-Type", "").startswith("text/html"):
        return None

    total_size = int(r.headers.get("Content-Length", 0))
    if total_size == 0:
        return None

    filename = get_filename_from_header(r.headers.get("content-disposition", ""))
    if not filename:
        return None
    # Strip characters Windows won't allow in a filename (e.g. the ':' in
    # "Law and Order Toronto: Criminal Intent") to avoid Errno 22.
    filename = sanitize_filename(filename)

    if not destination:
        destination = str(DEFAULT_DOWNLOAD_DIR)

    os.makedirs(destination, exist_ok=True)

    if os.path.isdir(destination):
        filepath = os.path.join(destination, filename)
    else:
        filepath = destination

    # Log the exact path we're about to write so we can diagnose Errno 22
    try:
        import logging
        logging.getLogger('MP3Player').info(f"VAULT: Writing download to: {filepath!r}")
    except Exception:
        pass

    so_far = 0
    # Use a modest fixed chunk size. Very large buffers to flaky USB/external
    # drives can trigger "[Errno 22] Invalid argument" on write; smaller chunks
    # with periodic flushing are far more reliable.
    chunk_size = 256 * 1024  # 256 KB
    bytes_since_flush = 0
    flush_interval = 4 * 1024 * 1024  # flush to disk every ~4 MB

    def _write_with_retry(f, data, attempts=5):
        """Write a chunk, retrying briefly on transient OS write errors that
        happen when an external drive hiccups mid-transfer."""
        for attempt in range(attempts):
            try:
                f.write(data)
                return
            except OSError as err:
                # Errno 22 and friends can be transient on USB drives.
                if attempt == attempts - 1:
                    raise
                time.sleep(0.5 * (attempt + 1))

    with open(filepath, "wb", buffering=0) as f:
        for chunk in r.iter_content(chunk_size):
            if not chunk:
                continue
            _write_with_retry(f, chunk)
            so_far += len(chunk)
            bytes_since_flush += len(chunk)
            # Periodically flush and fsync so data lands on the drive steadily
            # instead of building up in a cache that can fail all at once.
            if bytes_since_flush >= flush_interval:
                try:
                    f.flush()
                    os.fsync(f.fileno())
                except OSError:
                    pass
                bytes_since_flush = 0
            percent = round((so_far / total_size) * 100, 2)
            if progress_callback:
                progress_callback(percent, total_size, filename)

    return filepath


def _parse_pages(text):
    soup = bs4.BeautifulSoup(text, features="html.parser")
    next_link = soup.find("a", rel="next")
    if not next_link:
        table = soup.find("tbody")
        return _parse_page(table) if table else []

    last = next_link.findPrevious("a", {"class": "page-link"})
    last_url = last.get("href")
    last_page = int(last_url[last_url.rfind("=") + 1:])

    results = []
    for i in range(1, last_page + 1):
        page_url = last_url[:last_url.rfind("=") + 1] + str(i)
        r = session.get(page_url)
        r.raise_for_status()
        soup = bs4.BeautifulSoup(r.text, features="html.parser")
        table = soup.find("tbody")
        if table:
            results += _parse_page(table)
    return results


def _parse_page(table):
    results = []
    for row in table.find_all("tr"):
        id_cell = row.find_next("td")
        name_cell = id_cell.find_next("td")
        link = name_cell.find_next("td").find("a").get("href")
        av_id = id_cell.text.strip() if id_cell else ""
        name = name_cell.text.strip() if name_cell else ""
        results.append([av_id, name, link])
    return results

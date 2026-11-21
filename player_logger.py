import base64
import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from datetime import datetime

# Log uploads go to GitHub now, not S3. The log file lands in the repo at
# logs/<username>_log.txt. Writing to GitHub needs a token, saved in
# github_token.txt next to the program (a fine-grained token for this
# repo with Contents read and write). The token file is never pushed.
GITHUB_API = "https://api.github.com"
GITHUB_REPO = "ashleymorisseau-stack/audiovault-tv"
GITHUB_BRANCH = "master"
TOKEN_FILE = "github_token.txt"


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
        """Upload the log file to GitHub (logs/<username>_log.txt).

        The same information as the old S3 upload: the whole player_log.txt
        (playback, navigation, channels, voice, errors, live TV
        diagnostics). Raises an exception with a plain-words reason on
        failure.
        """
        if not self.log_file.exists():
            raise FileNotFoundError(f"Log file not found: {self.log_file}")
        token_path = Path(__file__).parent / TOKEN_FILE
        if not token_path.exists():
            raise FileNotFoundError(
                "No GitHub token saved. Save a token in github_token.txt "
                "next to the program first."
            )
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise ValueError("github_token.txt is empty.")
        log_path = f"logs/{self.username}_log.txt"
        content = base64.b64encode(self.log_file.read_bytes()).decode("ascii")
        # If the log is already on GitHub, its fingerprint (sha) is needed
        # to replace it; otherwise this creates it.
        sha = self._github_log_sha(log_path, token)
        body = {
            "message": f"Update {self.username} log",
            "content": content,
            "branch": GITHUB_BRANCH,
        }
        if sha:
            body["sha"] = sha
        status, _payload = self._github_request(
            "PUT", f"/repos/{GITHUB_REPO}/contents/{log_path}", token, body
        )
        if status not in (200, 201):
            raise Exception(f"GitHub returned status {status}")

    def _github_log_sha(self, log_path, token):
        """Fingerprint (sha) of the log file already on GitHub, or None."""
        status, payload = self._github_request(
            "GET", f"/repos/{GITHUB_REPO}/contents/{log_path}", token,
            allow_404=True,
        )
        if status == 404:
            return None
        return payload.get("sha")

    def _github_request(self, method, path, token, body=None, allow_404=False):
        """One authenticated GitHub API call. Returns (status, payload)."""
        url = GITHUB_API + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("User-Agent", "AudioVaultTV-LogUpload")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404 and allow_404:
                return 404, None
            try:
                detail = json.loads(e.read().decode("utf-8", "replace"))
                message = detail.get("message", "")
            except Exception:
                message = ""
            if e.code == 401:
                raise Exception(
                    "GitHub said the token is not valid. Check github_token.txt."
                )
            if e.code == 403:
                raise Exception(
                    "GitHub refused the upload. The token needs Contents "
                    "read and write access to this repo."
                )
            raise Exception(f"GitHub returned {e.code}: {message}".strip())
        except urllib.error.URLError as e:
            raise Exception(f"Could not reach GitHub: {e.reason}")

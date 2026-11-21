"""Audio Vault TV Sync -- push and pull tool for Audio Vault TV.

Replaces Push-AudioVault-Update.bat and Pull-AudioVault-Update.bat.

Double-click run_audiovault_sync.bat to open it, then pick Push or Pull.
Built for NVDA:

* Two big buttons, Push and Pull, plus a Close button. Nothing to type.
* A progress bar that moves as each step finishes. NVDA gives progress
  beeps for it, so you can hear how far along it is.
* Every step is written in the "What happened" log, which you can review
  with NVDA any time.
* It beeps and speaks out loud at every step, calling you Honey, just
  like the old batch scripts did. Two high happy beeps mean it worked.
  One low beep means it did not, and it says in plain words why.
* Push pulls from GitHub first, so it is never rejected for being behind.
  If the first push fails, it pulls again and tries once more by itself.
* pull_result.txt is never pushed to GitHub. It stays only on this PC.
* If the pull works, it writes a little note called pull_result.txt
  saying what changed, so you can open it with NVDA any time.

Needs Python and wxPython (already in requirements.txt).
Runs from inside the audiovault-tv folder.
"""

import os
import subprocess
import sys
import threading
from datetime import datetime

import wx

APP_TITLE = "Audio Vault TV Sync"
NAME = "Honey"
REPO_FOLDER = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# Sound and speech (never allowed to break the sync)
# ---------------------------------------------------------------------------

def speak(text):
    """Say text out loud with the Windows voice.

    Uses the same System.Speech call the old batch scripts used.
    If speech is not available, the words are still on screen and the
    beeps still play, so the sync goes on.
    """
    try:
        ps = (
            "try { Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "$s.Speak($env:SYNC_SPEAK_MSG); } catch { }"
        )
        env = dict(os.environ)
        env["SYNC_SPEAK_MSG"] = text
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            env=env, capture_output=True, timeout=60,
        )
    except Exception:
        pass


def beep(freq, ms):
    """Play one beep at the given frequency (Hz) for ms milliseconds."""
    try:
        import winsound
        winsound.Beep(freq, ms)
    except Exception:
        try:
            wx.CallAfter(wx.Bell)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run_git(args, folder=None):
    """Run one git command in the repo folder.

    Returns (return_code, combined_output). return_code is None when git
    itself could not be run at all.
    """
    if folder is None:
        folder = REPO_FOLDER
    try:
        result = subprocess.run(
            ["git"] + args, cwd=folder,
            capture_output=True, text=True, errors="replace", timeout=180,
        )
        return result.returncode, (result.stdout or "") + (result.stderr or "")
    except FileNotFoundError:
        return None, "Git is not installed on this PC."
    except Exception as exc:
        return None, "Could not run git: %s" % exc


def explain_failure(output):
    """Turn git's error text into one plain sentence, like the old scripts."""
    low = (output or "").lower()
    if "rejected" in low or "non-fast-forward" in low:
        return ("GitHub has newer changes than this PC. "
                "Please run Pull first, then run Push again.")
    if ("authentication failed" in low or "could not read username" in low
            or "403" in low or "401" in low):
        return ("GitHub did not accept the sign-in on this PC. "
                "Please check the sign-in or token, then try again.")
    if ("could not resolve host" in low or "failed to connect" in low
            or "network is unreachable" in low or "connection timed out" in low
            or "unable to access" in low):
        return ("There is no internet connection to GitHub right now. "
                "Please check the internet, then try again.")
    if "conflict" in low:
        return ("Your changes conflict with GitHub. "
                "Please ask Muse for help before pushing again.")
    return ("It did not finish. Please try running it again, "
            "and tell Muse what GitHub said.")


def fail(report, reason, output):
    """Report a failed step: plain words, the raw output, a low beep."""
    report(100, "It did not finish, %s.\nIn plain words: %s" % (NAME, reason))
    if output and output.strip():
        report(100, "Here is what GitHub said:\n" + output.strip())
    beep(220, 500)
    speak("It did not finish, %s. %s" % (NAME, reason))


def list_files(report):
    """List the files in this folder, so NVDA can read them."""
    try:
        files = sorted(os.listdir(REPO_FOLDER))
    except Exception:
        return
    report(10, "Files in this folder right now:\n" + "\n".join(files))


# ---------------------------------------------------------------------------
# Push and pull
# ---------------------------------------------------------------------------

def do_push(report):
    """Push this PC's changes to GitHub. Mirrors the old push script."""
    report(5, "Starting the push, %s." % NAME)
    speak("Starting the push, %s." % NAME)
    beep(660, 200)
    list_files(report)
    report(15, "Pulling the latest changes from GitHub first, "
               "so the push is not rejected...")
    speak("Pulling the latest changes from GitHub first, %s." % NAME)
    beep(770, 150)
    code, out = run_git(["pull", "--no-edit"])
    if out.strip():
        report(25, out.strip())
    if code != 0:
        fail(report, explain_failure(out), out)
        return

    report(35, "Adding every new and changed file, %s..." % NAME)
    speak("Adding your files now, %s." % NAME)
    beep(770, 150)
    run_git(["add", "-A"])
    run_git(["add", "*.py", "*.bat", "*.md", "*.txt"])
    # pull_result.txt stays only on this PC, never goes to GitHub.
    run_git(["reset", "-q", "pull_result.txt"])
    report(50, "Halfway done, %s. Your files are added and ready to send." % NAME)
    speak("Halfway done, %s. Your files are added and ready to send." % NAME)
    beep(880, 150)

    code, out = run_git(["diff", "--cached", "--name-only"])
    files = [line for line in (out or "").splitlines() if line.strip()]
    if files:
        report(55, "Files ready to send:\n" + "\n".join(files))
    code, out = run_git(["status", "--short"])
    if out.strip():
        report(58, out.strip())

    # git diff --cached --quiet returns 0 when there is nothing staged.
    code, _out = run_git(["diff", "--cached", "--quiet"])
    if code == 0:
        report(100, "Nothing new to push, %s. "
                    "Everything is already on GitHub." % NAME)
        speak("Nothing new to push, %s. Everything is already on GitHub." % NAME)
        beep(660, 250)
        return

    report(65, "There are changes to send. Committing them now, %s..." % NAME)
    speak("Committing your changes now, %s." % NAME)
    beep(770, 150)
    message = ("Update from PC on %s - Audio Vault TV"
               % datetime.now().strftime("%Y-%m-%d %H:%M"))
    code, out = run_git(["commit", "-m", message])
    if out.strip():
        report(75, out.strip())
    if code != 0:
        fail(report, explain_failure(out), out)
        return

    report(85, "Pushing to GitHub now, %s..." % NAME)
    speak("Pushing to GitHub now, %s." % NAME)
    beep(990, 150)
    code, out = run_git(["push"])
    if out.strip():
        report(90, out.strip())
    if code != 0:
        report(88, "The first push did not go through, %s. "
                    "Pulling again and trying once more..." % NAME)
        speak("The first push did not go through, %s. "
              "Pulling again and trying once more." % NAME)
        beep(990, 150)
        code, out = run_git(["pull", "--no-edit"])
        if out.strip():
            report(90, out.strip())
        if code != 0:
            fail(report, explain_failure(out), out)
            return
        code, out = run_git(["push"])
        if out.strip():
            report(92, out.strip())
        if code != 0:
            fail(report, explain_failure(out), out)
            return

    report(97, "Almost done, %s." % NAME)
    speak("Almost done, %s." % NAME)
    beep(990, 150)
    beep(880, 250)
    beep(1320, 400)
    report(100, "Push successful, %s, it's on GitHub.\n"
                "Your changes are now on GitHub for Muse to read." % NAME)
    speak("Push successful, %s, it's on GitHub." % NAME)


def do_pull(report):
    """Pull the latest changes from GitHub. Mirrors the old pull script."""
    report(5, "Starting the pull now, %s." % NAME)
    speak("Starting the pull, %s." % NAME)
    beep(660, 200)
    report(20, "Pulling the latest Audio Vault TV changes from GitHub...")
    speak("Pulling from GitHub now, %s." % NAME)
    beep(770, 150)
    code, out = run_git(["pull", "--no-edit"])
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    note_path = os.path.join(REPO_FOLDER, "pull_result.txt")

    if code != 0:
        reason = explain_failure(out)
        try:
            with open(note_path, "w", encoding="utf-8") as note:
                note.write("Pull did not finish, %s.\n\nDate and time: %s\n\n%s\n"
                           % (NAME, now, reason))
        except Exception:
            pass
        report(100, "The pull did not finish, %s.\nIn plain words: %s"
                    % (NAME, reason))
        if out.strip():
            report(100, "Here is what GitHub said:\n" + out.strip())
        report(100, "I wrote a little note for you in this folder called "
                    "pull_result.txt.\nIt says the pull did not finish, %s, "
                    "and why." % NAME)
        beep(220, 500)
        speak("Pull did not finish, %s. %s" % (NAME, reason))
        return

    if out.strip():
        report(40, out.strip())
    up_to_date = "already up to date" in (out or "").lower()
    report(60, "Halfway done, %s. The pull finished. "
               "Now I am writing your note." % NAME)
    speak("Halfway done, %s. The pull finished. Now I am writing your note."
          % NAME)
    beep(770, 150)
    report(80, "Almost done, %s." % NAME)
    speak("Almost done, %s." % NAME)
    beep(990, 150)
    beep(880, 250)
    beep(1320, 400)
    if up_to_date:
        text = ("Pull successful, %s! It's done.\n"
                "Everything was already up to date. Nothing new came down."
                % NAME)
        note = ("Pull successful, %s! It's done.\n\nDate and time: %s\n\n"
                "Everything was already up to date. Nothing new came down.\n"
                % (NAME, now))
        spoken = "Pull successful, %s! It's done. Everything was already up to date." % NAME
    else:
        text = ("Pull successful, %s! It's done.\n"
                "New changes came down from GitHub." % NAME)
        note = ("Pull successful, %s! It's done.\n\nDate and time: %s\n\n"
                "New changes came down from GitHub. Here is what changed:\n\n%s\n"
                % (NAME, now, out.strip()))
        spoken = "Pull successful, %s! It's done. New changes came down from GitHub." % NAME
    try:
        with open(note_path, "w", encoding="utf-8") as note_file:
            note_file.write(note)
    except Exception:
        pass
    report(100, text + "\nI wrote a little note for you in this folder called "
                      "pull_result.txt.")
    speak(spoken)
    list_files(report)


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

class SyncFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=APP_TITLE, size=(620, 500))
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        intro = wx.StaticText(
            panel,
            label="Audio Vault TV Sync, %s. Choose push or pull, "
                  "then listen for the beeps." % NAME)
        intro.Wrap(580)
        sizer.Add(intro, 0, wx.ALL, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.push_btn = wx.Button(panel, label="Push my changes to GitHub")
        self.pull_btn = wx.Button(panel, label="Pull the latest from GitHub")
        btn_sizer.Add(self.push_btn, 1, wx.ALL, 5)
        btn_sizer.Add(self.pull_btn, 1, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)

        self.gauge_label = wx.StaticText(panel, label="Progress: 0 percent")
        sizer.Add(self.gauge_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.gauge = wx.Gauge(panel, range=100, size=(-1, 25))
        self.gauge.SetName("Progress")
        sizer.Add(self.gauge, 0, wx.EXPAND | wx.ALL, 10)

        log_label = wx.StaticText(panel, label="What happened:")
        sizer.Add(log_label, 0, wx.LEFT | wx.RIGHT, 10)
        self.log = wx.TextCtrl(
            panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP)
        sizer.Add(self.log, 1, wx.EXPAND | wx.ALL, 10)

        self.close_btn = wx.Button(panel, label="Close")
        sizer.Add(self.close_btn, 0, wx.ALIGN_RIGHT | wx.ALL, 10)

        panel.SetSizer(sizer)
        self.push_btn.Bind(wx.EVT_BUTTON, lambda _e: self.start_work(do_push))
        self.pull_btn.Bind(wx.EVT_BUTTON, lambda _e: self.start_work(do_pull))
        self.close_btn.Bind(wx.EVT_BUTTON, lambda _e: self.Close())
        self.push_btn.SetFocus()
        self.busy = False
        self.check_git_folder()
        self.Centre()

    def check_git_folder(self):
        """Warn in plain words if this folder is not a Git copy."""
        code, _out = run_git(["rev-parse", "--git-dir"])
        if code != 0:
            msg = ("This folder is not a Git copy of Audio Vault TV, %s. "
                   "Please clone the repo first, then open this program "
                   "from inside that folder." % NAME)
            self.append_log(msg)
            speak(msg)
            self.push_btn.Disable()
            self.pull_btn.Disable()

    def start_work(self, worker):
        if self.busy:
            return
        self.busy = True
        self.push_btn.Disable()
        self.pull_btn.Disable()
        self.gauge.SetValue(0)
        self.gauge_label.SetLabel("Progress: 0 percent")
        self.log.Clear()
        thread = threading.Thread(
            target=self.run_worker, args=(worker,), daemon=True)
        thread.start()

    def run_worker(self, worker):
        try:
            worker(self.report)
        except Exception as exc:
            wx.CallAfter(self.append_log,
                         "Something went wrong, %s: %s" % (NAME, exc))
            beep(220, 500)
        finally:
            wx.CallAfter(self.work_done)

    def work_done(self):
        self.busy = False
        self.push_btn.Enable()
        self.pull_btn.Enable()
        self.push_btn.SetFocus()

    def report(self, percent, message):
        """Called from the worker thread; hands the update to the GUI."""
        wx.CallAfter(self.update_progress, percent, message)

    def update_progress(self, percent, message):
        percent = max(0, min(100, int(percent)))
        self.gauge.SetValue(percent)
        self.gauge_label.SetLabel("Progress: %d percent" % percent)
        self.append_log(message)

    def append_log(self, message):
        self.log.AppendText(message.strip() + "\n")


def main():
    os.chdir(REPO_FOLDER)
    app = wx.App(False)
    frame = SyncFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()

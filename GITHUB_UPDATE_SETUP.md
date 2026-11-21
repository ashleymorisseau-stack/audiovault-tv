# AudioVault TV Updates — Now From GitHub

AudioVault TV used to get its updates from an Amazon S3 bucket. It does not
any more. Updates now come from the public GitHub repo
**ashleymorisseau-stack/audiovault-tv**, branch **master**. There is no S3
bucket to pay for, no AWS login, and no upload script to run.

## For the developer (Joshua / Ashley) — when you change something

1. Change the code on your computer, as usual.
2. Push it to GitHub with the **AudioVault TV Sync** tool (the
   `run_audiovault_sync` program), or with `git push`.
3. That is it. The next time anyone checks for updates, they get the new
   version. There is no `upload_to_s3.py` step any more.

## For the user (Ashley) — when you want the latest version

Either of these works:

- **Inside the program:** open the File menu and choose **Check for
  Updates**. If there are updates, it asks if you want them, then downloads
  them. You will need to close and reopen AudioVault TV for the changes to
  take effect.
- **On startup:** the program checks in the background when it opens and
  offers any updates it finds.
- **By hand:** double-click the **AudioVault TV Updater** (`update.py`). It
  shows a progress bar and a log of what it did, in plain words.

If there is no internet connection, the check just says so (or quietly
offers nothing on startup) and the program carries on playing normally.
Nothing breaks.

## How it decides what changed

The updater asks GitHub for the list of files in the repo. Each file has a
fingerprint (a git blob SHA) that describes its exact contents. The updater
works out the same fingerprint for the file on your computer. If they are
different, or the file is missing on your computer, it downloads the new
copy. It checks the downloaded copy's fingerprint before replacing the old
file, so a bad download never overwrites a good file.

## Files that do NOT come from GitHub

Some files are never in the GitHub repo, because the repo's `.gitignore`
leaves them out:

- The sounds: `sounds/startup.mp3`, `sounds/outro.mp3`,
  `sounds/start_of_request.wav`, `sounds/end_of_request.wav`,
  `sounds/remote.mp3`
- The tools programs: `tools/ffmpeg.exe`, `tools/ffprobe.exe`,
  `tools/ffplay.exe`, `tools/deno.exe`

The updater simply leaves those files alone and says so in the log
("Not in the GitHub repo, left alone"). It never deletes them and never
fails because of them.

If you install AudioVault TV on a new computer, copy the `sounds` folder
and the `tools` folder from the old computer afterwards. Note that GitHub
refuses single files over 100 MB, so the big tools programs may never be
able to live in the repo at all — the updater is built to cope with that.

## What did not change

- `main.py` still calls the same two functions, `check_for_updates()`
  and `apply_updates()`, from `auto_updater.py`.
- `upload_to_s3.py` and `S3_SETUP.md` have been deleted. There is no S3
  code left in the program at all.
- The old `.update_etags.json` file (the S3 change-memory) is no longer
  used. You can delete it; leaving it there is harmless.
- The log upload now goes to GitHub instead of S3. From the File menu,
  **Upload Log** sends `player_log.txt` to `logs/<your name>_log.txt` in
  this repo, with the same playback, navigation, and error information as
  before. It needs a GitHub token saved in `github_token.txt` next to the
  program (a fine-grained token for this repo with Contents read and
  write). The token file is never pushed to GitHub.

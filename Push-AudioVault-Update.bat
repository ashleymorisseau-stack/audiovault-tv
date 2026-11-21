@echo off
REM Push-AudioVault-Update.bat
REM Double-click this file to send your Audio Vault TV changes,
REM including any changed code and the log file, up to GitHub so Muse can read them.
REM Put this file inside the audiovault-tv folder on the PC.
REM It works from the folder it is in, so no Command Prompt typing is needed.
REM
REM What it does, step by step:
REM   1. Beeps once when it starts, so you know it is running.
REM      It also beeps and speaks at every step along the way --
REM      starting, pulling first, adding files, halfway, committing,
REM      pushing, almost done, then done -- so you always know if
REM      it is halfway done, almost done, done, or not completed.
REM      If a step fails, it plays one low beep and says plainly,
REM      Honey, that it did not finish and why, so you are not
REM      left waiting.
REM   2. Pulls the latest changes from GitHub FIRST, so GitHub is not ahead
REM      of this PC and the push is not rejected. This was the problem
REM      when you heard high, high, low: Muse had just put new
REM      code on GitHub, so her PC was behind, and the
REM      push was rejected. Pulling first fixes that.
REM   3. Adds EVERYTHING new or changed: any changed .py, .bat, .md
REM      and .txt files, and the log file if it is in this folder,
REM      and every brand-new file, no matter what it is called.
REM      It never adds pull_result.txt -- that note stays only on
REM      this PC, and it is also listed in .gitignore.
REM   4. Lists the files in this folder, so NVDA can read them.
REM      Audio Vault TV has no Sounds folder, so it lists the
REM      folder itself instead.
REM   5. Lists the files ready to send, so you can hear what is going up.
REM   6. Commits them with today date and time, if there is anything new.
REM   7. Pushes them to GitHub. If the first push is rejected for being
REM      behind, it pulls again and tries the push once more, by itself.
REM   8. When it is done, it plays two high happy beeps, 880 then 1320,
REM      then it says out loud, and shows on screen: "Push successful,
REM      Honey, it's on GitHub." It speaks with the Windows voice, so
REM      you can hear it even if NVDA does not read the window.
REM   9. If it really fails, it plays one low beep, 220, then it says
REM      out loud, and shows on screen, in plain words why it failed.
REM      The low beep is only for a real failure, never for nothing new.
REM  10. If there is nothing new, it says out loud, and shows on screen:
REM      "Nothing new to push, Honey. Everything is already on GitHub."
REM      with one medium beep, 660, not a low beep, so it never stays silent.
REM  11. It pauses at the end so NVDA can read what happened.
REM  12. Speaking never breaks the push: if the Windows voice is not
REM      available, the words are still shown on screen and the beeps
REM      still play.
REM
REM Before you run it: make sure any new file is inside this
REM audiovault-tv folder, not still in Downloads. A file still
REM in Downloads cannot be pushed.
REM
REM pull_result.txt is never sent to GitHub. It stays only on this PC.

cd /d "%~dp0%"
set "LOG=%TEMP%\audiovault_push_log.txt"
if exist "%LOG%" del "%LOG%"
echo Sending Audio Vault TV changes to GitHub, Honey...
powershell -NoProfile -Command "[console]::beep(660,200)"
set "SPEAK_MSG=Starting the push, Honey."
call :SPEAK
echo.
echo Before you push, make sure any new file is inside this folder,
echo not still in Downloads. A file still in Downloads cannot be pushed.
echo.
echo Files in this folder right now:
dir /b
echo.
echo Listen for your new files in that list. If one is not there,
echo move it into this folder first, then run this file again.
echo.
echo Pulling the latest changes from GitHub first, so the push is not rejected...
powershell -NoProfile -Command "[console]::beep(770,150)"
set "SPEAK_MSG=Pulling the latest changes from GitHub first, Honey."
call :SPEAK
git pull --no-edit > "%LOG%" 2>&1
set PULL_ERR=%errorlevel%
type "%LOG%"
echo.
if %PULL_ERR% NEQ 0 goto PULL_FAILED
echo.
echo Adding every new and changed file, Honey...
powershell -NoProfile -Command "[console]::beep(770,150)"
set "SPEAK_MSG=Adding your files now, Honey."
call :SPEAK
git add -A
git add *.py *.bat *.md *.txt 2>nul
REM pull_result.txt must never go to GitHub, even if it was added
REM above. Take it back out of the list of files ready to send.
git reset -q pull_result.txt 2>nul
powershell -NoProfile -Command "[console]::beep(880,150)"
echo Halfway done, Honey. Your files are added and ready to send.
set "SPEAK_MSG=Halfway done, Honey. Your files are added and ready to send."
call :SPEAK
echo.
echo Files ready to send:
git diff --cached --name-only
echo.
git status --short
echo.
git diff --cached --quiet
if errorlevel 1 goto HAS_CHANGES
goto NOTHING_NEW

:HAS_CHANGES
echo There are changes to send. Committing them now, Honey...
powershell -NoProfile -Command "[console]::beep(770,150)"
set "SPEAK_MSG=Committing your changes now, Honey."
call :SPEAK
git commit -m "Update from PC on %DATE% %TIME% - Audio Vault TV" > "%LOG%" 2>&1
set COMMIT_ERR=%errorlevel%
type "%LOG%"
echo.
if %COMMIT_ERR% NEQ 0 goto COMMIT_FAILED
goto PUSH

:PUSH
echo Pushing to GitHub now, Honey...
powershell -NoProfile -Command "[console]::beep(990,150)"
set "SPEAK_MSG=Pushing to GitHub now, Honey."
call :SPEAK
git push > "%LOG%" 2>&1
set PUSH_ERR=%errorlevel%
type "%LOG%"
echo.
if %PUSH_ERR% NEQ 0 goto PUSH_RETRY
goto PUSH_OK

:PUSH_RETRY
echo The first push did not go through, Honey. Pulling again and trying once more...
powershell -NoProfile -Command "[console]::beep(990,150)"
set "SPEAK_MSG=The first push did not go through, Honey. Pulling again and trying once more."
call :SPEAK
git pull --no-edit > "%LOG%" 2>&1
set PULL2_ERR=%errorlevel%
type "%LOG%"
echo.
if %PULL2_ERR% NEQ 0 goto PUSH_FAILED
git push > "%LOG%" 2>&1
set PUSH2_ERR=%errorlevel%
type "%LOG%"
echo.
if %PUSH2_ERR% NEQ 0 goto PUSH_FAILED
goto PUSH_OK

:PUSH_OK
echo Almost done, Honey.
powershell -NoProfile -Command "[console]::beep(990,150)"
set "SPEAK_MSG=Almost done, Honey."
call :SPEAK
powershell -NoProfile -Command "[console]::beep(880,250); [console]::beep(1320,400)"
echo Push successful, Honey, it's on GitHub.
echo Your changes are now on GitHub for Muse to read.
set "SPEAK_MSG=Push successful, Honey, it's on GitHub."
call :SPEAK
goto END

:PULL_FAILED
echo The pull did not finish, Honey, so the push cannot go through yet.
echo Here is what GitHub said:
type "%LOG%"
echo.
powershell -NoProfile -Command "[console]::beep(220,500)"
call :EXPLAIN
goto END

:COMMIT_FAILED
echo The commit did not finish, Honey. Please try running this file again.
echo Here is what GitHub said:
type "%LOG%"
echo.
powershell -NoProfile -Command "[console]::beep(220,500)"
call :EXPLAIN
goto END

:PUSH_FAILED
echo The push did not finish, Honey, even after pulling and trying again.
echo Here is what GitHub said:
type "%LOG%"
echo.
powershell -NoProfile -Command "[console]::beep(220,500)"
call :EXPLAIN
goto END

:NOTHING_NEW
echo Nothing new to push, Honey. Everything is already on GitHub.
echo If a new file is in this folder but it says nothing new, it may not be in this folder yet.
echo If your new file is still in Downloads, move it into this folder, then run this file again.
powershell -NoProfile -Command "[console]::beep(660,250)"
set "SPEAK_MSG=Nothing new to push, Honey. Everything is already on GitHub."
call :SPEAK
goto END

:END
echo.
pause
exit /b 0

:EXPLAIN
findstr /i /c:"rejected" /c:"non-fast-forward" "%LOG%" >nul && echo In plain words: GitHub has newer changes than this PC. Please run Pull-AudioVault-Update.bat, then run this push file again. && set "SPEAK_MSG=Push failed, Honey, because GitHub has newer changes than this PC. Please run Pull first, then run this push file again." && call :SPEAK && goto :eof
findstr /i /c:"Authentication failed" /c:"could not read Username" /c:"403" /c:"401" "%LOG%" >nul && echo In plain words: GitHub did not accept the sign-in on this PC. Please check the sign-in or token, then try again. && set "SPEAK_MSG=Push failed, Honey, because GitHub did not accept the sign-in on this PC. Please check the sign-in, then try again." && call :SPEAK && goto :eof
findstr /i /c:"Could not resolve host" /c:"Failed to connect" /c:"Network is unreachable" /c:"Connection timed out" /c:"unable to access" "%LOG%" >nul && echo In plain words: There is no internet connection to GitHub right now. Please check the internet, then try again. && set "SPEAK_MSG=Push failed, Honey, because there is no internet connection to GitHub right now. Please check the internet, then try again." && call :SPEAK && goto :eof
findstr /i /c:"CONFLICT" "%LOG%" >nul && echo In plain words: Your changes conflict with GitHub. Please ask Muse for help before pushing again. && set "SPEAK_MSG=Push failed, Honey, because your changes conflict with GitHub. Please ask Muse for help before pushing again." && call :SPEAK && goto :eof
echo In plain words: The push did not finish. Please try running this file again, and tell Muse what GitHub said above.
set "SPEAK_MSG=Push failed, Honey. Please try running this file again, and tell Muse what GitHub said."
call :SPEAK
goto :eof

:SPEAK
REM Speak the text in SPEAK_MSG out loud with the Windows voice.
REM If speech is not available, ignore the error and keep going:
REM the words are still on screen, and the beeps still play.
powershell -NoProfile -Command "try { Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak($env:SPEAK_MSG); } catch { }" 2>nul
goto :eof

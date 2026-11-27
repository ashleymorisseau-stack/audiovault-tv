@echo off
REM Pull-AudioVault-Update.bat
REM Double-click this file to pull the latest Audio Vault TV changes.
REM Put this file inside the audiovault-tv folder on the PC.
REM It pulls from the folder it is in, so no Command Prompt typing is needed.
REM It also brings down Push-AudioVault-Update.bat, if one was pushed.
REM
REM What it does now, just like the push file:
REM   1. Beeps once when it starts, so you know it is running.
REM      It also beeps and speaks at every step along the way --
REM      starting, pulling from GitHub, halfway, almost done, then
REM      done -- so you always know if it is halfway done, almost
REM      done, done, or not completed. If a step fails, it plays
REM      one low beep and says plainly, Ashley, that it did not
REM      finish and why, so you are not left waiting.
REM   2. Pulls the latest changes from GitHub. It fetches first, then
REM      pulls with rebase and autostash, so local changes or a stash
REM      do not stop it from getting the updates.
REM   3. Writes a little text note called pull_result.txt in this
REM      same folder, saying whether the pull worked. On success it
REM      says "Pull successful, Ashley! It's done." with the date and
REM      time, and what changed, if anything changed. If everything
REM      was already up to date, it says so. On failure it says so
REM      in plain words. You can open pull_result.txt with NVDA any
REM      time to hear how the last pull went.
REM   4. It also says the same words out loud with the Windows voice,
REM      just like the push file does, so you can hear it even if
REM      NVDA does not read the window.
REM   5. When it is done, it plays two high happy beeps, so you know
REM      it finished without looking. If it fails, it plays one low beep.
REM   6. Lists the files in this folder, so NVDA can read them.
REM      Audio Vault TV has no Sounds folder, so it lists the
REM      folder itself instead.
REM   7. It pauses at the end so NVDA can read what happened.
REM   8. Speaking never breaks the pull: if the Windows voice is not
REM      available, the words are still on screen, the note file is
REM      still written, and the beeps still play.
REM
REM pull_result.txt is only on this PC. It is never pushed to GitHub.

cd /d "%~dp0%"
set "LOG=%TEMP%\audiovault_pull_log.txt"
set "NOTE=pull_result.txt"
if exist "%LOG%" del "%LOG%"
echo Starting the pull now, Ashley...
powershell -NoProfile -Command "[console]::beep(660,200)"
set "SPEAK_MSG=Starting the pull, Ashley."
call :SPEAK
echo.
echo Pulling the latest Audio Vault TV changes from GitHub...
powershell -NoProfile -Command "[console]::beep(770,150)"
set "SPEAK_MSG=Pulling from GitHub now, Ashley."
call :SPEAK
echo.
git fetch origin > "%LOG%" 2>&1
git pull --rebase --autostash --no-edit >> "%LOG%" 2>&1
set PULL_ERR=%errorlevel%
type "%LOG%"
echo.
if %PULL_ERR% NEQ 0 goto PULL_FAILED
findstr /i /c:"Already up to date" "%LOG%" >nul
if %errorlevel% EQU 0 goto ALREADY_UP_TO_DATE
goto PULL_OK

:PULL_OK
echo Halfway done, Ashley. The pull finished. Now I am writing your note.
powershell -NoProfile -Command "[console]::beep(770,150)"
set "SPEAK_MSG=Halfway done, Ashley. The pull finished. Now I am writing your note."
call :SPEAK
echo Almost done, Ashley.
powershell -NoProfile -Command "[console]::beep(990,150)"
set "SPEAK_MSG=Almost done, Ashley."
call :SPEAK
powershell -NoProfile -Command "[console]::beep(880,250); [console]::beep(1320,400)"
echo Pull successful, Ashley! It's done.
echo New changes came down from GitHub.
(
echo Pull successful, Ashley! It's done.
echo.
echo Date and time: %DATE% %TIME%
echo.
echo New changes came down from GitHub. Here is what changed:
echo.
type "%LOG%"
) > "%NOTE%"
echo.
echo I wrote a little note for you in this folder called pull_result.txt.
echo It says the pull worked, Ashley, and what changed.
echo.
echo Files in this folder right now:
dir /b
set "SPEAK_MSG=Pull successful, Ashley! It's done. New changes came down from GitHub."
call :SPEAK
goto END

:ALREADY_UP_TO_DATE
echo Halfway done, Ashley. The pull finished. Now I am writing your note.
powershell -NoProfile -Command "[console]::beep(770,150)"
set "SPEAK_MSG=Halfway done, Ashley. The pull finished. Now I am writing your note."
call :SPEAK
echo Almost done, Ashley.
powershell -NoProfile -Command "[console]::beep(990,150)"
set "SPEAK_MSG=Almost done, Ashley."
call :SPEAK
powershell -NoProfile -Command "[console]::beep(880,250); [console]::beep(1320,400)"
echo Pull successful, Ashley! It's done.
echo Everything was already up to date. Nothing new came down.
(
echo Pull successful, Ashley! It's done.
echo.
echo Date and time: %DATE% %TIME%
echo.
echo Everything was already up to date. Nothing new came down.
) > "%NOTE%"
echo.
echo I wrote a little note for you in this folder called pull_result.txt.
echo It says the pull worked, Ashley, and everything was already up to date.
echo.
echo Files in this folder right now:
dir /b
set "SPEAK_MSG=Pull successful, Ashley! It's done. Everything was already up to date."
call :SPEAK
goto END

:PULL_FAILED
echo The pull did not finish, Ashley.
echo Here is what GitHub said:
type "%LOG%"
echo.
powershell -NoProfile -Command "[console]::beep(220,500)"
call :EXPLAIN
goto END

:END
echo.
pause
exit /b 0

:EXPLAIN
findstr /i /c:"Could not resolve host" /c:"Failed to connect" /c:"Network is unreachable" /c:"Connection timed out" /c:"unable to access" "%LOG%" >nul && set "FAIL_REASON=There is no internet connection to GitHub right now. Please check the internet, then try again." && goto FAIL_NOTE
findstr /i /c:"Authentication failed" /c:"could not read Username" /c:"403" /c:"401" "%LOG%" >nul && set "FAIL_REASON=GitHub did not accept the sign-in on this PC. Please check the sign-in or token, then try again." && goto FAIL_NOTE
findstr /i /c:"CONFLICT" "%LOG%" >nul && set "FAIL_REASON=Your changes conflict with GitHub. Please ask Muse for help before pulling again." && goto FAIL_NOTE
set "FAIL_REASON=The pull did not finish. Please try running this file again, and tell Muse what GitHub said above."
goto FAIL_NOTE

:FAIL_NOTE
echo In plain words: %FAIL_REASON%
(
echo Pull did not finish, Ashley.
echo.
echo Date and time: %DATE% %TIME%
echo.
echo %FAIL_REASON%
) > "%NOTE%"
echo.
echo I wrote a little note for you in this folder called pull_result.txt.
echo It says the pull did not finish, Ashley, and why.
set "SPEAK_MSG=Pull did not finish, Ashley. %FAIL_REASON%"
call :SPEAK
goto :eof

:SPEAK
REM Speak the text in SPEAK_MSG out loud with the Windows voice.
REM If speech is not available, ignore the error and keep going:
REM the words are still on screen, the note file is still written,
REM and the beeps still play.
powershell -NoProfile -Command "try { Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.Speak($env:SPEAK_MSG); } catch { }" 2>nul
goto :eof

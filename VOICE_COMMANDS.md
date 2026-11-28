# Voice Commands Reference

## Two Modes of Voice Control

### Mode 1: One-Time Command (Ctrl+Shift+B)
1. Press **Ctrl+Shift+B** to start listening
2. Speak your command clearly within 20 seconds. It keeps listening through a short pause, so you do not have to rush.
3. You do not have to say "Samantha" in this mode. Just say the command, for example "search for Young Sheldon".
4. A voice search also downloads the show. Say "search for Young Sheldon" and that is it — it searches AudioVault for the exact show and downloads it in the background, so you do not have to say "download it" afterwards. Saying "download Young Sheldon" does the same thing.
5. Samantha says "I'm listening" when she starts listening.
6. If she cannot hear you, or does not understand what you said, she says "Excuse me, I didn't hear you. Could you say that again?"
7. Press **Ctrl+Shift+B** again to stop listening early

### Mode 2: Wake Word Mode (Ctrl+Shift+W) - Recommended
1. Press **Ctrl+Shift+W** to activate continuous listening
2. Say **"Samantha"** followed by your command
3. Example: "Samantha, play" or "Samantha, next file"
4. The app stays in listening mode until you press **Ctrl+Shift+W** again
5. NVDA announces "Listening..." when wake word is detected

**Wake Word Mode is hands-free** - no need to press any keys once activated!

## Your Name — Samantha Remembers It

Samantha learns your name only when you tell it to her by voice, and she remembers it after you close and reopen Audio Vault TV. She never guesses a name you have not told her. Your name is saved on your own PC only, in config.ini, and is never pushed to GitHub.

| Say This | Action |
|----------|--------|
| "my name is Honey" | Samantha remembers your name is Honey |
| "call me Honey" | Samantha remembers to call you Honey |
| "remember my name is Honey" | Samantha remembers your name is Honey |
| "what is my name" | Samantha tells you the name she remembers for you |
| "do you know my name" | Samantha tells you the name she remembers for you |
| "forget my name" | Samantha forgets your name |
| "what is your name" | Samantha says "My name is Samantha" |
| "hello" / "hi" | Samantha greets you by name, if she knows it |

When she knows your name, Samantha greets you with it when she hears her wake word — "Hi Honey, I'm listening" — instead of just "I'm listening". Samantha does the greeting in her own recorded voice; NVDA does not greet you as well, so you only hear her. You can set your own name, including your real name, any time: tell Samantha by voice, for example "my name is Honey", or use Controls, then Set My Name, and type it in. Your name is saved on your own PC only, in config.ini, and is never pushed to GitHub.

## Samantha's Own Voice

Samantha now speaks in her own recorded voice, not just NVDA. Her voice is friendly, excited but not yelling, and a little louder than the first recording.

- Her full name is Samantha Hernandez Right — first name Samantha, middle name Hernandez, last name Right. You still call her Samantha. Ask "what is your name" and she says it in her own voice: "Hi! My name is Samantha Hernandez Right. What is your name?" Her voice file is sounds/samantha_my_name_is.wav.
- When Samantha hears her wake word, she asks in her own voice: "What do you want to watch?"
- When you ask "what is your name", she answers in her own voice: "Hi, my name is Samantha. What is your name?"
- Her voice files are in the sounds folder: samantha_greeting.wav (3.4 seconds) and samantha_what_to_watch.wav (1.6 seconds).

## How to Talk to Samantha — Press a Button First (2026-11-27)

Samantha only listens when you press a button. She never listens in the background while a show is playing, and she never starts listening by herself — not after the greeting, and not after she answers a command. That was the bug: she was listening all the time, heard the show itself as commands ("playing", "stopped", "playback"), and paused the show in the middle of it. Now the show keeps playing unless you ask her to change it.

- **Ctrl+Shift+B — press once to talk.** Press it, Samantha says "I'm listening" in her own voice (after the high chime, then the low chime), then she listens for one command for 20 seconds, understands it, answers, and stops listening. You do NOT say her name first — just press B and speak. If you press B again while she is already listening, she says "I'm already listening. Go ahead." instead of switching herself off. B works even when the cursor is in the text box.
- **Ctrl+Shift+W — always listen, wake-word mode.** Press it once and it stays on. Samantha says "I'm listening. Say my name, then your command." Then you say her name — Samantha, Sam, Sammy, Guide, or Metro — followed by your command, for example "Samantha, list shows" or "Sam, play Classic Doctor Who". When she hears her name she answers "Yes?" in her own voice, then listens for the command (15 seconds after the name, or in the same breath). She stays in this mode, so you can say her name again for the next command. Press Ctrl+Shift+W again to turn it off.
- If you say nothing, she stops quietly instead of repeating "Excuse me". If she hears words but cannot understand them, she says what she did hear and gives one example: "Excuse me, I didn't understand list me shows. I heard list me shows. Try saying, list shows, or play Doctor Who."

She understands the same command said several ways, and she fixes the words Vosk often hears wrong: "list shows", "list my shows", "list me shows", "what shows do I have", "what do I have to watch", "show me what shows I have", "play Doctor Who", "play Classic Doctor Who", "watch Classic Doctor Who" — and "please" or "thank you" at the end never breaks it. She already has Classic Doctor Who, so "play Classic Doctor Who" just plays it — she does not search or download it again.

## Playing a Whole Series — No Quiet Moments (2026-11-27)

A show plays all the way through. When one file really finishes, the next file in the same channel plays; when the whole channel (the whole series) is finished, the next channel plays, and so on, so you can sleep with it on and it keeps going. It never moves on because the sound went quiet for a moment — there is no quiet-moment check at all, not one moment and not three. It only moves on when pygame itself says the track finished (its own music-end signal), or, as a backup, when pygame says the music is not playing at all and you were well into the file. A quiet passage in the middle of an episode, or a brief hiccup, never stops it or jumps it ahead.

## Wake Words — Samantha, Sam, Sammy, Guide, Metro

Samantha answers to five wake words, in wake-word mode only (Ctrl+Shift+W, see above): Samantha, Sam, Sammy, Guide, and Metro. Say any one of them, then your command — for example "Sam, play Friends" or "Guide, what are my options?" When she hears her name she answers "Yes?" in her own recorded voice (sounds/samantha_yes.wav), then listens for your command. You still call her Samantha most of the time; the other names are there when you want them.

## "I'm Good" — Samantha Answers, Then Lists Your Channels and What's Next

Samantha asks "Hi Sweetie! How are you doing? What do you want to watch?" in her own voice when Audio Vault TV opens, and when she hears her wake word. Answer her by voice: press **Ctrl+Shift+B** and say "I'm good", or say "Samantha, I'm good" in wake-word mode.

- Samantha answers in her own recorded voice: "That's wonderful! I'm so glad you're doing good. What do you want to watch?" Her voice file is sounds/samantha_glad_youre_good.wav. NVDA does not repeat it.
- Then, without you having to ask, she reads the list of shows you have, so you can tell her which one you want to watch.
- Then she tells you what comes up next in the TV guide — including marathons, folded into one smooth sentence, for example "Coming up next is a marathon of Classic Doctor Who, starting with season 1, episode 2, The Daleks", or a marathon of Two and a Half Men, Friends, or Frasier, on whatever channels you have.
- Then tell her the channel you want, for example "play Friends" or "play Classic Doctor Who", and she will take you there.

You can also ask for the list on its own, any time: "Samantha, list all the channels I have" or "what channels do I have".

The channel names, and the show names in the guide, change as you add channels, so they are read in the app's usual speaking voice — Samantha's voice is recordings and cannot read new names she never recorded — the same pattern as the TV guide below.

## List of Shows — "What Are My Options?"

Ask Samantha, by voice, "What are my options?" or "tell me the list of shows I have", and she reads out all the shows you have — one name per channel, in the order they are sorted — so you can choose the show you want. A channel is a show: your library is named after episodes ("01 Ruby Reborn.mp3"), so the list comes from your channel names, the same names she reads for "list channels". After the list she says "I'm listening" and waits — you just say the show you want, for example "Doctor Who" or "I want Two and a Half Men" — no "play" needed, and she takes you there. The names change as you add channels, so they are read in Samantha's reading voice, the same pattern as the TV guide.

After the list, three things all work the same way:

- Say the show by name only — "Doctor Who", "corner gas" — and it plays.
- Say "I want ...", "let's watch ...", "I'm going to watch ..." and it plays.
- Say "play ..." like before — unchanged.

If you name a show you do not have ("I want Friends"), she says plainly "You don't have a channel called Friends, so I didn't change anything."

| Say This | Action |
|----------|--------|
| "what are my options" | Samantha reads the list of shows you have |
| "tell me the list of shows I have" | Same as above |
| "what shows do I have" | Same as above |
| "list all the shows" | Same as above |
| "list my shows" | Same as above |
| "list me shows" | Same as above — Vosk hears "my" as "me", and that is fixed now |
| "what do I have to watch" | Same as above |
| "show me what shows I have" | Same as above |
| "list all the channels I have" | Samantha reads the list of channels you have |

## Loading Is Silent — Samantha Greets You in Her Voice

Audio Vault TV does not print "Loading ..." lines any more, because NVDA reads the terminal out loud and was saying every loading line while the app opened. Loading is silent now. The only thing you hear is Samantha, in her own voice, saying "Hi Sweetie! How are you doing? What do you want to watch?" when the app is ready.

## NVDA Quiet Toggle — Ctrl+Shift+Q

Press Ctrl+Shift+Q in Audio Vault TV to turn NVDA quiet on or off while you are in the app. When NVDA is quiet, you hear Samantha's voice and the shows, not NVDA. NVDA used to keep saying "pane" all the time, because focus landed on the main panel, which NVDA announces by its role — the panel is now named Audio Vault TV, focus goes to the "Type to Samantha" box instead, the window is only raised when it is not already active, and any queued NVDA speech is cleared before quiet mode is turned on. When you close the app, NVDA talks again. The menus themselves are still read by NVDA when NVDA is back on, because Samantha's voice is recordings and cannot read new menu names she never recorded — the same limit as the TV guide.

Ctrl+Shift+G is not the NVDA toggle — it was already the TV guide key ("What's Coming Up Next"), so it stays the guide. If you press Ctrl+Shift+G you hear the guide, not a toggle.

## Downloads in Samantha's Voice

When Samantha starts downloading a show for you, from AudioVault.net or from YouTube, she says in her own recorded voice "I'm downloading that show for you" (sounds/samantha_downloading.wav), so you hear it even with NVDA quiet on.

## "Can You Hear Me?" — Only "Yes" When She Really Can

When you ask Samantha "can you hear me", "do you hear me", or "are you listening", she answers in her own recorded voice "Yes, I can hear you" (sounds/samantha_yes_i_can.wav) — but only when listening is really working. That answer used to be a lie: the reading voice being ready does not mean she can hear you at all. Listening and speaking are separate things (see "Samantha Can Hear You" below). If she cannot hear yet, she says so instead, in her own voice, and tells you why — "I cannot hear you yet. I am still getting my listening ready", or "the listening model did not install" — and she tries again by herself in a minute. You can also ask "why can't you hear me" (or "why can you not hear me"), and she tells you the plain reason for the last try, in her own voice when the reading voice is up, or with her recorded "Excuse me" clip when it is not, with the reason on the status line either way.

## Samantha Can Hear You — the Listening Model

Listening (Vosk) and speaking (Edge TTS, the reading voice) are separate. "My reading voice is ready" means she can read the list out loud; it does not mean she can hear you. Hearing needs a second thing, a listening model — a folder called vosk-model-small-en-us-0.15 beside main.py. That folder was the missing piece: the app used to pip-install the listening library, but it never downloaded the model itself, so VoiceControl() failed at startup and listening stayed off for the whole run, while the reading voice said it was ready. And when you pressed Ctrl+Shift+B or Ctrl+Shift+W, the answer went through NVDA, which is quiet in the app, so you heard nothing at all — not even that listening was off.

Now the app downloads and installs the listening model itself, in the background, when it opens — about 40 MB from alphacephei.com, unzipped beside main.py, with a double-nested folder flattened so the model ends up exactly where it is looked for. The listening libraries themselves (Vosk and sounddevice) are also loaded only when they are needed now, so a missing library no longer stops the app from opening or typing from working — listening just stays off, with a plain reason, until the app installs the library and tries again by itself. It checks disk space first (under 200 MB free fails plainly instead of filling the disk), says "I'm on it" while it downloads, and retries by itself every 1 minute if a try fails, with the plain reason in the app log ("VOSK MODEL install failed: ..."). One install at a time, never two at once. When the model is ready, Samantha says "I can hear you now. Ask me to list your shows." in her own voice. She still waits for you to press a button — she never starts listening by herself (see "How to Talk to Samantha" above). If the model was already there when the app opened, nothing is downloaded and nothing extra is said.

You can also ask for it directly, any time: say or type "install the listening model" (or "get Samantha listening", or "make Samantha listen"), or use Controls, then "Install the Listening Model". That always forces a fresh try right now, even if a try just failed a moment ago. Samantha says "I'm on it", the download runs in the background, and when it is ready she says she can hear now. If she can already hear, she just says so instead of downloading again.

Pressing Ctrl+Shift+B or Ctrl+Shift+W when listening is not available is no longer silent: Samantha answers in her own voice — the full plain reason in her reading voice when it is up, or her recorded "Excuse me" clip when it is not — and the model install is kicked off if it is not already running. The same goes for answering the greeting: if she cannot listen yet, she says so once, instead of just never listening. If the microphone itself fails (no mic, mic in use), she says that as a voice error in her own voice, with the plain reason, instead of "Excuse me" as if you had simply not spoken.

There is no Command Prompt step for any of this any more. No NVDA or Microsoft voice is ever used for these announcements — Samantha's own voice only. The wake words (Samantha, Sam, Sammy, Guide, Metro), her full name (Samantha Hernandez Right), Ctrl+Shift+Q (NVDA quiet), Ctrl+Shift+G (TV guide), the reading voice, the text box, and the chimes (once each) are all unchanged.

## "I'm Good" — Answer Her After You Press B (or in Wake-Word Mode)

When Samantha greets you at startup and asks how you are doing, she does NOT start listening by herself — she waits for you to press a button (see "How to Talk to Samantha" above), because listening by itself was hearing the show and cutting it off. So to answer her: press **Ctrl+Shift+B** and say "I'm good", or press **Ctrl+Shift+W** and say "Samantha, I'm good". After her recorded reply ("That's wonderful! I'm so glad you're doing good."), she reads your shows and what's coming up next. That list and guide are read in Samantha's own reading voice, never NVDA — NVDA stays quiet for all of it. Then, once every reading has finished, she says "I'm listening" and opens the microphone for one turn: you just say the show you want ("Doctor Who") and it plays. Nothing is playing at that moment — you are still choosing — which is why listening here is safe, and the turn ends with your command or after 20 seconds of silence and never re-arms, so a show playing afterwards is never heard as a command. If you said nothing, she says "Excuse me, I didn't hear you" once; press B again any time.

## Startup — What Samantha Says When the App Opens

When Audio Vault TV opens, Samantha does this, one thing at a time, in her own voice:

1. She says "Audio Vault TV" (sounds/audio_vault_tv.wav, her own recorded voice, about 2 seconds).
2. She greets you: "Hi Sweetie! How are you doing? What do you want to watch?" — that is also her asking what channels you want.
3. She waits for you to press a button. Press **Ctrl+Shift+B** and say "I'm good", and she says "That's wonderful! I'm so glad you're doing good." and then names the channels you have and what comes up next. Or press **Ctrl+Shift+W** and say "Samantha, I'm good" — same answer. If you name a show after pressing B, it plays. If you say nothing, she stays quiet — she does not listen by herself, and she does not name the channels until you ask.

She waits longer between your words now (4 seconds instead of 2.5), so she hears every word even if you pause. And in wake-word mode she says "Excuse me" only once in a row, then stays quiet and keeps listening, instead of repeating it.

## Samantha Reads the List Herself — No NVDA, No Microsoft

The list of shows, the list of channels, the TV guide, and the "you have it / you don't have it" answer are all read by Samantha herself, not by NVDA. NVDA never reads the list — Ashley said "I don't want NVDA to use the list. I want her to use the list." NVDA stays quiet for all of it, and the quiet toggle is never turned off for a reading.

Samantha's recorded voice cannot read show names she never recorded, so the readings use a reading voice that can say any words. There is exactly one reading voice, and it is NOT Microsoft: Edge TTS, a warm female neural voice (Aria). Microsoft's own speech (System.Speech / Zira) was tried once and is gone for good — Ashley said "I didn't tell you to add Microsoft" and "I don't like Microsoft Sierra", so it is never used, not even as a fallback.

The reading voice was not installed on her PC, which is why the Microsoft voice was used instead. So when the app opens, it now installs Edge TTS itself, in the background, with no window and nothing blocked — no Command Prompt step, ever. You only have to open the app and wait.

Since 2026-11-27 the reading voice ships WITH the app, in a folder called vendor/ next to main.py, so it is ready the moment the app opens and no install is needed at all on a normal open — the library and everything it needs are already there in the app folder, and they come down with the usual pull. The internet is still needed for the voice itself to speak (Edge TTS speaks over the internet), but not to have the library. If vendor/ is ever missing, the app falls back to installing Edge TTS itself as before. The greeting also waits a little longer now (2.5 seconds after the window opens instead of 1), so the voice is confirmed ready before Samantha asks you anything — that was the other half of the bug: she asked "What do you want to watch?" and you answered before the install had even started, so the first thing you heard was "not ready". While an install is still running, you now hear "I'm on it" and the list is read when it is ready — "not ready" is only ever said after a try has really failed, never while nothing has failed yet.

If the voice is not ready, you can ask why: say or type "why is my reading voice not ready" (or "what happened to my reading voice"). Samantha tells you the plain reason for the last try — "there is no internet connection right now", "the disk is full", "Windows would not let the app write the files" — in her own reading voice when it is up, and the full pip error stays in the app log ("EDGE-TTS install failed: ..." / "REQUIREMENTS install failed: ..."). One honest limit: when the reading voice itself is down, there is no voice that can speak the reason out loud — her recorded clips cannot say words she never recorded — so then you hear the "not ready" clip once, and the plain reason is on the status line and in the log, where it can be read back to you.

Why it kept saying "not ready" anyway, and what changed: the old background install was silent and fragile — it re-ran pip on nearly every start even when the voice was already there, it could start two pip installs at once (one at startup, one from asking for the list) that fought each other, it cached "not ready" for the whole run so the list stayed unread even after an install finished, and it only ever retried once per run. Worst of all, the startup install thread was started before the lock it needed even existed, so it could return silently and no install ever happened at all. Now the app checks first whether Edge TTS already imports and installs nothing if it does; only one install ever runs at a time; a finished install is verified by re-importing Edge TTS in the same app before it counts as ready; pip is tried twice per attempt (first normally, then once per-user with --user, in case the normal install is blocked); and a failed try is written in the app log (last lines of pip's own error, "EDGE-TTS install failed: ...") instead of vanishing. While it is installing, Samantha says "I'm on it" in her own recorded voice, so you hear it happening, and asking for the list says "I'm on it" too and the list is read to you when the voice is ready — you do not have to ask again. If a try fails, Samantha says so herself in her own recorded voice — "My reading voice isn't ready yet. Give me a moment, then ask me again." — once for that failure, and the app then tries again by itself every 1 minute while the voice is not ready, so you do not have to ask again or do anything at all. When the install finishes, Samantha now always tells you in the reading voice itself — "My reading voice is ready now. Ask me to list your shows." — even if you did not ask for a list, so you know the moment it is ready when you open the program. If the reading voice is not ready yet when she asks for the list, Samantha says so herself in her own recorded voice instead of NVDA reading anything.

You can also ask for the voice directly, any time: say or type "install my reading voice" (or "get my reading voice ready"), or use Controls, then "Install My Reading Voice". That always forces a fresh try right now, even if a try just failed a moment ago. Samantha says "I'm on it", the install runs in the background, and when it is ready she says so in the reading voice: "My reading voice is ready now. Ask me to list your shows." If the voice is already ready, she just says so instead of installing again.

There is no Command Prompt step for this any more. If the install keeps failing after the app has retried on its own, the pip error in the app log is the next thing to look at — not a command for you to type. No NVDA or Microsoft voice is ever used instead.

One voice at a time: a reading now waits for any Samantha recording that is still playing ("I'm on it", the guide intro, the greeting) to finish before it starts, and listening waits while Samantha is reading, so nothing talks over her and she is never heard as her own command.

One honest note: the reading voice is now the same Fish Audio voice that greets you, not a different neural voice. Samantha reads the list of channels, the list of shows, and the TV guide in your chosen Fish Audio voice — the one that says "Hi, my name is Samantha." The app calls Fish Audio over the internet (the same `api.fish.audio` your NVDA "fishy" add-on uses) with your API key, which it reads from your NVDA fishy settings automatically, so you do not type anything. The voice itself is set in `config.ini` — `samantha_fish_voice` — and the default is the custom "Ariana Grande" voice, the one measured closest to the greeting in pitch. If a Fish Audio call fails (no internet), that one reading falls back to the Edge TTS voice so the list is still read; the bad day costs the voice, not the list. To try the voices, an audition is ready: `voice_samples/Fish_voice_audition.wav` plays the real recording first, then each Fish Audio voice reading the channel-list line, so you can hear which one you want and tell me the name.

## The App Installs Everything It Needs Itself — No Command Prompt

Ashley asked: whatever requirements she needs for Command Prompt, the app should just get them and install them itself, so she never has to do it in Command Prompt. That is now how the app works, for everything it needs — not just the reading voice.

When the app opens, it checks for each library it needs and installs any that are missing, in the background, one at a time:

- edge-tts — Samantha's reading voice, so she can read the list of shows.
- vosk — voice listening, so Samantha can hear you.
- sounddevice — the microphone, so listening has something to listen with.
- pygame — playing sounds and shows.
- requests — getting shows from AudioVault.
- beautifulsoup4 — reading the show pages.
- yt-dlp — YouTube search and downloads.
- cloudscraper — getting shows (optional: the app already falls back to plain requests without it, so it never blocks the rest).

wxPython is the one exception, and it has to be: the app cannot open at all without it, so there is no app yet to install it from — it has to come with the installer.

How it works: the reading voice is installed first, then the rest, one pip install at a time — never two at once, so they cannot fight each other. Samantha says "I'm on it" in her own recorded voice while installs are running, so you hear it happening. When everything is ready she says so in the reading voice itself: "Everything is ready now. Ask me to list your shows." If something fails, she says the plain reason once — "there is no internet connection right now", "the disk is full", "Windows would not let the app write the files" — instead of going silent or repeating "not ready" forever, and the app tries again by itself every 1 minute. The full pip error still goes to the app log, so it can be found if it keeps failing.

After the libraries, the app gets the listening model itself (see "Samantha Can Hear You" above) — that is the last step in the same chain, so listening comes alive without restarting the app and without Command Prompt.

Three ways the old install failed silently, now fixed: first, the app used to run pip with its own program file as if it were Python — when the app runs as a built .exe, that file is not Python and has no pip, so the install failed at once with no message. Now it uses a real Python (its own, or the `py` launcher, or `python`), and if a Python has no pip at all it puts pip there first with ensurepip and tries again. Second, an unexpected error inside the install used to kill the background thread and leave the app stuck saying "I'm on it" forever, with no retry — now that counts as a failed try, with the reason logged and a retry in 1 minute. Third, a library that was missing when the app opened used to stop the whole app from starting, because its import ran at the top of the file before the installer could run at all — now those imports are guarded, the app opens, the install gets the library, and the app loads it afterwards, so the feature comes alive without restarting.

You can also ask for it directly, any time: say or type "install everything I need" (or "get everything ready"), or use Controls, then "Install Everything I Need". That always forces a fresh try right now, even if a try just failed a moment ago. Samantha says "I'm on it", the installs run in the background one at a time, and she says when it is all ready. If everything is already ready, she just says so instead of installing again.

There is no Command Prompt step for any of this any more. No NVDA or Microsoft voice is ever used for these announcements — Samantha's own voice only, her recorded clips while installing and her reading voice when it is ready.

## Type to Samantha — the Text Box

There is a text box at the bottom of the window, labelled "Type to Samantha (press Enter)". It is there for when Samantha cannot hear you: type a command — "play Friends", "list shows", "what are my options" — and press Enter, and Samantha answers in her own voice, exactly as if you had spoken it. Tab reaches the box. Typing in the box never pauses playback or triggers the other hotkeys.

Why Enter used to do nothing you could hear: the commands did run, but nearly every answer was spoken through NVDA — and NVDA is quiet while you are in the app, so NVDA said nothing at all and the box seemed dead. Now every command answer goes through Samantha herself: her reading voice when it is ready, or a short recorded clip when it is not ("I'm on it" when something was done, "Excuse me" when she did not understand). That covers pause, next/previous file and folder, next/previous channel, rewind, fast-forward, and the live-TV fallback too — those answers used to go through NVDA as well, so typing "pause" ran it and she heard nothing. Three other fixes in the same area: the app no longer yanks focus out of the text box when NVDA quiet is switched on, Enter is caught by the key itself as well as by the text-enter event, so the command runs once even if one of those paths swallows it, and the box keeps focus after Enter, so she can type the next command straight away without having to find the box again. Typing still works even with no Vosk model installed: the text is parsed without any voice recognition. One boundary to know: download and search progress ("Downloading 2 of 5...") is still announced through NVDA, because those messages come from background download threads and Samantha's voice needs the main thread — the command itself is always answered out loud ("I'm on it", then the downloading clip), and the progress words stay on the status line.

## "I'm on it" — and She Keeps Listening

When you ask Samantha to do work — search for a show, download one, play a channel, list your shows, read the guide — she answers "I'm on it" in her own voice right away, so you know she heard you and is working on it. The answer itself waits until "I'm on it" has finished: the old code started the answer in the same breath, so the two talked over each other. Quick replies (how you are doing, "can you hear me", your name, play/pause, skipping) answer directly instead.

After a Ctrl+Shift+B turn, she stops listening — one press, one command, then she is done, and the show keeps playing. Press B again for the next command. In wake-word mode (Ctrl+Shift+W) she keeps listening for her name, so you can say "Samantha" again for the next command without pressing anything. If you say nothing, she stops quietly instead of repeating "Excuse me". Press Ctrl+Shift+W again to turn wake-word mode off.

## NVDA Quiet — the Toggle, Made Robust

NVDA must not talk at all while you are in Audio Vault TV. The app presses NVDA+Shift+S (sleep mode) when it opens and again when it closes, so NVDA talks again outside the app. Ctrl+Shift+Q turns it on and off by hand.

Why it did not work before: the app always pressed Insert+Shift+S, but that only works when your NVDA key is Insert (desktop keyboard layout). With the laptop layout your NVDA key is CapsLock, so that keypress did nothing at all and NVDA kept reading everything. The app now reads NVDA's own settings file (%APPDATA%\nvda\nvda.ini) to find which key your NVDA uses — CapsLock for laptop layout, Insert or Numpad Insert for desktop — and presses the right one. It also only presses the key once the app window is actually focused, retries if it is not, and tries again when you come back to the window.

One honest limit, now fixed: the show list, the TV guide, and the "you have it / you don't have it" answers used to be read by NVDA's voice, because Samantha's voice is recordings and a recording cannot read show names she never recorded. They are now read by Samantha's reading voice instead (see "Samantha Reads the List Herself" above), and NVDA never reads the list at all — if the reading voice is not ready yet, Samantha says so herself in her own voice. Microsoft's voice is gone entirely.

When you choose one — "play Friends", "watch Classic Doctor Who" — she tells you plainly if you have it or not: "You have Friends. Now playing: Friends." or "You don't have a channel called ... , so I didn't change anything."

## Wake Chimes — Start Once, Then End Once, Separate

When Samantha starts listening — Ctrl+Shift+B or Ctrl+Shift+W — the start of request sound plays once (sounds/start_of_request.wav, one long high C), then the end of request sound plays once (sounds/end_of_request.wav, medium G to medium C). Each one plays once only, and they play separately, never at the same time: the high chime lasts about 5 seconds, so the low chime waits until the high chime has finished, plus a short quiet gap, before it plays. The low chime is also the end-of-request sound, so it is not played again at the end of each request — that was why it sounded twice. In wake-word mode the listening session stays open for many commands, so the low chime still only plays that one time, until you stop wake-word mode and start it again. After a Ctrl+Shift+B turn the microphone only opens once the chimes AND Samantha's own "I'm listening" have finished, so her own voice is never heard back as a command. A B turn lasts 20 seconds; in wake-word mode you have 15 seconds after you say her name — the chimes do not cut you off; you still have plenty of time to speak. The chimes were also levelled so they play at a steadier volume, same length as before. The start bell no longer rings twice when you call Samantha — it rings once when wake-word mode starts, and then Samantha just answers "Yes?" in her own voice.

## Live TV by Voice

Samantha can play live channels, like Game Show Network and other channels. Live TV streams over the internet, so it does not need your external drive.

| Say This | Action |
|----------|--------|
| "play Game Show Network live" | Play the Game Show Network live channel |
| "play live channel Game Show Network" | Play the Game Show Network live channel |
| "play live TV" | Play a favourite live channel first, otherwise the first live channel |
| "search live channels for Game Show Network" | Search live channels and show the list to pick from |
| "search live for Game Show Network" | Search live channels for Game Show Network |
| "search for Game Show Network live" | Search live channels for Game Show Network |
| "search for live shows" | Show the live channels to pick from |
| "stop live TV" | Stop the live stream |

A plain show search does live shows too, as well as AudioVault search and download: "search for Close Enough" searches AudioVault, and if a live channel has the same name Samantha speaks it first, so you can say "play Game Show Network live" to watch it live.

## TV Guide - What Is Coming Up Next

Samantha reads the whole TV guide: what is playing now, what comes up next in this channel, and what channel comes after this one. She says "Here's what's coming up next!" in her own recorded voice first, then the guide itself is read in the app's usual speaking voice, because Samantha's voice is recordings and she cannot read new show names she never recorded. When one show finishes and the next one starts, she also says what is coming up after that one, without you asking — in one smooth announcement, not three separate bits: what is playing now, then the marathon, then what comes up next. The guide also names marathons coming up on your other channels, for example a marathon of Classic Doctor Who, Two and a Half Men, Friends, or Frasier, not only a marathon on the channel playing right now. Live TV has no programme schedule, only channel names, so the live guide names the live channel now and the next live channels after it.

The guide only ever says clean show names, in plain words — never a file path, a backslash, a drive letter, or ".mp3", and never a file code like S01E02. For example, while Classic Doctor Who is playing: "Now playing Classic Doctor Who, season 1, episode 1, An Unearthly Child. Coming up next: season 1, episode 2, The Daleks. After that, the next channel is Friends." When the next episode is the same show, she says the show name once, not twice — "episode 2, The Daleks" — and when it is a different show she names it. The same goes for the list of shows, and for "Playing", "Paused", "Next file" and "Coming up next" announcements: only show names and episode numbers in words, never where the file lives on the computer.

| Say This | Action |
|----------|--------|
| "what's coming up next" | Read the whole TV guide |
| "what is next" | Read the whole TV guide |
| "give me the TV guide" | Read the whole TV guide |
| "tell me what's coming up next" | Read the whole TV guide |

You can also open it from the Controls menu, "What's Coming Up Next", Ctrl+Shift+G.

## Voice Downloads Make Their Own Channel

When Samantha searches for a show and downloads it - from AudioVault.net or from YouTube - she also makes a channel for it by herself, with no pop-up question. The channel is named after the show, and it holds the folders the files downloaded into. If a channel with that name already exists, the new files are added to it; nothing is ever replaced or deleted. When the download finishes she says so, for example "Channel Young Sheldon created, with 2 folders." Say "Samantha, get Young Sheldon Who Wants to Be a Millionaire on YouTube" and, after the download, the Young Sheldon channel is there ready to play.

## Game Show Network Guide

| Say This | Action |
|----------|--------|
| "what's coming up next on Game Show Network" | Read the Game Show Network guide: the live channel now and the live channels coming up after it |
| "give me the Game Show Network guide" | Same as above |

Live TV has no programme schedule in its catalogue, only channel names, so this guide cannot name the actual game shows playing on Game Show Network. A free programme guide does exist for many channels from iptv-org, but it is not wired into Audio Vault TV yet.

## Marathon Starting

A marathon is three or more episodes of the same show in a row in one of your channels. When one is coming up, the TV guide folds it into the coming-up-next sentence: "Coming up next is a marathon of Doctor Who, starting with season 1, episode 2, The Daleks." And when a marathon starts playing, the announcement says so in the same breath: "Now playing Doctor Who, season 1, episode 1. It's a marathon, so it will keep playing through the whole series. Coming up next is season 1, episode 2." For live TV, marathons cannot be seen, because the live catalogue has no programme listings.

## Fix Shows That Are Mixed Up

If shows you already have are in the wrong channel - Odd Squad playing on the Doctor Who channel, for example - Samantha can sort them out. She takes a file out of a channel it does not belong to, and moves it to the channel it does belong to when there is one. She never deletes the file itself from your computer.

| Say This | Action |
|----------|--------|
| "fix the mixed up shows" | Check every channel and take mixed-up files out of the wrong ones |
| "unmix my shows" | Same as above |
| "my shows are mixed up" | Same as above |

## Delete a Channel's Downloads

If a channel's downloads are wrong or you do not like them — for example "A Killer Among Friends", the wrong Friends download — Samantha can get rid of them. She asks Yes or No first, so nothing is deleted by accident. Only that channel's own downloaded files are deleted, never a whole shared folder, and the channel is removed so it stops coming up.

| Say This | Action |
|----------|--------|
| "delete the show" | Delete the show playing right now, and remove its channel |
| "delete this show" | Delete the show playing right now, and remove its channel |
| "delete Friends" | Delete the Friends show and remove its channel |
| "delete A Killer Among Friends downloads" | Delete its downloaded files and remove the channel |
| "delete Friends downloads" | Delete that channel's downloaded files and remove the channel |

When you tell Samantha by voice to delete a show, she deletes it right away and then tells you what she removed. The menu version still asks Yes or No first.

You can also do this from the menu: Channels, then "Delete Channel and Downloads" (Ctrl+Shift+D) for the current channel.

## Available Voice Commands

### Playback Control
| Say This | Action |
|----------|--------|
| "play" | Play or resume playback |
| "pause" | Pause playback |
| "stop" | Pause playback |
| "resume" | Resume playback |

### File Navigation
| Say This | Action |
|----------|--------|
| "next file" | Go to next file |
| "next track" | Go to next file |
| "previous file" | Go to previous file |
| "previous track" | Go to previous file |
| "last file" | Go to previous file |

### Folder Navigation
| Say This | Action |
|----------|--------|
| "next folder" | Go to next folder |
| "next season" | Go to next folder |
| "previous folder" | Go to previous folder |
| "previous season" | Go to previous folder |
| "last folder" | Go to previous folder |

### Channel Switching
| Say This | Action |
|----------|--------|
| "next channel" | Switch to next channel |
| "previous channel" | Switch to previous channel |
| "last channel" | Switch to previous channel |

### Seek Controls
| Say This | Action |
|----------|--------|
| "rewind" | Rewind 10 seconds |
| "go back" | Rewind 10 seconds |
| "back" | Rewind 10 seconds |
| "forward" | Fast forward 10 seconds |
| "skip" | Fast forward 10 seconds |
| "fast forward" | Fast forward 10 seconds |

### Reading Voice — Install and Diagnose
| Say This | Action |
|----------|--------|
| "install my reading voice" | Get Samantha's reading voice ready now ("I'm on it", then she says when it is ready) |
| "install everything I need" | Get every library the app needs, one at a time, in the background |
| "why is my reading voice not ready" | Samantha tells you the plain reason the last try failed, and what state the voice is in |
| "what happened to my reading voice" | Same as above |

### Listening — Install and Diagnose
| Say This | Action |
|----------|--------|
| "install the listening model" | Get Samantha listening now ("I'm on it", then "I can hear you now" when the model is ready) |
| "get Samantha listening" | Same as above |
| "make Samantha listen" | Same as above |
| "can you hear me" | Samantha answers "Yes, I can hear you" — only when listening is really working; otherwise she says she cannot hear yet, and why |
| "why can't you hear me" | Samantha tells you whether she can hear, and if not, why (model installing / missing / failed) |
| "why can you not hear me" | Same as above |

### Search and Download on AudioVault.net
| Say This | Action |
|----------|--------|
| "search for Friends the sitcom new description" | Search AudioVault.net for Friends, and show only the actual Friends sitcom, Season 1, US New Description — not every title containing the word, like "A Killer Among Friends" |
| "search for a TV show Close Enough" | Search AudioVault.net for that TV show, and speak the first few results |
| "download Friends" | Search AudioVault and download the exact Friends show, Season 1 New Description, in the background — this exact-match pick works for every show you mention, not just Friends |
| "find a TV show Chicago Party Aunt" | Search AudioVault.net for that TV show |
| "search for a movie Ghostbusters" | Search AudioVault.net for that movie |
| "search audiovault for Close Enough" | Search AudioVault.net for that show |
| "download Close Enough" | Search AudioVault.net and download the top result in the background, with no list to pick from |
| "download a TV show Close Enough season 2" | Download the top result for that show and season |
| "search and download Close Enough" | Search AudioVault.net and download the top result |
| "download it" | After a search, download the first result from that search |
| "download status" | Hear what is downloading in the background |
| "cancel downloads" | Stop any downloads running in the background |

### Search and Download on YouTube
| Say This | Action |
|----------|--------|
| "search YouTube for Close Enough" | Search YouTube for that show or video, and speak the first few results |
| "search for Close Enough on YouTube" | Search YouTube for that show or video |
| "find a movie Ghostbusters on YouTube" | Search YouTube for that movie |
| "download Close Enough from YouTube" | Search YouTube and download the top result in the background, with no list to pick from |
| "download from YouTube Close Enough" | Download the top YouTube result for that show |
| "search and download Close Enough on YouTube" | Search YouTube and download the top result |
| "download it" | After a YouTube search, download the first result from that search |
| "download status" | Hear what is downloading in the background |
| "cancel downloads" | Stop any downloads running in the background |

YouTube downloads save as MP3 audio in your YouTube download folder. Saying "download it" always downloads from your last search — YouTube if that search was on YouTube, AudioVault if it was on AudioVault.

Saying "Samantha, play" in one breath works too — the words after "Samantha" are kept as the command, instead of being thrown away.

## Tips for Best Recognition

- **Wake Word Mode**: Say "Samantha" clearly, pause briefly, then give your command
- Speak clearly and at normal volume
- Use short, simple commands
- If a command isn't recognized, try rephrasing it
- Playback commands work offline - no internet required. Searching and downloading on AudioVault.net and YouTube need internet.
- Wake word mode runs continuously in the background

## Examples

**One-Time Mode:**
1. Press Ctrl+Shift+B
2. Say "play"
3. Done

**Wake Word Mode:**
1. Press Ctrl+Shift+W once to activate
2. Say "Samantha, play"
3. Say "Samantha, next file"
4. Say "Samantha, next channel"
5. Press Ctrl+Shift+W to deactivate when done

## Technical Details

- **Recognition Engine**: Vosk (offline speech recognition)
- **Model**: vosk-model-small-en-us-0.15
- **Wake Word**: "Samantha"
- **One-Time Listening Duration**: 20 seconds per activation
- **Wake Word Command Duration**: 15 seconds after "Samantha" is detected
- **Pause Grace**: keeps listening for 4 seconds after the first words, so a pause does not cut a command off
- **Language**: English (US)

## Coming Soon

- Custom wake word option
- Voice feedback for all actions

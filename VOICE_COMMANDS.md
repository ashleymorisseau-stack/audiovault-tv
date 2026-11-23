# Voice Commands Reference

## Two Modes of Voice Control

### Mode 1: One-Time Command (Ctrl+Shift+B)
1. Press **Ctrl+Shift+B** to start listening
2. Speak your command clearly within 10 seconds
3. The app will recognize and execute the command
4. Press **Ctrl+Shift+B** again to stop listening early

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

When she knows your name, Samantha greets you with it when she hears her wake word — "Hi Honey, I'm listening" — instead of just "Listening...". You can also set or change your name from the menu, without voice.

## Samantha's Own Voice

Samantha now speaks in her own recorded voice, not just NVDA. Her voice is friendly, excited but not yelling, and a little louder than the first recording.

- When Samantha hears her wake word, she asks in her own voice: "What do you want to watch?"
- When you ask "what is your name", she answers in her own voice: "Hi, my name is Samantha. What is your name?"
- Her voice files are in the sounds folder: samantha_greeting.wav (3.4 seconds) and samantha_what_to_watch.wav (1.6 seconds).

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

## Delete a Channel's Downloads

If a channel's downloads are wrong or you do not like them — for example "A Killer Among Friends", the wrong Friends download — Samantha can get rid of them. She asks Yes or No first, so nothing is deleted by accident. Only that channel's own downloaded files are deleted, never a whole shared folder, and the channel is removed so it stops coming up.

| Say This | Action |
|----------|--------|
| "delete A Killer Among Friends downloads" | Ask first, then delete its downloaded files and remove the channel |
| "delete Friends downloads" | Ask first, then delete that channel's downloaded files and remove the channel |

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

### Search and Download on AudioVault.net
| Say This | Action |
|----------|--------|
| "search for Friends the sitcom new description" | Search AudioVault.net for Friends, and pick the exact Friends sitcom, Season 1, US New Description — not the first title containing the word, like "A Killer Among Friends" |
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
- **One-Time Listening Duration**: 10 seconds per activation
- **Wake Word Command Duration**: 8 seconds after "Samantha" is detected
- **Language**: English (US)

## Coming Soon

- Custom wake word option
- Voice feedback for all actions

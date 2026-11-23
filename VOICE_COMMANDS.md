# Voice Commands Reference

## Two Modes of Voice Control

### Mode 1: One-Time Command (Ctrl+Shift+B)
1. Press **Ctrl+Shift+B** to start listening
2. Speak your command clearly within 20 seconds. It keeps listening through a short pause, so you do not have to rush.
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

## TV Guide - What Is Coming Up Next

Samantha reads the whole TV guide: what is playing now, what comes up next in this channel, and what channel comes after this one. She says "Here's what's coming up next!" in her own recorded voice first, then the guide itself is read in the app's usual speaking voice, because Samantha's voice is recordings and she cannot read new show names she never recorded. When one show finishes and the next one starts, she also says what is coming up after that one, without you asking. Live TV has no programme schedule, only channel names, so the live guide names the live channel now and the next live channels after it.

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

A marathon is three or more episodes of the same show in a row in one of your channels. When one is coming up, the TV guide says so: "A marathon of Doctor Who is coming up next." And when a marathon starts playing, Samantha says so right then: "A marathon of Doctor Who is starting." For live TV, marathons cannot be seen, because the live catalogue has no programme listings.

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
- **Pause Grace**: keeps listening for 2.5 seconds after the first words, so a pause does not cut a command off
- **Language**: English (US)

## Coming Soon

- Custom wake word option
- Voice feedback for all actions

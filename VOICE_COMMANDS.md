# Voice Commands Reference

## Two Modes of Voice Control

### Mode 1: One-Time Command (Ctrl+Shift+B)
1. Press **Ctrl+Shift+B** to start listening
2. Speak your command clearly within 10 seconds
3. The app will recognize and execute the command
4. Press **Ctrl+Shift+B** again to stop listening early

### Mode 2: Wake Word Mode (Ctrl+Shift+W) - Recommended
1. Press **Ctrl+Shift+W** to activate continuous listening
2. Say **"Sam"** followed by your command
3. Example: "Sam, play" or "Sam, next file"
4. The app stays in listening mode until you press **Ctrl+Shift+W** again
5. NVDA announces "Listening..." when wake word is detected

**Wake Word Mode is hands-free** - no need to press any keys once activated!

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
| "search for a TV show Close Enough" | Search AudioVault.net for that TV show, and speak the first few results |
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

Saying "Sam, play" in one breath works too — the words after "Sam" are kept as the command, instead of being thrown away.

## Tips for Best Recognition

- **Wake Word Mode**: Say "Sam" clearly, pause briefly, then give your command
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
2. Say "Sam, play"
3. Say "Sam, next file"
4. Say "Sam, next channel"
5. Press Ctrl+Shift+W to deactivate when done

## Technical Details

- **Recognition Engine**: Vosk (offline speech recognition)
- **Model**: vosk-model-small-en-us-0.15
- **Wake Word**: "Sam"
- **One-Time Listening Duration**: 10 seconds per activation
- **Wake Word Command Duration**: 8 seconds after "Sam" is detected
- **Language**: English (US)

## Coming Soon

- Custom wake word option
- Voice feedback for all actions

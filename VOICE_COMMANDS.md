# Voice Commands Reference

## Two Modes of Voice Control

### Mode 1: One-Time Command (Ctrl+Shift+B)
1. Press **Ctrl+Shift+B** to start listening
2. Speak your command clearly within 5 seconds
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

## Tips for Best Recognition

- **Wake Word Mode**: Say "Sam" clearly, pause briefly, then give your command
- Speak clearly and at normal volume
- Use short, simple commands
- If a command isn't recognized, try rephrasing it
- Commands work offline - no internet required
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
- **One-Time Listening Duration**: 5 seconds per activation
- **Wake Word Command Duration**: 3 seconds after "Sam" is detected
- **Language**: English (US)

## Coming Soon

- More natural language variations
- Custom wake word option
- Voice feedback for all actions

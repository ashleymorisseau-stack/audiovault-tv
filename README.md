# MP3 Folder Player

An accessible MP3 player designed for NVDA screen reader users. Play audio files from multiple folders in natural numeric order with full keyboard navigation and automatic bookmarking.

## Features

- **Channels**: Save multiple folder configurations as channels and switch between them instantly
- **Multi-folder playback**: Select multiple folders and play all MP3 files in natural order
- **Natural sorting**: Handles numeric ordering correctly (Episode 1, 2, 3... 10, 11, not 1, 10, 11, 2)
- **NVDA accessible**: Full screen reader support with wxPython
- **Keyboard navigation**: Complete control without mouse
- **Auto-bookmark**: Each channel automatically saves and resumes your position
- **Auto-advance**: Automatically plays next file when current finishes

## Installation

1. Install Python 3.7 or higher
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the player:
```bash
python main.py
```

### First Time Setup

1. Press Ctrl+T to create a new channel (e.g., "Breaking Bad")
2. Press Ctrl+O to select folders containing MP3 files
3. When prompted, add more folders or select "No"
4. Press Space to start playback

### Keyboard Shortcuts

#### Playback Controls
| Key | Action |
|-----|--------|
| **Space** | Play/Pause |
| **Left Arrow** | Previous file |
| **Right Arrow** | Next file |
| **Ctrl + Left** | Previous folder |
| **Ctrl + Right** | Next folder |
| **Shift + Left** | Rewind 10 seconds |
| **Shift + Right** | Fast forward 10 seconds |
| **Ctrl + S** | Set bookmark at current position |
| **Ctrl + J** | Jump to bookmark |

#### Channel Management
| Key | Action |
|-----|--------|
| **Ctrl + T** | Create new channel |
| **Ctrl + R** | Rename current channel |
| **Ctrl + D** | Delete current channel |
| **Ctrl + L** | List all channels |
| **Ctrl + Tab** | Next channel |
| **Ctrl + Shift + Tab** | Previous channel |

#### File Operations
| Key | Action |
|-----|--------|
| **Ctrl + O** | Select folders for current channel |
| **Ctrl + Q** | Quit application |

## How It Works

### Folder Organization Example

```
AudioBooks/
├── Season 1/
│   ├── Episode 1.mp3
│   ├── Episode 2.mp3
│   └── Episode 3.mp3
├── Season 2/
│   ├── Episode 1.mp3
│   └── Episode 2.mp3
└── Season 3/
    └── Episode 1.mp3
```

If you select all three season folders, the player will:
1. Play all files in Season 1 (in order)
2. Automatically continue to Season 2
3. Then Season 3
4. All files within each folder play in natural numeric order

### Bookmarking

The player has two types of bookmarks:

#### Automatic Position Saving
The player automatically saves your position for each channel when you close it:
- Which folders you selected
- Which file you were on
- Exact playback position in that file

Next time you open the player, it resumes exactly where you left off.

#### Manual Bookmarks
Create named bookmarks to mark specific moments you want to return to:
- Press **Ctrl+S** to save a bookmark at the current position
- Press **Ctrl+J** to view and jump to saved bookmarks
- Each channel can have up to 20 named bookmarks
- Bookmarks show the file name and timestamp
- You can overwrite existing bookmarks or delete them from the jump dialog

Example: Mark "Favorite scene" in Episode 5, then jump back to it anytime from Episode 10.

Channels file location: `~/.mp3_player_channels.json`

### Channels

Channels let you save different folder configurations. For example:
- Channel "Breaking Bad" with Season 1-5 folders
- Channel "Podcasts" with different podcast folders
- Channel "Audiobooks" with book folders

Switch between channels instantly without re-selecting folders. Each channel remembers its own playback position independently.

## Project Structure

```
AudioFolders/
├── main.py                 # Main application with UI
├── audio_player.py         # Audio playback engine
├── playlist_manager.py     # Folder and file management
├── channel_manager.py      # Channel management
├── requirements.txt        # Python dependencies
├── README.md              # This file
└── IMPLEMENTATION_PLAN.md # Development plan
```

## Accessibility Notes

- All UI elements have proper labels for screen readers
- Status updates are announced via wx.StaticText
- Keyboard-first design - no mouse required
- Tested for NVDA compatibility

## Troubleshooting

**No sound playing:**
- Ensure your MP3 files are valid
- Check system volume settings
- Verify pygame.mixer is properly installed

**Folders not loading:**
- Ensure folders contain .mp3 files
- Check folder permissions

**Bookmark not working:**
- Ensure you have write permissions to your home directory
- Check `~/.mp3_player_channels.json` exists after closing
- Each channel saves its own position independently

## Requirements

- Python 3.7+
- wxPython 4.2.0+
- pygame 2.5.0+
- Windows/Linux/macOS

## License

Free to use and modify for personal or commercial purposes.

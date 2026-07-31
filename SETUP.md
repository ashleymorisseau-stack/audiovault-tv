# MP3 Folder Player - Setup Guide

## Quick Start

### Step 1: Get the Program Files
Run the updater to download all program files:
```cmd
python update.py
```

### Step 2: Install Python Dependencies
```cmd
pip install -r requirements.txt
```

### Step 3: Download Vosk Model (Required for Voice Control)
Voice control requires the Vosk speech recognition model:

1. Go to: https://alphacephei.com/vosk/models
2. Download **vosk-model-small-en-us-0.15** (40MB)
3. Extract the ZIP file
4. Place the extracted folder in the same directory as main.py
5. The folder should be named: `vosk-model-small-en-us-0.15`

**Your folder structure should look like:**
```
AudioFolders/
├── main.py
├── audio_player.py
├── voice_control.py
├── vosk-model-small-en-us-0.15/    ← Vosk model here
│   ├── am/
│   ├── conf/
│   ├── graph/
│   └── ...
└── requirements.txt
```

### Step 4: Run the Program
```cmd
python main.py
```

## Voice Control Setup

If you skip the Vosk model download, the program will still work but voice control features will be disabled.

To enable voice control:
- Download the model as described in Step 3
- Restart the program
- Press **Ctrl+Shift+B** for one-time commands
- Press **Ctrl+Shift+W** for wake word mode ("Sam")

## Updating the Program

To get the latest version:
```cmd
python update.py
```

This will download any updated files from S3. Your channels and bookmarks are saved locally and won't be affected.

## Troubleshooting

**Voice control not working:**
- Make sure the vosk-model folder is in the correct location
- Check that the folder name is exactly: `vosk-model-small-en-us-0.15`
- Verify vosk and sounddevice are installed: `pip install vosk sounddevice`

**Program won't start:**
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Check Python version: Python 3.7 or higher required

**No sound:**
- Check system volume
- Verify MP3 files are valid
- Try a different MP3 file

## First Time Use

1. Press **Ctrl+T** to create your first channel
2. Press **Ctrl+O** to select folders with MP3 files
3. Press **Space** to start playing
4. See README.md for all keyboard shortcuts

## Files Not Included in Updates

These files are stored locally and won't be overwritten by updates:
- `.mp3_player_channels.json` - Your channels and bookmarks
- `vosk-model-small-en-us-0.15/` - Vosk model (download separately)

# AudioVault Integration - Implementation Plan

## Overview
Integrate the AudioVault downloader into the MP3 Folder Player GUI, allowing users to search, download, extract, and automatically create channels for audio described movies and TV shows.

## Phase 1 - Basic Download Integration

### 1.1 AudioVault Module
- [x] Create `audiovault_client.py` - refactored version of CLI tool for GUI use
- [x] Login function with credential saving (config.ini)
- [x] Search function (movies and shows)
- [x] Get recents function
- [x] Download function with progress callback (for UI updates)

### 1.2 Login UI
- [x] Login dialog (email + password fields)
- [x] "Remember me" checkbox to save credentials
- [x] Login status indicator in main window
- [x] Auto-login on startup if credentials saved

### 1.3 Search & Browse UI
- [x] Add "AudioVault" menu to menu bar
- [x] Search dialog with text input and movie/show toggle
- [x] Results list dialog with selection
- [x] "View Recent Movies" and "View Recent Shows" menu items

### 1.4 Download UI
- [x] Download progress dialog with NVDA announcements
- [x] Configurable download folder (default: ~/AudioVault/)
- [x] Download status in main window
- [x] Cancel download support

## Phase 2 - ZIP Support & Extraction

### 2.1 ZIP Handling
- [x] Detect if downloaded file is a ZIP
- [x] Auto-extract ZIP to appropriate folder
- [x] Extract to show-name/season subfolder structure
- [x] Clean up ZIP after extraction
- [x] Handle nested ZIPs if needed

### 2.2 File Organization
- [x] Create folder structure: Downloads/[ShowName]/
- [x] Organize by season if applicable
- [x] Natural sort extracted files

## Phase 3 - Auto Channel Creation

### 3.1 Channel Integration
- [x] After download/extract, prompt to create channel
- [x] Auto-name channel from subfolder name
- [x] Auto-set folders from download location
- [x] Option to add to existing channel instead
- [ ] Auto-name channel from show/movie name
- [ ] Auto-set folders from download location
- [ ] Option to add to existing channel instead

### 3.2 Smart Channel Management
- [ ] Detect new episodes added to existing channel folders
- [ ] Notify user of new content available
- [ ] Option to re-download/update channel content

## Phase 4 - Library Management

### 4.1 Downloaded Content Browser
- [ ] View all downloaded content
- [ ] Delete downloaded files/folders
- [ ] Re-download option
- [ ] Storage usage display

### 4.2 Keyboard Shortcuts
- [ ] Ctrl+Shift+F - Search AudioVault
- [ ] Ctrl+Shift+R - View recent additions
- [ ] Ctrl+Shift+D - View downloads

## Dependencies
- requests
- bs4 (BeautifulSoup)
- zipfile (built-in Python)

## Progress Tracking
- Start Date: 2026-03-24
- Current Phase: Planning Complete
- Next Step: Phase 1.1 - Create audiovault_client.py

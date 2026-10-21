# 📖 Complete Video Scheduling Automation — Comprehensive User Guide

Welcome to the definitive user and operational guide for **Video Scheduling Automation (Creator Studio)**, created and developed by **Parth Wagh**. This guide covers everything from initial system setup, video processing, and Excel metadata synchronization to automated multi-platform browser publishing across YouTube Studio, Instagram Reels, and Facebook Professional Dashboard.

---

## 📑 Table of Contents

1. [System Overview & High-Level Architecture](#1-system-overview--high-level-architecture)
2. [Directory Structure & Naming Conventions](#2-directory-structure--naming-conventions)
3. [Prerequisites & First-Time Installation](#3-prerequisites--first-time-installation)
4. [Launching the Application (GUI & CLI)](#4-launching-the-application-gui--cli)
5. [Connecting Creator Accounts (Persistent Browser Profile)](#5-connecting-creator-accounts-persistent-browser-profile)
6. [Video Processing, Outro Concatenation & Thumbnails](#6-video-processing-outro-concatenation--thumbnails)
7. [Excel Metadata & SEO Synchronization](#7-excel-metadata--seo-synchronization)
8. [Publishing Calendar, Rescheduling & Schedule Realignment](#8-publishing-calendar-rescheduling--schedule-realignment)
9. [Publishing Engine, Execution Modes & Queue Management](#9-publishing-engine-execution-modes--queue-management)
10. [Auto-Healer, Self-Recovery & Unattended Study Mode](#10-auto-healer-self-recovery--unattended-study-mode)
11. [Settings & Customization](#11-settings--customization)
12. [Troubleshooting & Frequently Asked Questions](#12-troubleshooting--frequently-asked-questions)
13. [CLI Command Reference](#13-cli-command-reference)

---

## 1. System Overview & High-Level Architecture

Video Scheduling Automation is an end-to-end desktop automation system designed to eliminate repetitive manual social media posting for short-form video creators (YouTube Shorts, Instagram Reels, Facebook Reels).

```
   ┌──────────────────┐       ┌─────────────────┐
   │   start video/   │       │   End Video/    │
   │  (Raw MP4 clips) │       │  (Outro video)  │
   └────────┬─────────┘       └────────┬────────┘
            │                          │
            └───────────┬──────────────┘
                        ▼
       ┌─────────────────────────────────┐
       │     FFmpeg Processing Engine    │
       │  • Alternating / Manual Outros  │
       │  • 0.0s Opening Frame Thumbnail │
       └────────────────┬────────────────┘
                        ▼
   ┌──────────────────────────────────────────────┐
   │       Excel SEO Workbook Synchronization     │
   │  • 500-word YouTube SEO Descriptions         │
   │  • 200-word IG/FB Captions & Hashtags        │
   │  • Automatic Timestamped Backups             │
   └────────────────────┬─────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────┐
   │        SQLite Database & Queue Engine        │
   │  • 3 Daily Time Slots (08:30, 18:00, 21:00)  │
   │  • 9 Videos/Day Platform Upload Cap          │
   └────────────────────┬─────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────┐
   │     Playwright Native Browser Automation     │
   │  • Persistent Chrome Profile (No Bot Flag)   │
   │  • YouTube Studio  • Instagram  • Facebook   │
   └──────────────────────────────────────────────┘
```

### Core Architecture Highlights
- **No Third-Party Cloud APIs Required**: Publishes directly through native web interfaces using your authenticated Google Chrome session, bypassing third-party API rate limits and developer app restrictions.
- **Strict Anti-Bot Pacing**: Employs human-like delays, natural keystrokes, and bezier mouse trajectories to avoid platform automated activity triggers.
- **Bi-Directional Synchronization**: Reflects scheduled publication times, live YouTube URLs, and publication status changes back to your central Excel workbook and SQLite database simultaneously.

---

## 2. Directory Structure & Naming Conventions

### Project Layout
```
Video Scheduling/
├── start video/                     # Raw incoming vertical videos (.mp4)
├── End Video/                       # Outro call-to-action video (e.g., End Video.mp4)
├── YouTube_SEO_61_Videos...xlsx     # Primary Excel SEO metadata workbook
├── output/
│   ├── processed/                   # Concatenated videos with outros appended
│   └── thumbnails/                  # Extracted 0.0s opening frame thumbnails
├── backups/                         # Automatic timestamped Excel backups before any write
├── browser_profile/                 # Persistent Chrome cookies, sessions, and cache
├── config/
│   └── settings.py                  # Default system configuration and paths
├── user_settings.json               # Active user-defined overrides (slots, caps, paths)
├── video_scheduler.db               # SQLite database tracking jobs, logs, and queue state
├── app/                             # Core Python modules (dashboard, video, scheduler, browser)
├── launch_gui.py                    # One-click GUI launcher with auto-port freeing
└── run.py                           # CLI automation runner
```

### Video File Naming Rules
1. **Title Case with Underscores**: Name videos with meaningful descriptive words:
   - ✅ `A_Moment_To_Reflect_On_Life_And_Success.mp4`
   - ✅ `Master_The_Art_Of_Quiet_Influence.mp4`
   - ❌ `VID_20261020_001.mp4`
   - ❌ `final_v2_edit.mp4`
2. **Exact 1:1 Excel Match**: The filename on disk must exactly match the value in Column A (`Video File Name`) of the Excel workbook.
3. **Format**: Vertical format (`1080x1920`, 9:16 aspect ratio), H.264 video codec, AAC audio codec, 30 or 60 fps.

---

## 3. Prerequisites & First-Time Installation

### Minimum Requirements
- **Operating System**: Windows 10/11, macOS, or modern Linux.
- **Python**: Version `3.10` or higher (Python `3.13` verified).
- **FFmpeg & FFprobe**: Installed and added to system `PATH` (e.g. `C:\Tools\ffmpeg\bin`).
- **Google Chrome**: Stable version installed.

### Step-by-Step Installation

1. **Clone or Download Workspace**:
   ```bash
   cd "H:\google antigravity\Video Scheduling"
   ```

2. **Install Python Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Install Playwright Browsers**:
   ```bash
   playwright install chromium
   ```

4. **Verify FFmpeg Installation**:
   ```bash
   ffmpeg -version
   ffprobe -version
   ```

5. **Initialize Database**:
   ```bash
   python -c "from app.database.models import init_db; init_db()"
   ```

---

## 4. Launching the Application (GUI & CLI)

### Option A: Launching the Web GUI (Recommended)
Double-click `START_GUI.bat` or run from PowerShell:
```bash
python launch_gui.py
```
- **Port Management**: The launcher checks port `8899`. If a orphaned background task is holding the port, it automatically frees it.
- **Browser Auto-Launch**: Your default web browser will automatically open to `http://127.0.0.1:8899`.

### Option B: Command-Line Interface (CLI)
You can execute tasks headlessly without opening the browser dashboard:
```bash
# Scan media files
python run.py scan

# Check and sync Excel metadata
python run.py sync

# Process videos and append outros
python run.py process --rule every_second

# Generate scheduling queue
python run.py schedule

# Run automated publishing (dry-run or live)
python run.py publish --limit 3 --dry-run
python run.py publish --platform youtube --limit 1
```

---

## 5. Connecting Creator Accounts (Persistent Browser Profile)

The publishing engine uses a persistent Chrome profile located at [`browser_profile/`](file:///h:/google%20antigravity/Video%20Scheduling/browser_profile). This preserves your login cookies so you do **not** need to enter credentials or complete 2FA during automated uploads.

### How to Authenticate:
1. Open the Web Dashboard and click **"🔗 Connections"** in the sidebar.
2. Click **"🌐 Open Browser for Login"**.
3. A dedicated Chrome window opens pointing to:
   - **YouTube Studio** (`studio.youtube.com`)
   - **Instagram Web** (`instagram.com`)
   - **Facebook Creator / Professional Dashboard** (`facebook.com`)
4. Log into each account and check "Remember Me". Complete any two-factor authentication (2FA) prompts.
5. Once logged in, click **"✅ Close Browser & Save Session"** in the dashboard.
6. Click **"🔄 Check Auth Status"** to confirm all three platforms show `Active / Authenticated`.

> [!NOTE]
> Authentication sessions typically last 30 to 90 days. If a platform session expires, return to the **Connections** tab, click **Open Browser for Login**, re-authenticate, and close the browser.

---

## 6. Video Processing, Outro Concatenation & Thumbnails

The processing engine prepares raw videos for publication using FFmpeg.

### Outro Concatenation Rules
Navigate to **Settings &rarr; Video Processing & Outro Selection**:
- **Every Second (Alternating - Default)**: Appends the outro video to alternating videos (Index 0 gets outro, Index 1 gets no outro, Index 2 gets outro...).
- **Every Video**: Appends the outro video to 100% of discovered videos.
- **None**: Does not append any outro; retains original start video length.
- **Manual Selection**: Activates an interactive video checklist allowing you to pick precisely which specific videos receive the outro. A live preview table indicates the exact sequence before rendering.

### Thumbnail Generation
- For YouTube Shorts and Reels, the thumbnail is automatically extracted from frame `0.0s` (the very first frame of the start video).
- Thumbnails are saved as high-resolution JPEGs in [`output/thumbnails/`](file:///h:/google%20antigravity/Video%20Scheduling/output/thumbnails).
- Thumbnails are automatically selected and uploaded during YouTube Studio automation.

---

## 7. Excel Metadata & SEO Synchronization

The application synchronizes with [`YouTube_SEO_61_Videos_500_Word_Descriptions_FILENAME_MATCHED.xlsx`](file:///h:/google%20antigravity/Video%20Scheduling/YouTube_SEO_61_Videos_500_Word_Descriptions_FILENAME_MATCHED.xlsx) in the project root.

### Excel Column Mapping
| Col # | Header Name | Function |
| :---: | :--- | :--- |
| **A (1)** | `Video File Name` | Matches `.mp4` filename on disk |
| **B (2)** | `SEO Title` | Title entered into YouTube, IG, and FB uploads |
| **C (3)** | `SEO Description + Hashtags` | 500-word keyword-optimized description for YouTube |
| **D (4)** | `Description Word Count` | Word count verification for SEO compliance |
| **E (5)** | `Status` | Current lifecycle state: `Pending`, `Scheduled`, or `Published` |
| **F (6)** | `Scheduled Date` | Date string in `YYYY-MM-DD` format |
| **G (7)** | `Scheduled Time` | Time string in `HH:MM` 24h format |
| **H (8)** | `YouTube URL` | Populated automatically with live watch URL upon upload |
| **I (9)** | `Uploaded At` | ISO timestamp recorded when upload completes |
| **J (10)** | `Instagram/Facebook Caption` | 200-word caption for social platforms |
| **K (11)** | `Caption Word Count` | Word count for caption tracking |

### Safe Sync with Backups
Whenever you click **"✅ Sync Workbook"** in the dashboard:
1. The engine creates a timestamped copy in [`backups/`](file:///h:/google%20antigravity/Video%20Scheduling/backups/) (e.g. `Excel_backup_before_sync_20261021_143000.xlsx`).
2. Scans `start video/` for any newly added videos.
3. Appends new rows to Excel with blank metadata ready for editing.
4. Preserves all formulas, row formats, and cell styles.

---

## 8. Publishing Calendar & Schedule Realignment

### Publishing Slots (IST)
The default publication schedule is tuned for Indian Standard Time (`Asia/Kolkata`):
- **Slot 1 (Morning)**: `08:30 IST`
- **Slot 2 (Evening Peak)**: `18:00 IST`
- **Slot 3 (Night Prime)**: `21:00 IST`

### Calendar Controls
In the **📅 Publishing Calendar** tab:
- **Visual Month View**: Displays all upcoming scheduled videos with color-coded platform pills (`YT`, `IG`, `FB`).
- **Click-to-Reschedule**: Click any video card to open the **Reschedule Modal**:
  - Change scheduled date and time with 1-click presets (`08:30`, `18:00`, `21:00`).
  - Optionally check **"Apply new date & time to all platforms"** to synchronize YouTube, Instagram, and Facebook together.
  - Reset status back to `Pending` if you deleted a draft on YouTube Studio and want the engine to re-upload it.

### Schedule Realignment
When you adjust publishing slots in **Settings** (e.g., changing `18:00` to `19:00` or adding a 4th slot):
- The engine automatically recalibrates all pending and future scheduled jobs.
- **Already published posts are strictly preserved** and will never be overwritten.

---

## 9. Publishing Engine, Execution Modes & Queue Management

### Queue Execution Bar
Navigate to **📤 Publishing Queue**:
1. **Target Platform**: Choose `All Platforms` or isolate `YouTube`, `Instagram`, or `Facebook`.
2. **Batch Limit**:
   - `Today (3 videos)`: Processes today's 3 scheduled slots.
   - `3 Days (9 videos)`: Publishes the maximum safe 3-day batch (9 videos per platform).
   - `All Pending`: Exhausts all pending queue jobs.
3. **Execution Controls**:
   - ☑ **"Open Browser Window (Headed)"**: Recommended. Keeps the Chrome window visible so you can supervise the upload process.
   - ☐ **"Dry Run Mode"**: Navigates the pages and verifies selectors without clicking the final "Publish" or "Schedule" button.
4. **Emergency Stop**: Click **"🛑 Stop Uploading"** to cleanly halt the browser engine between videos without corrupting database states.

### In-Flight Transient Error Recovery
Unlike brittle scripts that crash on the first selector timeout, the publisher features an automated transient retry loop:
- **Scrim & Modal Interception**: Dismisses modal scrim overlays with the `Escape` key.
- **Cooling Delays**: Automatically pauses 10 seconds to allow slow network streams to stabilize.
- **Auto-Retries**: Retries up to 3 times per job without failing the video or interrupting the rest of the queue.

---

## 10. Auto-Healer, Self-Recovery & Unattended Study Mode

The **Auto-Healer & Diagnostics System** (`#diagnostics`) is built specifically for autonomous, unattended workflows: **you click "Start Automation" in the morning, leave your PC scheduling, and go study with complete peace of mind.**

### The Unattended Morning Workflow
1. **Open GUI**: Launch the dashboard at `http://127.0.0.1:8899`.
2. **Pre-Flight Health Check**: Navigate to **"🩺 Auto-Healer & Issues"** and click **"🎓 Check Study Readiness"**.
   - Verifies 6 critical subsystems: Network Connectivity, Browser Session Cookies, Watchdog Loop, Daily Upload Cap, FFmpeg Engine, and SQLite Database integrity.
   - If green (100% Ready), your PC is primed for automated scheduling.
3. **Trigger Publishing**: Go to **Publishing Queue** and click **"⚡ Start Live Uploading"**.
4. **Walk Away to Study**:
   - Transient issues (DOM popups, YouTube modal scrims, temporary lag) are auto-resolved in flight.
   - PC sleep interruptions (>10 min stuck in `uploading`) are safely reset back to `pending`.
   - Quota exhaustion (e.g. YouTube 24h upload limit reached) shifts remaining videos to tomorrow's slots instead of crashing.
5. **Post-Study Review**:
   - If an unresolvable issue occurred (such as Instagram requiring a 2FA SMS code), a red notification badge appears on the sidebar.
   - The diagnosis explains the exact human step required.
   - 1-click action buttons (**[↺ Re-arm & Retry]**, **[📅 Shift Tomorrow]**, or **[🔓 Log In Now]**) let you resolve it instantly.

### Master Knowledge Matrix (7 Core Failure Modes)

| # | Failure Mode | Root Cause | Automated Self-Healing Resolution |
| :-: | :--- | :--- | :--- |
| **1** | **YouTube Daily Limit** (`daily upload limit reached`) | Unverified channels capped at ~10–15 Shorts per 24 hours. | Engine detects quota banner, halts daily submissions, and auto-shifts pending queue slots to tomorrow. |
| **2** | **Modal Scrim / Click Block** (`pointer-events: none`) | YouTube animation or backdrop blocks Playwright pointer clicks. | Auto-presses `Escape` key, waits 10s stabilization cooldown, and retries the click sequence up to 3x. |
| **3** | **2FA / Cookie Expiry** (`Login challenge required`) | Instagram or Google security session token expired. | Flags as non-transient, isolates job so queue continues, and provides 1-click `[🔓 Log In Now]` launcher. |
| **4** | **Windows Sleep Mode** (Stuck in `uploading`) | Windows power-saving suspended CPU and network mid-stream. | Watchdog detects jobs in `uploading` state >10 minutes and resets them cleanly back to `pending`. |
| **5** | **Network Idle Timeout** (`net::ERR_TIMED_OUT`) | Studio asset upload took longer than 60s timeout. | Flushes Chromium socket cache, verifies connectivity, and retries with progressive backoff. |
| **6** | **Singleton Lockfile** (`SingletonLock in browser_profile`) | Chromium abruptly stopped without flushing lock files. | 1-Click Auto-Heal automatically unlinks orphaned `SingletonLock` and `SingletonCookie` files. |
| **7** | **Excel Metadata Drift** (Missing or shifted columns) | User manually edited Excel structure or removed required headers. | Two-way validator verifies all 11 required columns and restores backups from `backups/`. |

### 1-Click Self-Healing (`⚡ Run Auto-Heal & Fix All`)
Executing this action runs a comprehensive 5-point maintenance routine:
1. Clears dead Chromium singleton lockfiles (`SingletonLock`, `SingletonCookie`, `SingletonSocket`).
2. Resets stuck `uploading` jobs back to `pending`.
3. Re-arms transiently failed jobs with reset attempt counters.
4. Validates SQLite database integrity (`PRAGMA integrity_check`) and executes safe passive WAL checkpoints.
5. Logs all maintenance actions to the system audit trail.

---

## 11. Settings & Customization

Under **⚙️ Settings** (`#settings`):
- **Daily Publishing Slots**: Add or delete custom slots (`HH:MM`). Click **"Save Slots & Realign"** to apply changes immediately.
- **Platform Daily Upload Cap**: Defaults to 9 videos/day to protect channel health and adhere to platform spam guidelines.
- **Directory Paths**: Override defaults for input, output, thumbnails, browser profile, and Excel workbook paths.
- **Excel Metadata Sync**: Run integrity audits and trigger manual syncs.

---

## 12. Troubleshooting & Frequently Asked Questions

### Q1: The browser opens to port 8899, but displays "Port already in use"?
**Solution**: The application includes automatic port recovery. If another process is holding the port, simply re-run `python launch_gui.py` or execute:
```powershell
netstat -ano | findstr :8899
taskkill /F /PID <PID>
```

### Q2: YouTube Studio shows "Select date" error or date picker fails?
**Solution**: YouTube Studio requires exact keyboard input and click-away triggers. The built-in date-picker helper automatically sets the date, navigates the calendar popup, verifies input formatting, and sends `Tab` or `Escape` to commit the selection.

### Q3: How do I re-publish a video if I deleted it from YouTube Studio?
**Solution**:
1. Go to **Publishing Calendar** or **Publishing Queue**.
2. Click the video and select **"↺ Mark Draft Deleted & Set Pending"** in the Reschedule Modal.
3. Return to the Queue and click **Start Uploading & Scheduling**.

### Q4: FFmpeg error: `'ffmpeg' is not recognized as an internal or external command`?
**Solution**: Ensure FFmpeg binaries are in your Windows PATH:
1. Download essentials build from `gyan.dev` or `ffmpeg.org`.
2. Extract to `C:\Tools\ffmpeg`.
3. Add `C:\Tools\ffmpeg\bin` to your System Environment Variable `Path`.
4. Restart your terminal.

---

## 13. CLI Command Reference

| Action | Command |
| :--- | :--- |
| **Launch Web GUI** | `python launch_gui.py` |
| **Run CLI Dashboard** | `python run.py dashboard --port 8899` |
| **Scan Video Directories** | `python run.py scan` |
| **Sync Excel Metadata** | `python run.py sync` |
| **Process Videos (Outro Every 2nd)** | `python run.py process --rule every_second` |
| **Process Videos (All Outros)** | `python run.py process --rule every` |
| **Process Videos (No Outro)** | `python run.py process --rule none` |
| **Generate Schedule Queue** | `python run.py schedule` |
| **Dry Run Publishing (3 Videos)** | `python run.py publish --limit 3 --dry-run` |
| **Live Publish to YouTube Only** | `python run.py publish --platform youtube --limit 3` |
| **Run Automated Tests** | `pytest tests/ -v` |

---

## 👨‍💻 Author & Engineering Credits

**Created & Maintained by Parth Wagh**  
- **GitHub**: [@parthwagh9999](https://github.com/parthwagh9999)  
- **Repository**: [parthwagh9999/Video-Scheduling](https://github.com/parthwagh9999/Video-Scheduling)

# 🎬 Video Scheduling & Multi-Platform Automation System

A production-grade, Windows-based automation suite and web dashboard to manage, prepare, schedule, and publish videos across **YouTube Shorts**, **Instagram Reels**, and **Facebook Reels** via Playwright browser automation (no publishing APIs used).

---

## 🌟 Key Highlights

- **Pure Browser Automation**: Operates real desktop browser interfaces via Playwright with realistic human-like typing delays, cubic-bezier mouse movements, random pauses, and modal handling.
- **Persistent Profile Authentication**: Uses a dedicated persistent browser profile directory (`browser_profile/`). You sign in once manually, and subsequent automated sessions reuse valid cookies and storage state.
- **3 Daily Slots & Rate Limit Enforcement**: Schedules videos strictly at **08:30**, **18:00**, and **21:00 IST** (Asia/Kolkata), while enforcing a strict **maximum upload cap of 9 videos/day per platform** to prevent spam triggers or account flags.
- **Non-Destructive Excel Sync**: Reads and writes metadata in `YouTube_SEO_61_Videos_500_Word_Descriptions_FILENAME_MATCHED.xlsx`, creates timestamped backups in `output/excel_backups/` before any write, and never overwrites user-approved copy.
- **Smart FFmpeg Concatenation**: Appends the outro video from `End Video/` to every second video (alternating pattern) with zero quality loss using FFmpeg concat demuxer, and extracts high-res opening frame thumbnails (at 0.5s) for each clip.
- **Glassmorphic Web Dashboard**: Complete Single Page Application (SPA) built with FastAPI, vanilla HTML5/CSS3/JavaScript featuring dark-mode aesthetics, real-time status counters, interactive calendar, pipeline tracking, and one-click actions.

---

## 🏗️ Architecture Overview

```
Video Scheduling/
├── run.py                                    # Unified CLI runner
├── requirements.txt                          # Python dependencies
├── video_scheduler.db                        # SQLite database (WAL mode)
├── config/
│   └── settings.py                           # Central configuration & constants
├── app/
│   ├── database/
│   │   └── models.py                         # SQLite schema & CRUD operations
│   ├── video/
│   │   └── processor.py                      # FFmpeg concatenation & thumbnail extractor
│   ├── excel/
│   │   └── sync.py                           # Openpyxl workbook matching & backups
│   ├── scheduler/
│   │   └── engine.py                         # Queue generation & background worker
│   ├── browser/
│   │   └── publisher.py                      # Playwright human-like browser automation
│   └── dashboard/
│       ├── server.py                         # FastAPI REST API server
│       ├── templates/
│       │   └── index.html                    # Dashboard SPA markup
│       └── static/
│           ├── css/dashboard.css             # Glassmorphic dark theme CSS
│           └── js/dashboard.js               # Client application logic
├── tests/                                    # Full test suite (21 unit & integration tests)
├── start video/                              # Source videos (63 clips)
├── End Video/                                # Outro video (End Video.mp4)
└── output/                                   # Processed outputs, thumbnails & backups
```

---

## 🚀 Quick Start

### 1. Launch the Web GUI (One Click)
- **Windows Double-Click**: Double-click `Launch_GUI.bat` (or `START_GUI.bat`) in the root folder.
- **Or via Command Line**:
  ```bash
  python launch_gui.py
  ```
The server will start and automatically open **[http://127.0.0.1:8899](http://127.0.0.1:8899)** in your default browser.

### 2. First-Time Account Login
Open the browser with your dedicated automation profile to log into your creator accounts:
```bash
python run.py login
```
Sign in to:
1. **YouTube Studio** (`studio.youtube.com`)
2. **Instagram** (`instagram.com`)
3. **Facebook** (`facebook.com`)

Press `Enter` in the terminal when finished. The cookies and tokens remain stored in `browser_profile/` for all future automated tasks.

### 3. Check Authentication Status
```bash
python run.py check-auth
```

---

## 💻 CLI Commands

| Command | Description |
|---|---|
| `python run.py dashboard` | Launches the FastAPI dashboard on `http://127.0.0.1:8899` |
| `python run.py scan` | Scans `start video/` and `End Video/`, probes media, and registers items into the database |
| `python run.py sync-excel` | Synchronizes Excel workbook with disk files (creates backup automatically) |
| `python run.py sync-excel --dry-run` | Previews missing files without modifying the workbook |
| `python run.py process` | Renders concatenated videos and extracts opening-frame thumbnails |
| `python run.py process --dry-run` | Previews outro assignment distribution without rendering |
| `python run.py login` | Opens browser for manual login with persistent profile |
| `python run.py check-auth` | Inspects current login state across all platforms |
| `python run.py test` | Executes the complete Pytest test suite |

---

## 📊 Dashboard Modules

1. **Overview**: Real-time stats on source videos, ready to publish, uploaded today, and platform breakdowns.
2. **Video Library**: Full table of discovered videos, metadata, durations, outro indicators, and status filters.
3. **Excel Sync**: Workbook sync summary, missing record preview, and one-click backup & update.
4. **Video Processing**: Outro assignment rules (`every_second`, `every`, `none`), dry-run simulator, and background batch runner.
5. **Thumbnails**: Visual gallery of extracted opening frame thumbnails with resolution and validation status.
6. **Publishing Calendar**: Interactive 30-day view showing daily slots (08:30, 18:00, 21:00 IST) and scheduled videos.
7. **Publishing Queue**: Multi-stage pipeline (`Pending` → `Uploading` → `Uploaded` → `Scheduled` → `Published`), retry counters, and dry-run publisher.
8. **Settings**: Configuration inspector, persistent profile paths, and one-click browser launcher.

---

## 🧪 Testing

Run all unit and integration tests:
```bash
python -m pytest tests/ -v
```
All 21 tests validate database transactions, natural filename ordering, Excel header matching, outro alternation algorithms, queue allocation across time slots, and FastAPI REST endpoints.

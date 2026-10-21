# 🤖 Google Antigravity Integration Guide & AI Companion Playbook

> **100% Native Compatibility with Google Antigravity IDE & AI Pair Programmer**  
> *Created & Engineered by [Parth Wagh](https://github.com/parthwagh9999)*

This repository is designed out-of-the-box to work seamlessly with **Google Antigravity**. You can clone or open this entire workspace directly inside Google Antigravity, and Antigravity's agentic AI assistant can operate, manage, debug, and monitor your entire multi-platform video publishing pipeline autonomously.

---

## 📋 Instant Antigravity AI Prompt (Copy & Paste)

When you open this folder inside **Google Antigravity**, copy and paste the following prompt directly into your Antigravity chat window:

```markdown
Hello Antigravity! I have opened the "Video Scheduling — Creator Studio" repository created by Parth Wagh.

You are acting as my autonomous co-pilot for this project. Here is your core orientation:
1. System Role: This is a privacy-first, desktop-automated video scheduling and publishing suite for vertical short-form videos (YouTube Shorts, Instagram Reels, Facebook Reels) built with Python, FastAPI, SQLite (WAL mode), OpenPyXL, and Playwright browser automation.
2. Port & Dashboard: The dashboard runs at http://127.0.0.1:8899 via `python launch_gui.py`.
3. Database: `video_scheduler.db` tracks source_videos, processed_videos, thumbnails, excel_records, publishing_jobs, and audit_log.
4. Core Media Directories:
   - `start video/`: Raw vertical MP4 clips
   - `End Video/`: Outro video to concatenate
   - `output/processed/`: Concatenated MP4 videos
   - `output/thumbnails/`: 0.0s opening frame thumbnails
   - `YouTube_SEO_61_Videos_500_Word_Descriptions_FILENAME_MATCHED.xlsx`: Two-way SEO metadata workbook with automated backups in `backups/`
5. Automated Self-Healing & Diagnostics:
   - The queue publisher includes in-flight auto-recovery (retries up to 3x with 10s cooldown and modal scrim clearance).
   - Health audit: `GET /api/diagnostics/audit-health`
   - 1-click self-healing: `POST /api/diagnostics/auto-heal-all` (clears Chrome SingletonLocks, resets stuck uploading jobs, checks SQLite WAL integrity).
6. Daily Publishing Cadence:
   - 3 daily slots: 08:30, 18:00, 21:00 IST (Asia/Kolkata).
   - Pacing cap: 9 videos/day per platform (up to 3 days ahead).
7. Safety Rules:
   - Never commit `browser_profile/`, `.env`, tokens, or raw video media.
   - Always run `pytest tests/ -v` (38 unit tests) after making any code adjustments.
   - On Windows, always enforce `asyncio.WindowsProactorEventLoopPolicy()` for Playwright subprocess compatibility.

Please inspect the current system health, verify the database and media directories, and report back what tasks are ready to run.
```

---

## ⚡ What Google Antigravity Can Handle Autonomously

When you talk to Google Antigravity, you can give simple conversational commands. Here is what Antigravity can execute on your behalf:

### 1. Launch & Manage the GUI Dashboard
- **Prompt**: *"Antigravity, start the dashboard server and check if it's healthy."*
- **Action**: Antigravity verifies port `8899`, frees orphaned processes if necessary, starts `python launch_gui.py`, and checks `/api/scheduler/heartbeat`.

### 2. Media Ingestion & Video Outro Processing
- **Prompt**: *"Antigravity, scan my start video folder and process all videos with alternating outros."*
- **Action**: Antigravity runs `python run.py scan` to discover files, checks FFmpeg compatibility, and executes `python run.py process --rule every_second` while generating opening-frame thumbnails (`0.0s`) into `output/thumbnails/`.

### 3. Excel SEO Synchronization
- **Prompt**: *"Antigravity, sync my Excel spreadsheet with the newly added videos."*
- **Action**: Antigravity creates a timestamped copy in `backups/`, parses `YouTube_SEO_61_Videos_500_Word_Descriptions_FILENAME_MATCHED.xlsx`, appends missing video records without touching existing formulas or approved descriptions, and validates row alignment.

### 4. Schedule Calendar Realignment & Time Slot Tuning
- **Prompt**: *"Antigravity, I want to change our evening slot from 18:00 to 19:30 and realign the queue."*
- **Action**: Antigravity safely calls `/api/settings/save-and-realign`, adjusts the schedule in `video_scheduler.db`, realigns future pending jobs, and strictly preserves already published posts.

### 5. Morning "Unattended Study Mode" Watchdog & Auto-Heal
- **Prompt**: *"Antigravity, I'm heading out to study. Run a full pre-flight readiness audit, resolve any stuck locks, and monitor live publishing."*
- **Action**:
  1. Antigravity calls `/api/diagnostics/audit-health` to inspect browser cookies, quota usage, and database state.
  2. Runs `POST /api/diagnostics/auto-heal-all` to clear dead Chrome `SingletonLock` files.
  3. Launches live publishing with in-flight retry enabled.
  4. If a non-transient error occurs (e.g. 2FA challenge), Antigravity diagnoses the exact issue, records it in the audit trail, and isolates the job so remaining uploads continue smoothly.

### 6. Automated Quality Assurance & Testing
- **Prompt**: *"Antigravity, run all unit tests and verify system integrity."*
- **Action**: Antigravity executes `pytest tests/ -v`, verifying all 38 test suites across the API, database schema, natural filename sorting, outro concatenation, Excel structure, and scheduler logic.

---

## 🛠️ Architecture Reference for Antigravity Agents

If Antigravity needs to inspect or extend any part of the system, reference this map:

| Subsystem | Source Path | Key Classes & Functions |
| :--- | :--- | :--- |
| **GUI REST API** | [`app/dashboard/server.py`](file:///h:/google%20antigravity/Video%20Scheduling/app/dashboard/server.py) | `FastAPI`, `api_overview`, `api_diagnostics_audit_health`, `api_diagnostics_auto_heal_all` |
| **Web UI Frontend** | [`app/dashboard/templates/index.html`](file:///h:/google%20antigravity/Video%20Scheduling/app/dashboard/templates/index.html) | Single-page application with dark-mode aesthetic, tabs for Home, Calendar, Queue, Diagnostics, Guide |
| **Frontend Controller** | [`app/dashboard/static/js/dashboard.js`](file:///h:/google%20antigravity/Video%20Scheduling/app/dashboard/static/js/dashboard.js) | `loadDiagnostics()`, `runAutoHealAll()`, `resolveJobIssue()`, `filterGuideCategory()` |
| **Database Engine** | [`app/database/models.py`](file:///h:/google%20antigravity/Video%20Scheduling/app/database/models.py) | SQLite (WAL mode), `init_db()`, `upsert_source_video()`, `get_overview_stats()` |
| **Video Engine** | [`app/video/processor.py`](file:///h:/google%20antigravity/Video%20Scheduling/app/video/processor.py) | FFmpeg concat demuxer, `extract_thumbnail()`, `compute_outro_assignments()` |
| **Excel Sync** | [`app/excel/sync.py`](file:///h:/google%20antigravity/Video%20Scheduling/app/excel/sync.py) | `read_all_records()`, `sync_workbook()`, `create_backup()` |
| **Scheduler Engine** | [`app/scheduler/engine.py`](file:///h:/google%20antigravity/Video%20Scheduling/app/scheduler/engine.py) | `generate_publication_queue()`, `SchedulerWorker`, daily quota calculation |
| **Browser Publisher** | [`app/browser/publisher.py`](file:///h:/google%20antigravity/Video%20Scheduling/app/browser/publisher.py) | Playwright browser automation, human-like typing, modal scrim handling |

---

## 🔒 Security & Safe Sharing Notice

- **Zero Credentials in Git**: All session cookies and authentication states are maintained locally in `browser_profile/` which is ignored by `.gitignore`.
- **Zero API Keys**: Uses native desktop browser automation; no third-party developer accounts or API keys required.
- **Local SQLite Storage**: Your video publishing database (`video_scheduler.db`) and Excel backups remain strictly local on your machine.

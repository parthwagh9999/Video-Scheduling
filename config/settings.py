"""
Central configuration for the Video Scheduling application.
All defaults match the master project specification.
"""
import os
from pathlib import Path

# ── Base paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(r"H:\google antigravity\Video Scheduling")
START_VIDEO_DIR = PROJECT_ROOT / "start video"
END_VIDEO_DIR = PROJECT_ROOT / "End Video"
EXCEL_PATH = PROJECT_ROOT / "YouTube_SEO_61_Videos_500_Word_Descriptions_FILENAME_MATCHED.xlsx"
OUTPUT_DIR = PROJECT_ROOT / "output"
PROCESSED_DIR = OUTPUT_DIR / "processed"
THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails"
BACKUP_DIR = PROJECT_ROOT / "backups"
LOG_DIR = PROJECT_ROOT / "logs"
DB_PATH = PROJECT_ROOT / "video_scheduler.db"
BROWSER_PROFILE_DIR = PROJECT_ROOT / "browser_profile"

# ── Timezone ────────────────────────────────────────────────────────────────
TIMEZONE = "Asia/Kolkata"

# ── Outro rule ──────────────────────────────────────────────────────────────
# Options: "every_second" (default), "every", "none", "manual"
OUTRO_RULE = "every_second"
# When "every_second", start with item at index 0 (first item gets outro)
OUTRO_START_INDEX = 0

# ── Daily limits ────────────────────────────────────────────────────────────
DAILY_UPLOAD_CAP_YOUTUBE = 9
DAILY_UPLOAD_CAP_INSTAGRAM = 9
DAILY_UPLOAD_CAP_FACEBOOK = 9
DAILY_PUBLICATION_COUNT = 3

# ── Publishing time slots (24h format, Asia/Kolkata) ────────────────────────
PUBLISHING_SLOTS = ["08:30", "18:00", "21:00"]

# ── Retry / timeout ────────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = [30, 120, 600]  # 30s, 2min, 10min
BROWSER_TIMEOUT_MS = 120000  # 2 minutes
UPLOAD_TIMEOUT_MS = 600000   # 10 minutes

# ── Catch-up policy ────────────────────────────────────────────────────────
# Options: "next_available" (default), "skip", "compress_today"
CATCHUP_POLICY = "next_available"

# ── Video processing ───────────────────────────────────────────────────────
FFMPEG_PATH = "ffmpeg"
FFPROBE_PATH = "ffprobe"
THUMBNAIL_EXTRACT_TIME = 0.0  # seconds into the start video (0.0 = exact opening first frame)
THUMBNAIL_QUALITY = 2         # ffmpeg -q:v value (2 = high quality)

# ── Dashboard ──────────────────────────────────────────────────────────────
DASHBOARD_HOST = "127.0.0.1"
DASHBOARD_PORT = 8899

# ── Excel columns (exact names as in the workbook) ─────────────────────────
EXCEL_COLUMNS = [
    "Video File Name",
    "SEO Title",
    "SEO Description + Hashtags (copy this entire cell)",
    "Description Word Count",
    "Status",
    "Scheduled Date",
    "Scheduled Time",
    "YouTube URL",
    "Uploaded At",
]

EXCEL_SHEET_NAME = "YouTube SEO"

# ── Status vocabulary ──────────────────────────────────────────────────────
class Status:
    PENDING = "Pending"
    PROCESSING = "Processing"
    READY = "Ready"
    UPLOADING = "Uploading"
    UPLOADED = "Uploaded"
    SCHEDULED = "Scheduled"
    PUBLISHED = "Published"
    FAILED = "Failed"
    NEEDS_ATTENTION = "Needs Attention"
    CANCELLED = "Cancelled"

# ── Platform names ─────────────────────────────────────────────────────────
class Platform:
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"
    ALL = [YOUTUBE, INSTAGRAM, FACEBOOK]

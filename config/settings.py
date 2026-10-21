"""
Central configuration for the Video Scheduling application.
All defaults match the master project specification.
"""
import os
from pathlib import Path

# ── Base paths ──────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(os.environ.get("VIDEO_SCHEDULER_ROOT", Path(__file__).resolve().parent.parent))

START_VIDEO_DIR = Path(os.environ.get("START_VIDEO_DIR", PROJECT_ROOT / "start video"))
END_VIDEO_DIR = Path(os.environ.get("END_VIDEO_DIR", PROJECT_ROOT / "End Video"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "output"))
PROCESSED_DIR = OUTPUT_DIR / "processed"
THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails"
BACKUP_DIR = PROJECT_ROOT / "backups"
LOG_DIR = PROJECT_ROOT / "logs"
DB_PATH = Path(os.environ.get("DB_PATH", PROJECT_ROOT / "video_scheduler.db"))
BROWSER_PROFILE_DIR = Path(os.environ.get("BROWSER_PROFILE_DIR", PROJECT_ROOT / "browser_profile"))


def get_excel_path() -> Path:
    """Find user Excel workbook or fall back to default template path."""
    env_path = os.environ.get("EXCEL_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_absolute():
            return p
        return PROJECT_ROOT / p

    # Prefer filename matched workbook if present in project
    specific = PROJECT_ROOT / "YouTube_SEO_61_Videos_500_Word_Descriptions_FILENAME_MATCHED.xlsx"
    if specific.exists():
        return specific

    # Check for any .xlsx in project root (excluding temporary Excel lock files)
    for xlsx in PROJECT_ROOT.glob("*.xlsx"):
        if not xlsx.name.startswith("~$"):
            return xlsx

    return PROJECT_ROOT / "video_metadata.xlsx"


EXCEL_PATH = get_excel_path()


def ensure_directories():
    """Ensure all required project directories exist."""
    for d in [START_VIDEO_DIR, END_VIDEO_DIR, OUTPUT_DIR, PROCESSED_DIR, THUMBNAIL_DIR, BACKUP_DIR, LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# Auto-create standard directories on load
ensure_directories()

USER_SETTINGS_PATH = PROJECT_ROOT / "user_settings.json"

# ── Timezone ────────────────────────────────────────────────────────────────
TIMEZONE = "Asia/Kolkata"

# ── Outro rule ──────────────────────────────────────────────────────────────
# Options: "every_second" (default), "every", "none", "manual"
OUTRO_RULE = "every_second"
# When "every_second", start with item at index 0 (first item gets outro)
OUTRO_START_INDEX = 0
# List of source filenames explicitly selected to receive outro when OUTRO_RULE == "manual"
MANUAL_OUTRO_VIDEOS = []

# ── Daily limits ────────────────────────────────────────────────────────────
DAILY_UPLOAD_CAP_YOUTUBE = 9
DAILY_UPLOAD_CAP_INSTAGRAM = 9
DAILY_UPLOAD_CAP_FACEBOOK = 9
DAILY_PUBLICATION_COUNT = 3

# ── Publishing time slots (24h format, Asia/Kolkata) ────────────────────────
PUBLISHING_SLOTS = ["08:30", "18:00", "21:00"]


def load_user_settings():
    """Load user settings from user_settings.json if present and apply to globals."""
    global START_VIDEO_DIR, END_VIDEO_DIR, OUTPUT_DIR, PROCESSED_DIR, THUMBNAIL_DIR
    global BROWSER_PROFILE_DIR, EXCEL_PATH, TIMEZONE, PUBLISHING_SLOTS
    global DAILY_UPLOAD_CAP_YOUTUBE, DAILY_UPLOAD_CAP_INSTAGRAM, DAILY_UPLOAD_CAP_FACEBOOK
    global DAILY_PUBLICATION_COUNT, OUTRO_RULE, MANUAL_OUTRO_VIDEOS

    if not USER_SETTINGS_PATH.exists():
        return

    try:
        import json
        data = json.loads(USER_SETTINGS_PATH.read_text(encoding="utf-8"))
        if data.get("start_video_dir"):
            START_VIDEO_DIR = Path(data["start_video_dir"])
        if data.get("end_video_dir"):
            END_VIDEO_DIR = Path(data["end_video_dir"])
        if data.get("output_dir"):
            OUTPUT_DIR = Path(data["output_dir"])
            PROCESSED_DIR = OUTPUT_DIR / "processed"
            THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails"
        if data.get("processed_dir"):
            PROCESSED_DIR = Path(data["processed_dir"])
        if data.get("thumbnail_dir"):
            THUMBNAIL_DIR = Path(data["thumbnail_dir"])
        if data.get("browser_profile_dir"):
            BROWSER_PROFILE_DIR = Path(data["browser_profile_dir"])
        if data.get("excel_path"):
            EXCEL_PATH = Path(data["excel_path"])
        if data.get("timezone"):
            TIMEZONE = str(data["timezone"]).strip()
        if data.get("publishing_slots") and isinstance(data["publishing_slots"], list):
            valid = []
            for s in data["publishing_slots"]:
                s_str = str(s).strip()
                parts = s_str.split(":")
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    h, m = int(parts[0]), int(parts[1])
                    if 0 <= h <= 23 and 0 <= m <= 59:
                        valid.append(f"{h:02d}:{m:02d}")
            if valid:
                PUBLISHING_SLOTS = sorted(list(dict.fromkeys(valid)))
                DAILY_PUBLICATION_COUNT = len(PUBLISHING_SLOTS)
        if data.get("daily_upload_cap"):
            cap = int(data["daily_upload_cap"])
            DAILY_UPLOAD_CAP_YOUTUBE = cap
            DAILY_UPLOAD_CAP_INSTAGRAM = cap
            DAILY_UPLOAD_CAP_FACEBOOK = cap
        if data.get("outro_rule"):
            OUTRO_RULE = str(data["outro_rule"]).strip()
        if "manual_outro_videos" in data and isinstance(data["manual_outro_videos"], list):
            MANUAL_OUTRO_VIDEOS = [str(x) for x in data["manual_outro_videos"]]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Could not load user_settings.json: {e}")


def save_user_settings(data: dict) -> dict:
    """Save user settings to user_settings.json and update active configuration."""
    global START_VIDEO_DIR, END_VIDEO_DIR, OUTPUT_DIR, PROCESSED_DIR, THUMBNAIL_DIR
    global BROWSER_PROFILE_DIR, EXCEL_PATH, TIMEZONE, PUBLISHING_SLOTS
    global DAILY_UPLOAD_CAP_YOUTUBE, DAILY_UPLOAD_CAP_INSTAGRAM, DAILY_UPLOAD_CAP_FACEBOOK
    global DAILY_PUBLICATION_COUNT, OUTRO_RULE, MANUAL_OUTRO_VIDEOS

    if "start_video_dir" in data and data["start_video_dir"]:
        START_VIDEO_DIR = Path(data["start_video_dir"])
    if "end_video_dir" in data and data["end_video_dir"]:
        END_VIDEO_DIR = Path(data["end_video_dir"])
    if "excel_path" in data and data["excel_path"]:
        EXCEL_PATH = Path(data["excel_path"])
    if "output_dir" in data and data["output_dir"]:
        OUTPUT_DIR = Path(data["output_dir"])
        PROCESSED_DIR = OUTPUT_DIR / "processed"
        THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails"
    if "processed_dir" in data and data["processed_dir"]:
        PROCESSED_DIR = Path(data["processed_dir"])
    if "thumbnail_dir" in data and data["thumbnail_dir"]:
        THUMBNAIL_DIR = Path(data["thumbnail_dir"])
    if "browser_profile_dir" in data and data["browser_profile_dir"]:
        BROWSER_PROFILE_DIR = Path(data["browser_profile_dir"])
    if "timezone" in data and data["timezone"]:
        TIMEZONE = str(data["timezone"]).strip()
    if "publishing_slots" in data and isinstance(data["publishing_slots"], list):
        valid = []
        for s in data["publishing_slots"]:
            s_str = str(s).strip()
            parts = s_str.split(":")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                h, m = int(parts[0]), int(parts[1])
                if 0 <= h <= 23 and 0 <= m <= 59:
                    valid.append(f"{h:02d}:{m:02d}")
        if valid:
            PUBLISHING_SLOTS = sorted(list(dict.fromkeys(valid)))
            DAILY_PUBLICATION_COUNT = len(PUBLISHING_SLOTS)
    if "daily_upload_cap" in data and data["daily_upload_cap"]:
        cap = int(data["daily_upload_cap"])
        DAILY_UPLOAD_CAP_YOUTUBE = cap
        DAILY_UPLOAD_CAP_INSTAGRAM = cap
        DAILY_UPLOAD_CAP_FACEBOOK = cap
    if "outro_rule" in data and data["outro_rule"]:
        OUTRO_RULE = str(data["outro_rule"]).strip()
    if "manual_outro_videos" in data and isinstance(data["manual_outro_videos"], list):
        MANUAL_OUTRO_VIDEOS = [str(x) for x in data["manual_outro_videos"]]

    ensure_directories()

    import json
    save_data = {
        "start_video_dir": str(START_VIDEO_DIR),
        "end_video_dir": str(END_VIDEO_DIR),
        "excel_path": str(EXCEL_PATH),
        "processed_dir": str(PROCESSED_DIR),
        "thumbnail_dir": str(THUMBNAIL_DIR),
        "browser_profile_dir": str(BROWSER_PROFILE_DIR),
        "timezone": TIMEZONE,
        "publishing_slots": PUBLISHING_SLOTS,
        "daily_upload_cap": DAILY_UPLOAD_CAP_YOUTUBE,
        "daily_publication_count": DAILY_PUBLICATION_COUNT,
        "outro_rule": OUTRO_RULE,
        "manual_outro_videos": MANUAL_OUTRO_VIDEOS,
    }
    USER_SETTINGS_PATH.write_text(json.dumps(save_data, indent=2), encoding="utf-8")
    return get_all_settings()


def get_all_settings() -> dict:
    """Return dictionary of all current application settings."""
    return {
        "start_video_dir": str(START_VIDEO_DIR),
        "end_video_dir": str(END_VIDEO_DIR),
        "excel_path": str(EXCEL_PATH),
        "processed_dir": str(PROCESSED_DIR),
        "thumbnail_dir": str(THUMBNAIL_DIR),
        "browser_profile_dir": str(BROWSER_PROFILE_DIR),
        "timezone": TIMEZONE,
        "outro_rule": OUTRO_RULE,
        "outro_start_index": OUTRO_START_INDEX,
        "manual_outro_videos": MANUAL_OUTRO_VIDEOS,
        "daily_upload_cap": DAILY_UPLOAD_CAP_YOUTUBE,
        "daily_publication_count": DAILY_PUBLICATION_COUNT,
        "publishing_slots": PUBLISHING_SLOTS,
        "db_path": str(DB_PATH),
    }


# Auto-load persisted settings if present
load_user_settings()

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

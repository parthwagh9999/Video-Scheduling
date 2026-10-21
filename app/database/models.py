"""
SQLite database schema and operations for the Video Scheduling application.
Tracks source videos, processed outputs, thumbnails, scheduling, publishing jobs,
Excel sync history, and audit events.
"""
import sqlite3
import os
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import DB_PATH, Status, Platform


def get_connection(db_path=None):
    """Get a SQLite connection with WAL mode and foreign keys enabled."""
    path = db_path or str(DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path=None):
    """Create all tables if they don't exist."""
    conn = get_connection(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
    -- Source videos discovered from the start-video folder
    CREATE TABLE IF NOT EXISTS source_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE NOT NULL,
        filepath TEXT NOT NULL,
        duration_seconds REAL,
        width INTEGER,
        height INTEGER,
        codec TEXT,
        fps TEXT,
        pixel_format TEXT,
        audio_codec TEXT,
        audio_sample_rate INTEGER,
        audio_channels INTEGER,
        file_size_bytes INTEGER,
        discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    -- Processed (concatenated) video outputs
    CREATE TABLE IF NOT EXISTS processed_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_video_id INTEGER NOT NULL REFERENCES source_videos(id),
        source_filename TEXT NOT NULL,
        end_video_filename TEXT,
        outro_appended INTEGER NOT NULL DEFAULT 0,
        sequence_position INTEGER,
        output_filename TEXT NOT NULL,
        output_filepath TEXT NOT NULL,
        output_duration_seconds REAL,
        output_width INTEGER,
        output_height INTEGER,
        processing_params TEXT,
        validation_passed INTEGER DEFAULT 0,
        validation_details TEXT,
        processed_at TEXT NOT NULL DEFAULT (datetime('now')),
        error_message TEXT,
        UNIQUE(source_video_id)
    );

    -- Extracted thumbnails
    CREATE TABLE IF NOT EXISTS thumbnails (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_video_id INTEGER NOT NULL REFERENCES source_videos(id),
        source_filename TEXT NOT NULL,
        thumbnail_path TEXT NOT NULL,
        extract_time_seconds REAL NOT NULL DEFAULT 0.5,
        width INTEGER,
        height INTEGER,
        file_size_bytes INTEGER,
        is_valid INTEGER DEFAULT 0,
        is_blank INTEGER DEFAULT 0,
        extraction_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        upload_status TEXT DEFAULT 'pending',
        browser_confirmed INTEGER DEFAULT 0,
        fallback_used TEXT,
        manual_intervention INTEGER DEFAULT 0,
        notes TEXT,
        UNIQUE(source_video_id)
    );

    -- Excel synchronization metadata
    CREATE TABLE IF NOT EXISTS excel_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_video_id INTEGER REFERENCES source_videos(id),
        filename TEXT UNIQUE NOT NULL,
        seo_title TEXT,
        seo_description TEXT,
        instagram_caption TEXT,
        word_count INTEGER,
        status TEXT DEFAULT 'Pending',
        scheduled_date TEXT,
        scheduled_time TEXT,
        youtube_url TEXT,
        uploaded_at TEXT,
        excel_row_number INTEGER,
        auto_generated INTEGER DEFAULT 0,
        needs_review INTEGER DEFAULT 0,
        synced_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    -- Per-platform publishing jobs
    CREATE TABLE IF NOT EXISTS publishing_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_video_id INTEGER NOT NULL REFERENCES source_videos(id),
        source_filename TEXT NOT NULL,
        platform TEXT NOT NULL,
        video_filepath TEXT NOT NULL,
        seo_title TEXT,
        seo_description TEXT,
        thumbnail_path TEXT,
        scheduled_date TEXT,
        scheduled_time TEXT,
        timezone TEXT DEFAULT 'Asia/Kolkata',
        status TEXT NOT NULL DEFAULT 'pending',
        attempt_count INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        remote_url TEXT,
        error_message TEXT,
        last_attempt_at TEXT,
        confirmed_at TEXT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        updated_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(source_video_id, platform, scheduled_date, scheduled_time)
    );

    -- Daily upload counters
    CREATE TABLE IF NOT EXISTS daily_upload_counts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        platform TEXT NOT NULL,
        upload_count INTEGER NOT NULL DEFAULT 0,
        UNIQUE(date, platform)
    );

    -- Scheduling queue for the calendar
    CREATE TABLE IF NOT EXISTS schedule_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_video_id INTEGER NOT NULL REFERENCES source_videos(id),
        source_filename TEXT NOT NULL,
        platform TEXT NOT NULL,
        publication_date TEXT NOT NULL,
        publication_time TEXT NOT NULL,
        slot_index INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        publishing_job_id INTEGER REFERENCES publishing_jobs(id),
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(platform, publication_date, publication_time)
    );

    -- Processing manifest (persistent record for each video)
    CREATE TABLE IF NOT EXISTS processing_manifest (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_filename TEXT NOT NULL,
        source_filepath TEXT NOT NULL,
        end_video_filename TEXT,
        outro_appended INTEGER NOT NULL DEFAULT 0,
        sequence_position INTEGER,
        processing_params TEXT,
        output_filename TEXT,
        output_filepath TEXT,
        output_duration REAL,
        output_resolution TEXT,
        validation_result TEXT,
        processing_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        processing_errors TEXT,
        UNIQUE(source_filename)
    );

    -- Audit log for traceability
    CREATE TABLE IF NOT EXISTS audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        entity_type TEXT,
        entity_id INTEGER,
        entity_name TEXT,
        details TEXT,
        timestamp TEXT NOT NULL DEFAULT (datetime('now'))
    );

    -- Application settings stored in DB for runtime overrides
    CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    -- Excel sync history
    CREATE TABLE IF NOT EXISTS excel_sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workbook_path TEXT NOT NULL,
        sheet_name TEXT NOT NULL,
        rows_before INTEGER,
        rows_after INTEGER,
        rows_added INTEGER DEFAULT 0,
        rows_updated INTEGER DEFAULT 0,
        rows_unchanged INTEGER DEFAULT 0,
        backup_path TEXT,
        sync_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
        notes TEXT
    );
    """)

    # Safe automated migrations for existing databases
    cursor = conn.cursor()
    cols = [r['name'] for r in cursor.execute("PRAGMA table_info(excel_records)").fetchall()]
    if 'instagram_caption' not in cols:
        cursor.execute("ALTER TABLE excel_records ADD COLUMN instagram_caption TEXT")

    conn.commit()
    return conn


# ── Helper CRUD functions ────────────────────────────────────────────────

def upsert_source_video(conn, data: dict):
    """Insert or update a source video record. Returns the row id."""
    params = {
        'filename': data.get('filename'),
        'filepath': data.get('filepath', ''),
        'duration_seconds': data.get('duration_seconds'),
        'width': data.get('width'),
        'height': data.get('height'),
        'codec': data.get('codec'),
        'fps': data.get('fps'),
        'pixel_format': data.get('pixel_format'),
        'audio_codec': data.get('audio_codec'),
        'audio_sample_rate': data.get('audio_sample_rate'),
        'audio_channels': data.get('audio_channels'),
        'file_size_bytes': data.get('file_size_bytes'),
    }
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO source_videos (filename, filepath, duration_seconds, width, height,
            codec, fps, pixel_format, audio_codec, audio_sample_rate, audio_channels,
            file_size_bytes)
        VALUES (:filename, :filepath, :duration_seconds, :width, :height,
            :codec, :fps, :pixel_format, :audio_codec, :audio_sample_rate,
            :audio_channels, :file_size_bytes)
        ON CONFLICT(filename) DO UPDATE SET
            filepath=excluded.filepath,
            duration_seconds=excluded.duration_seconds,
            width=excluded.width, height=excluded.height,
            codec=excluded.codec, fps=excluded.fps,
            pixel_format=excluded.pixel_format,
            audio_codec=excluded.audio_codec,
            audio_sample_rate=excluded.audio_sample_rate,
            audio_channels=excluded.audio_channels,
            file_size_bytes=excluded.file_size_bytes,
            updated_at=datetime('now')
    """, params)
    conn.commit()
    return cursor.lastrowid or cursor.execute(
        "SELECT id FROM source_videos WHERE filename=?", (params['filename'],)
    ).fetchone()['id']


def upsert_excel_record(conn, data: dict):
    """Insert or update an Excel metadata record."""
    params = {
        'filename': data.get('filename'),
        'seo_title': data.get('seo_title'),
        'seo_description': data.get('seo_description'),
        'word_count': data.get('word_count', 0),
        'status': data.get('status', Status.PENDING),
        'scheduled_date': data.get('scheduled_date'),
        'scheduled_time': data.get('scheduled_time'),
        'youtube_url': data.get('youtube_url'),
        'uploaded_at': data.get('uploaded_at'),
        'excel_row_number': data.get('excel_row_number'),
        'source_video_id': data.get('source_video_id'),
        'auto_generated': data.get('auto_generated', 0),
        'needs_review': data.get('needs_review', 0),
    }
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO excel_records (filename, seo_title, seo_description, word_count,
            status, scheduled_date, scheduled_time, youtube_url, uploaded_at,
            excel_row_number, source_video_id, auto_generated, needs_review)
        VALUES (:filename, :seo_title, :seo_description, :word_count,
            :status, :scheduled_date, :scheduled_time, :youtube_url, :uploaded_at,
            :excel_row_number, :source_video_id, :auto_generated, :needs_review)
        ON CONFLICT(filename) DO UPDATE SET
            seo_title=COALESCE(excluded.seo_title, seo_title),
            seo_description=COALESCE(excluded.seo_description, seo_description),
            word_count=COALESCE(excluded.word_count, word_count),
            status=COALESCE(excluded.status, status),
            scheduled_date=COALESCE(excluded.scheduled_date, scheduled_date),
            scheduled_time=COALESCE(excluded.scheduled_time, scheduled_time),
            youtube_url=COALESCE(excluded.youtube_url, youtube_url),
            uploaded_at=COALESCE(excluded.uploaded_at, uploaded_at),
            excel_row_number=COALESCE(excluded.excel_row_number, excel_row_number),
            source_video_id=COALESCE(excluded.source_video_id, source_video_id),
            updated_at=datetime('now')
    """, params)
    conn.commit()
    return cursor.lastrowid or cursor.execute(
        "SELECT id FROM excel_records WHERE filename=?", (params['filename'],)
    ).fetchone()['id']


def upsert_processed_video(conn, data: dict):
    """Insert or update a processed video record."""
    params = {
        'source_video_id': data.get('source_video_id'),
        'source_filename': data.get('source_filename'),
        'end_video_filename': data.get('end_video_filename'),
        'outro_appended': data.get('outro_appended', 0),
        'sequence_position': data.get('sequence_position'),
        'output_filename': data.get('output_filename', ''),
        'output_filepath': data.get('output_filepath', ''),
        'output_duration_seconds': data.get('output_duration_seconds'),
        'output_width': data.get('output_width'),
        'output_height': data.get('output_height'),
        'processing_params': data.get('processing_params'),
        'validation_passed': data.get('validation_passed', 0),
        'validation_details': data.get('validation_details'),
        'error_message': data.get('error_message'),
    }
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO processed_videos (source_video_id, source_filename, end_video_filename,
            outro_appended, sequence_position, output_filename, output_filepath,
            output_duration_seconds, output_width, output_height, processing_params,
            validation_passed, validation_details, error_message)
        VALUES (:source_video_id, :source_filename, :end_video_filename,
            :outro_appended, :sequence_position, :output_filename, :output_filepath,
            :output_duration_seconds, :output_width, :output_height, :processing_params,
            :validation_passed, :validation_details, :error_message)
        ON CONFLICT(source_video_id) DO UPDATE SET
            end_video_filename=excluded.end_video_filename,
            outro_appended=excluded.outro_appended,
            sequence_position=excluded.sequence_position,
            output_filename=excluded.output_filename,
            output_filepath=excluded.output_filepath,
            output_duration_seconds=excluded.output_duration_seconds,
            output_width=excluded.output_width,
            output_height=excluded.output_height,
            processing_params=excluded.processing_params,
            validation_passed=excluded.validation_passed,
            validation_details=excluded.validation_details,
            error_message=excluded.error_message,
            processed_at=datetime('now')
    """, params)
    conn.commit()


def upsert_thumbnail(conn, data: dict):
    """Insert or update a thumbnail record."""
    params = {
        'source_video_id': data.get('source_video_id'),
        'source_filename': data.get('source_filename'),
        'thumbnail_path': data.get('thumbnail_path', ''),
        'extract_time_seconds': data.get('extract_time_seconds', 0.5),
        'width': data.get('width'),
        'height': data.get('height'),
        'file_size_bytes': data.get('file_size_bytes'),
        'is_valid': data.get('is_valid', 0),
        'is_blank': data.get('is_blank', 0),
        'upload_status': data.get('upload_status', 'pending'),
        'fallback_used': data.get('fallback_used'),
        'manual_intervention': data.get('manual_intervention', 0),
        'notes': data.get('notes'),
    }
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO thumbnails (source_video_id, source_filename, thumbnail_path,
            extract_time_seconds, width, height, file_size_bytes, is_valid, is_blank,
            upload_status, fallback_used, manual_intervention, notes)
        VALUES (:source_video_id, :source_filename, :thumbnail_path,
            :extract_time_seconds, :width, :height, :file_size_bytes, :is_valid,
            :is_blank, :upload_status, :fallback_used, :manual_intervention, :notes)
        ON CONFLICT(source_video_id) DO UPDATE SET
            thumbnail_path=excluded.thumbnail_path,
            extract_time_seconds=excluded.extract_time_seconds,
            width=excluded.width, height=excluded.height,
            file_size_bytes=excluded.file_size_bytes,
            is_valid=excluded.is_valid, is_blank=excluded.is_blank,
            upload_status=excluded.upload_status,
            fallback_used=excluded.fallback_used,
            manual_intervention=excluded.manual_intervention,
            notes=excluded.notes,
            extraction_timestamp=datetime('now')
    """, params)
    conn.commit()


def create_publishing_job(conn, data: dict):
    """Create a new publishing job. Returns the job id."""
    params = {
        'source_video_id': data.get('source_video_id'),
        'source_filename': data.get('source_filename'),
        'platform': data.get('platform'),
        'video_filepath': data.get('video_filepath', ''),
        'seo_title': data.get('seo_title'),
        'seo_description': data.get('seo_description'),
        'thumbnail_path': data.get('thumbnail_path'),
        'scheduled_date': data.get('scheduled_date'),
        'scheduled_time': data.get('scheduled_time'),
        'timezone': data.get('timezone', 'Asia/Kolkata'),
        'status': data.get('status', 'pending'),
        'max_retries': data.get('max_retries', 3),
    }
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO publishing_jobs (source_video_id, source_filename, platform,
                video_filepath, seo_title, seo_description, thumbnail_path,
                scheduled_date, scheduled_time, timezone, status, max_retries)
            VALUES (:source_video_id, :source_filename, :platform,
                :video_filepath, :seo_title, :seo_description, :thumbnail_path,
                :scheduled_date, :scheduled_time, :timezone, :status, :max_retries)
        """, params)
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Job already exists for this video/platform/date/time
        return None


def update_job_status(conn, job_id, status, **kwargs):
    """Update a publishing job status with optional extra fields."""
    sets = ["status=?", "updated_at=datetime('now')"]
    params = [status]
    for key in ('remote_url', 'error_message', 'confirmed_at', 'last_attempt_at'):
        if key in kwargs:
            sets.append(f"{key}=?")
            params.append(kwargs[key])
    if 'increment_attempt' in kwargs and kwargs['increment_attempt']:
        sets.append("attempt_count=attempt_count+1")
    params.append(job_id)
    conn.execute(f"UPDATE publishing_jobs SET {', '.join(sets)} WHERE id=?", params)
    conn.commit()


def log_audit(conn, event_type, entity_type=None, entity_id=None,
              entity_name=None, details=None):
    """Write an audit log entry."""
    conn.execute("""
        INSERT INTO audit_log (event_type, entity_type, entity_id, entity_name, details)
        VALUES (?, ?, ?, ?, ?)
    """, (event_type, entity_type, entity_id, entity_name,
          json.dumps(details) if isinstance(details, dict) else details))
    conn.commit()


def get_daily_upload_count(conn, date_str, platform):
    """Get the upload count for a specific date and platform."""
    row = conn.execute(
        "SELECT upload_count FROM daily_upload_counts WHERE date=? AND platform=?",
        (date_str, platform)
    ).fetchone()
    return row['upload_count'] if row else 0


def increment_daily_upload_count(conn, date_str, platform):
    """Increment the daily upload counter."""
    conn.execute("""
        INSERT INTO daily_upload_counts (date, platform, upload_count) VALUES (?, ?, 1)
        ON CONFLICT(date, platform) DO UPDATE SET upload_count=upload_count+1
    """, (date_str, platform))
    conn.commit()


def get_all_source_videos(conn):
    """Return all source videos ordered by filename."""
    return conn.execute(
        "SELECT * FROM source_videos ORDER BY filename"
    ).fetchall()


def get_all_publishing_jobs(conn, platform=None, status=None):
    """Return publishing jobs with optional filters."""
    query = "SELECT * FROM publishing_jobs WHERE 1=1"
    params = []
    if platform:
        query += " AND platform=?"
        params.append(platform)
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY scheduled_date, scheduled_time"
    return conn.execute(query, params).fetchall()


def get_overview_stats(conn):
    """Get aggregate counts for the dashboard overview."""
    stats = {}
    stats['total_source_videos'] = conn.execute(
        "SELECT COUNT(*) c FROM source_videos").fetchone()['c']
    stats['total_with_outro'] = conn.execute(
        "SELECT COUNT(*) c FROM processed_videos WHERE outro_appended=1").fetchone()['c']
    stats['total_without_outro'] = conn.execute(
        "SELECT COUNT(*) c FROM processed_videos WHERE outro_appended=0").fetchone()['c']
    stats['total_processed'] = conn.execute(
        "SELECT COUNT(*) c FROM processed_videos WHERE validation_passed=1").fetchone()['c']
    stats['total_thumbnails'] = conn.execute(
        "SELECT COUNT(*) c FROM thumbnails WHERE is_valid=1").fetchone()['c']
    stats['total_excel_records'] = conn.execute(
        "SELECT COUNT(*) c FROM excel_records").fetchone()['c']
    stats['missing_excel_records'] = conn.execute(
        "SELECT COUNT(*) c FROM source_videos sv LEFT JOIN excel_records er ON sv.filename=er.filename WHERE er.id IS NULL").fetchone()['c']
    stats['unmatched_metadata'] = conn.execute(
        "SELECT COUNT(*) c FROM excel_records WHERE source_video_id IS NULL").fetchone()['c']

    for platform in Platform.ALL:
        pkey = platform
        stats[f'{pkey}_pending'] = conn.execute(
            "SELECT COUNT(*) c FROM publishing_jobs WHERE platform=? AND status='pending'",
            (platform,)).fetchone()['c']
        stats[f'{pkey}_uploading'] = conn.execute(
            "SELECT COUNT(*) c FROM publishing_jobs WHERE platform=? AND status='uploading'",
            (platform,)).fetchone()['c']
        stats[f'{pkey}_uploaded'] = conn.execute(
            "SELECT COUNT(*) c FROM publishing_jobs WHERE platform=? AND status='uploaded'",
            (platform,)).fetchone()['c']
        stats[f'{pkey}_scheduled'] = conn.execute(
            "SELECT COUNT(*) c FROM publishing_jobs WHERE platform=? AND status='scheduled'",
            (platform,)).fetchone()['c']
        stats[f'{pkey}_published'] = conn.execute(
            "SELECT COUNT(*) c FROM publishing_jobs WHERE platform=? AND status='published'",
            (platform,)).fetchone()['c']
        stats[f'{pkey}_failed'] = conn.execute(
            "SELECT COUNT(*) c FROM publishing_jobs WHERE platform=? AND status='failed'",
            (platform,)).fetchone()['c']
        stats[f'{pkey}_needs_attention'] = conn.execute(
            "SELECT COUNT(*) c FROM publishing_jobs WHERE platform=? AND status='needs_attention'",
            (platform,)).fetchone()['c']

    stats['total_failed'] = conn.execute(
        "SELECT COUNT(*) c FROM publishing_jobs WHERE status='failed'").fetchone()['c']
    stats['total_needs_attention'] = conn.execute(
        "SELECT COUNT(*) c FROM publishing_jobs WHERE status='needs_attention'").fetchone()['c']

    # Convenience aliases for dashboard & API
    stats['source_videos'] = stats['total_source_videos']
    stats['ready_to_publish'] = stats['total_processed']
    stats['published'] = sum(stats[f'{p}_published'] for p in Platform.ALL)
    stats['scheduled'] = sum(stats[f'{p}_scheduled'] for p in Platform.ALL)
    today_str = datetime.now().strftime("%Y-%m-%d")
    stats['uploaded_today'] = conn.execute(
        "SELECT COALESCE(SUM(upload_count), 0) s FROM daily_upload_counts WHERE date=?", (today_str,)
    ).fetchone()['s']
    stats['platforms'] = {}
    for p in Platform.ALL:
        stats['platforms'][p] = {
            'published': stats[f'{p}_published'],
            'scheduled': stats[f'{p}_scheduled'],
            'failed': stats[f'{p}_failed'],
            'pending': stats[f'{p}_pending'],
        }

    return stats

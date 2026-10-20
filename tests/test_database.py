"""
Unit tests for database models and schema.
"""
import sqlite3
import pytest
from pathlib import Path
from app.database.models import (
    init_db, get_connection, upsert_source_video, upsert_excel_record,
    upsert_processed_video, upsert_thumbnail, create_publishing_job,
    get_overview_stats, get_all_source_videos, get_all_publishing_jobs,
    log_audit,
)


@pytest.fixture
def test_db(tmp_path):
    """Fixture providing a temporary in-memory or file-backed database."""
    db_file = tmp_path / "test.db"
    conn = init_db(db_file)
    yield conn, db_file
    conn.close()


def test_init_db_creates_tables(test_db):
    conn, _ = test_db
    cursor = conn.cursor()
    tables = cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {t['name'] for t in tables}

    expected_tables = {
        'source_videos', 'processed_videos', 'thumbnails',
        'excel_records', 'publishing_jobs', 'audit_log',
        'processing_manifest', 'daily_upload_counts', 'schedule_queue'
    }
    assert expected_tables.issubset(table_names)


def test_upsert_source_video(test_db):
    conn, _ = test_db
    vid = {
        'filename': 'test_video_01.mp4',
        'filepath': 'H:/test/test_video_01.mp4',
        'duration_seconds': 45.2,
        'width': 1080,
        'height': 1920,
        'codec': 'h264',
        'fps': 30.0,
        'file_size_bytes': 15000000,
    }
    vid_id = upsert_source_video(conn, vid)
    assert vid_id > 0

    # Retrieve and check
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM source_videos WHERE id=?", (vid_id,)).fetchone()
    assert row['filename'] == 'test_video_01.mp4'
    assert row['duration_seconds'] == 45.2
    assert row['width'] == 1080


def test_upsert_excel_record(test_db):
    conn, _ = test_db
    rec = {
        'filename': 'test_video_01.mp4',
        'seo_title': 'Amazing Wildlife Short #shorts',
        'seo_description': 'Check out this wild creature in action! #wildlife #shorts',
        'word_count': 10,
        'status': 'Pending',
        'scheduled_date': '2026-10-19',
        'scheduled_time': '08:30',
        'excel_row_number': 2,
    }
    row_id = upsert_excel_record(conn, rec)
    assert row_id > 0

    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM excel_records WHERE filename=?", (rec['filename'],)).fetchone()
    assert row['seo_title'] == rec['seo_title']
    assert row['word_count'] == 10


def test_overview_stats(test_db):
    conn, _ = test_db
    # Empty stats
    stats = get_overview_stats(conn)
    assert stats['source_videos'] == 0
    assert stats['ready_to_publish'] == 0

    # Insert a video
    upsert_source_video(conn, {
        'filename': 'vid1.mp4',
        'filepath': '/path/vid1.mp4',
        'duration_seconds': 30.0,
    })
    stats = get_overview_stats(conn)
    assert stats['source_videos'] == 1

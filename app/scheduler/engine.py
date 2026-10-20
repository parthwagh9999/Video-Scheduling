"""
Scheduling engine for video publication.
- Builds a publication queue from 3 daily time slots
- Enforces daily upload caps per platform
- Manages the scheduling queue with catch-up policies
- Generates 30-day calendar previews
- Runs as a persistent background worker
"""
import asyncio
import logging
from datetime import datetime, timedelta, date, time
from pathlib import Path
import sys
import json
import signal

import pytz

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import (
    TIMEZONE, PUBLISHING_SLOTS, DAILY_UPLOAD_CAP_YOUTUBE,
    DAILY_UPLOAD_CAP_INSTAGRAM, DAILY_UPLOAD_CAP_FACEBOOK,
    DAILY_PUBLICATION_COUNT, MAX_RETRIES, RETRY_BACKOFF_SECONDS,
    CATCHUP_POLICY, Platform, Status, DB_PATH,
)
from app.database.models import (
    get_connection, get_daily_upload_count, increment_daily_upload_count,
    create_publishing_job, update_job_status, log_audit,
    get_all_publishing_jobs,
)

logger = logging.getLogger(__name__)


def get_timezone():
    """Get the configured timezone object."""
    return pytz.timezone(TIMEZONE)


def parse_time_slot(slot_str):
    """Parse a time slot string like '08:30' into a time object."""
    parts = slot_str.split(':')
    return time(int(parts[0]), int(parts[1]))


def get_daily_slots():
    """Return the configured daily publication time slots as time objects."""
    return [parse_time_slot(s) for s in PUBLISHING_SLOTS]


def get_upload_cap(platform):
    """Get the daily upload cap for a platform."""
    caps = {
        Platform.YOUTUBE: DAILY_UPLOAD_CAP_YOUTUBE,
        Platform.INSTAGRAM: DAILY_UPLOAD_CAP_INSTAGRAM,
        Platform.FACEBOOK: DAILY_UPLOAD_CAP_FACEBOOK,
    }
    return caps.get(platform, 9)


def generate_publication_queue(videos, start_date=None, platforms=None):
    """
    Generate a chronological publication queue.
    Each video gets assigned to a date + time slot across selected platforms.

    Args:
        videos: list of dicts with at least 'filename', 'video_path', 'title', 'description'
        start_date: first publication date (default: tomorrow)
        platforms: list of platforms to schedule for

    Returns:
        list of schedule entries
    """
    tz = get_timezone()
    if start_date is None:
        now = datetime.now(tz)
        start_date = (now + timedelta(days=1)).date()
    elif isinstance(start_date, str):
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()

    if platforms is None:
        platforms = [Platform.YOUTUBE]

    slots = get_daily_slots()
    queue = []
    current_date = start_date
    slot_index = 0

    for video in videos:
        for platform in platforms:
            entry = {
                'source_filename': video.get('filename', video.get('source_filename')),
                'video_path': video.get('video_path', video.get('output_filepath')),
                'seo_title': video.get('title', video.get('seo_title')),
                'seo_description': video.get('description', video.get('seo_description')),
                'thumbnail_path': video.get('thumbnail_path'),
                'platform': platform,
                'publication_date': current_date.isoformat(),
                'publication_time': slots[slot_index].strftime("%H:%M"),
                'slot_index': slot_index,
            }
            queue.append(entry)

        # Advance to next slot
        slot_index += 1
        if slot_index >= len(slots):
            slot_index = 0
            current_date += timedelta(days=1)

    return queue


def generate_calendar_preview(queue, days=30):
    """
    Generate a 30-day calendar preview from a queue.
    Returns a structured calendar dict.
    """
    calendar = {}
    for entry in queue:
        d = entry['publication_date']
        if d not in calendar:
            calendar[d] = []
        calendar[d].append({
            'time': entry['publication_time'],
            'filename': entry['source_filename'],
            'platform': entry['platform'],
            'title': entry.get('seo_title', ''),
        })

    # Sort each day's entries
    for d in calendar:
        calendar[d].sort(key=lambda x: x['time'])

    return calendar


def check_slot_available(conn, platform, pub_date, pub_time):
    """Check if a publication slot is available."""
    row = conn.execute(
        "SELECT id FROM schedule_queue WHERE platform=? AND publication_date=? AND publication_time=?",
        (platform, pub_date, pub_time)
    ).fetchone()
    return row is None


def check_already_scheduled(conn, source_filename, platform):
    """Check if a video is already scheduled/published on a platform."""
    row = conn.execute(
        "SELECT id, status FROM publishing_jobs WHERE source_filename=? AND platform=? AND status IN ('scheduled', 'published', 'uploaded')",
        (source_filename, platform)
    ).fetchone()
    return row is not None


def apply_catchup_policy(missed_slots, policy=None):
    """
    Apply catch-up policy for missed publication slots.
    Returns adjusted list of rescheduled entries.
    """
    policy = policy or CATCHUP_POLICY
    tz = get_timezone()
    now = datetime.now(tz)

    if policy == 'skip':
        logger.info(f"Skipping {len(missed_slots)} missed slots")
        return []

    rescheduled = []
    slots = get_daily_slots()

    # Find next available date/time
    current_date = now.date()
    current_time = now.time()

    # Find the next future slot
    next_slot_idx = None
    for i, slot_time in enumerate(slots):
        if slot_time > current_time:
            next_slot_idx = i
            break

    if next_slot_idx is None:
        current_date += timedelta(days=1)
        next_slot_idx = 0

    for entry in missed_slots:
        entry['publication_date'] = current_date.isoformat()
        entry['publication_time'] = slots[next_slot_idx].strftime("%H:%M")
        entry['rescheduled'] = True
        entry['original_date'] = entry.get('original_date', entry['publication_date'])
        rescheduled.append(entry)

        next_slot_idx += 1
        if next_slot_idx >= len(slots):
            next_slot_idx = 0
            current_date += timedelta(days=1)

    return rescheduled


def commit_queue_to_db(conn, queue):
    """
    Save a publication queue to the database.
    Prevents duplicate entries.
    Returns count of new entries.
    """
    added = 0
    for entry in queue:
        # Check for existing
        if check_already_scheduled(conn, entry['source_filename'], entry['platform']):
            logger.info(f"Already scheduled: {entry['source_filename']} on {entry['platform']}")
            continue

        if not check_slot_available(conn, entry['platform'],
                                     entry['publication_date'], entry['publication_time']):
            logger.warning(f"Slot occupied: {entry['platform']} {entry['publication_date']} {entry['publication_time']}")
            continue

        # Get source video id
        row = conn.execute(
            "SELECT id FROM source_videos WHERE filename=?",
            (entry['source_filename'],)
        ).fetchone()
        source_id = row['id'] if row else None

        if source_id is None:
            logger.warning(f"Source video not in DB: {entry['source_filename']}")
            continue

        # Create scheduling record
        conn.execute("""
            INSERT OR IGNORE INTO schedule_queue
                (source_video_id, source_filename, platform, publication_date,
                 publication_time, slot_index, status)
            VALUES (?, ?, ?, ?, ?, ?, 'queued')
        """, (source_id, entry['source_filename'], entry['platform'],
              entry['publication_date'], entry['publication_time'],
              entry.get('slot_index', 0)))

        # Create publishing job
        job_data = {
            'source_video_id': source_id,
            'source_filename': entry['source_filename'],
            'platform': entry['platform'],
            'video_filepath': entry.get('video_path', ''),
            'seo_title': entry.get('seo_title', ''),
            'seo_description': entry.get('seo_description', ''),
            'thumbnail_path': entry.get('thumbnail_path', ''),
            'scheduled_date': entry['publication_date'],
            'scheduled_time': entry['publication_time'],
            'timezone': TIMEZONE,
            'status': 'pending',
            'max_retries': MAX_RETRIES,
        }
        job_id = create_publishing_job(conn, job_data)
        if job_id:
            added += 1

    conn.commit()
    return added


class SchedulerWorker:
    """
    Background scheduler worker.
    Checks for due jobs and executes them via the browser engine.
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or str(DB_PATH)
        self.running = False
        self.check_interval = 60  # seconds

    async def start(self):
        """Start the scheduler loop."""
        self.running = True
        logger.info("Scheduler worker started")

        while self.running:
            try:
                await self._check_due_jobs()
            except Exception as e:
                logger.error(f"Scheduler check failed: {e}")

            await asyncio.sleep(self.check_interval)

    def stop(self):
        """Signal the scheduler to stop."""
        self.running = False
        logger.info("Scheduler worker stopping")

    async def _check_due_jobs(self):
        """Check for jobs that are due for execution."""
        conn = get_connection(self.db_path)
        tz = get_timezone()
        now = datetime.now(tz)
        current_date = now.strftime("%Y-%m-%d")
        current_time = now.strftime("%H:%M")

        # Find pending jobs due now or earlier
        due_jobs = conn.execute("""
            SELECT pj.*, sq.slot_index
            FROM publishing_jobs pj
            LEFT JOIN schedule_queue sq ON pj.source_filename=sq.source_filename
                AND pj.platform=sq.platform AND pj.scheduled_date=sq.publication_date
            WHERE pj.status='pending'
                AND (pj.scheduled_date < ? OR (pj.scheduled_date = ? AND pj.scheduled_time <= ?))
            ORDER BY pj.scheduled_date, pj.scheduled_time
        """, (current_date, current_date, current_time)).fetchall()

        if due_jobs:
            logger.info(f"Found {len(due_jobs)} due jobs")

        conn.close()

    async def get_heartbeat(self):
        """Return scheduler health status."""
        return {
            'running': self.running,
            'check_interval': self.check_interval,
            'timestamp': datetime.now().isoformat(),
        }

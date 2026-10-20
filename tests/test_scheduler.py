"""
Unit tests for scheduling engine, slots calculation, and queue generator.
"""
import pytest
from datetime import date
from app.scheduler.engine import (
    get_daily_slots, get_upload_cap, generate_publication_queue,
    generate_calendar_preview
)
from config.settings import Platform


def test_get_daily_slots():
    slots = get_daily_slots()
    assert len(slots) == 3
    times_str = [s.strftime("%H:%M") for s in slots]
    assert times_str == ["08:30", "18:00", "21:00"]


def test_get_upload_cap():
    assert get_upload_cap(Platform.YOUTUBE) == 9
    assert get_upload_cap(Platform.INSTAGRAM) == 9
    assert get_upload_cap(Platform.FACEBOOK) == 9


def test_generate_publication_queue():
    videos = [
        {'filename': f"video_{i:02d}.mp4", 'video_path': f"/path/video_{i:02d}.mp4", 'title': f"Short {i}"}
        for i in range(5)
    ]
    queue = generate_publication_queue(videos, start_date="2026-10-20", platforms=[Platform.YOUTUBE])

    assert len(queue) == 5
    # Day 1 (2026-10-20): 3 slots
    assert queue[0]['publication_date'] == "2026-10-20"
    assert queue[0]['publication_time'] == "08:30"
    assert queue[1]['publication_date'] == "2026-10-20"
    assert queue[1]['publication_time'] == "18:00"
    assert queue[2]['publication_date'] == "2026-10-20"
    assert queue[2]['publication_time'] == "21:00"

    # Day 2 (2026-10-21): next 2 slots
    assert queue[3]['publication_date'] == "2026-10-21"
    assert queue[3]['publication_time'] == "08:30"
    assert queue[4]['publication_date'] == "2026-10-21"
    assert queue[4]['publication_time'] == "18:00"


def test_generate_calendar_preview():
    videos = [
        {'filename': f"video_{i}.mp4", 'title': f"Title {i}"} for i in range(4)
    ]
    queue = generate_publication_queue(videos, start_date="2026-11-01", platforms=[Platform.YOUTUBE])
    calendar = generate_calendar_preview(queue)

    assert "2026-11-01" in calendar
    assert len(calendar["2026-11-01"]) == 3
    assert "2026-11-02" in calendar
    assert len(calendar["2026-11-02"]) == 1

"""
Unit tests for video discovery, sorting, and outro assignment computation.
"""
import pytest
from pathlib import Path
from app.video.processor import (
    natural_sort_key, compute_outro_assignments, check_compatibility
)


def test_natural_sort_key():
    files = ["10_video.mp4", "1_video.mp4", "2_video.mp4", "20_video.mp4"]
    sorted_files = sorted(files, key=natural_sort_key)
    assert sorted_files == ["1_video.mp4", "2_video.mp4", "10_video.mp4", "20_video.mp4"]


def test_outro_assignments_every_second_start_0():
    filenames = [f"vid_{i}.mp4" for i in range(6)]
    assignments = compute_outro_assignments(filenames, rule="every_second", start_index=0)

    # Indices 0, 2, 4 should get outro (True)
    # Indices 1, 3, 5 should NOT get outro (False)
    assert assignments[0][1] is True
    assert assignments[1][1] is False
    assert assignments[2][1] is True
    assert assignments[3][1] is False
    assert assignments[4][1] is True
    assert assignments[5][1] is False


def test_outro_assignments_every():
    filenames = ["v1.mp4", "v2.mp4", "v3.mp4"]
    assignments = compute_outro_assignments(filenames, rule="every")
    assert all(gets_outro for _, gets_outro, _ in assignments)


def test_outro_assignments_none():
    filenames = ["v1.mp4", "v2.mp4", "v3.mp4"]
    assignments = compute_outro_assignments(filenames, rule="none")
    assert not any(gets_outro for _, gets_outro, _ in assignments)


def test_check_compatibility_match():
    info1 = {'width': 1080, 'height': 1920, 'codec': 'h264', 'fps': '30/1', 'audio_codec': 'aac'}
    info2 = {'width': 1080, 'height': 1920, 'codec': 'h264', 'fps': '30/1', 'audio_codec': 'aac'}
    issues = check_compatibility(info1, info2)
    assert len(issues) == 0


def test_check_compatibility_mismatch():
    info1 = {'width': 1080, 'height': 1920, 'codec': 'h264'}
    info2 = {'width': 720, 'height': 1280, 'codec': 'h264'}
    issues = check_compatibility(info1, info2)
    assert len(issues) > 0

"""
Integration tests for FastAPI dashboard API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from app.dashboard.server import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_home_page_returns_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Video Scheduling Dashboard" in response.text


def test_api_overview(client):
    response = client.get("/api/overview")
    assert response.status_code == 200
    data = response.json()
    assert "source_videos" in data
    assert "ready_to_publish" in data
    assert "platforms" in data


def test_api_settings(client):
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert "timezone" in data
    assert data["timezone"] == "Asia/Kolkata"
    assert "publishing_slots" in data
    assert data["publishing_slots"] == ["08:30", "18:00", "21:00"]


def test_api_processing_status(client):
    response = client.get("/api/processing/status")
    assert response.status_code == 200
    data = response.json()
    assert "total_source" in data
    assert "processed" in data


def test_queue_publish_stream_dry_run(client):
    response = client.get("/api/queue/publish/stream?dry_run=true&limit=1")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "data:" in content
    assert "QUEUE PUBLISHING ENGINE" in content


def test_queue_publish_stop(client):
    response = client.post("/api/queue/publish/stop")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "stopped"


def test_queue_reset_failed(client):
    response = client.post("/api/queue/reset-failed")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "reset_count" in data


def test_windows_event_loop_factory():
    """Verify that Uvicorn loop factory returns ProactorEventLoop on Windows."""
    import sys
    if sys.platform == "win32":
        import asyncio
        import uvicorn.loops.asyncio
        import uvicorn.loops.auto
        assert uvicorn.loops.asyncio.asyncio_loop_factory(use_subprocess=True) == asyncio.ProactorEventLoop
        assert uvicorn.loops.auto.auto_loop_factory(use_subprocess=True) == asyncio.ProactorEventLoop


def test_api_schedule_calendar(client):
    response = client.get("/api/schedule/calendar?month=2026-10")
    assert response.status_code == 200
    data = response.json()
    assert "calendar" in data
    assert "total_events" in data
    assert isinstance(data["calendar"], dict)


def test_api_update_jobs_status(client):
    # Test setting status to scheduled then resetting back to pending
    response = client.post("/api/schedule/jobs/update-status", json={"job_id": 1, "status": "scheduled"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["status"] == "scheduled"

    # Reset back to pending (simulating deleting draft manually)
    response2 = client.post("/api/schedule/jobs/update-status", json={"job_id": 1, "status": "pending"})
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["success"] is True
    assert data2["status"] == "pending"


def test_api_reschedule_job(client):
    response = client.post("/api/schedule/jobs/reschedule", json={
        "job_id": 1,
        "scheduled_date": "2026-10-20",
        "scheduled_time": "08:30",
        "status": "pending",
        "update_all_platforms": True
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["scheduled_date"] == "2026-10-20"
    assert data["scheduled_time"] == "08:30"






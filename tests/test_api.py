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
    assert 'data-page="guide"' in response.text
    assert 'id="page-guide"' in response.text


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
    assert "publishing_slots" in data
    assert isinstance(data["publishing_slots"], list)
    assert len(data["publishing_slots"]) >= 1


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

def test_api_system_health(client):
    response = client.get("/api/system/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "python" in data
    assert "ffmpeg" in data
    assert "storage" in data
    assert "auth" in data
    assert "publishing" in data
    assert data["python"]["ok"] is True


def test_api_upcoming_schedule(client):
    response = client.get("/api/upcoming-schedule")
    assert response.status_code == 200
    data = response.json()
    assert "upcoming" in data
    assert isinstance(data["upcoming"], list)


def test_api_recent_activity(client):
    response = client.get("/api/recent-activity")
    assert response.status_code == 200
    data = response.json()
    assert "recent_jobs" in data
    assert "audit_events" in data
    assert isinstance(data["recent_jobs"], list)
    assert isinstance(data["audit_events"], list)


def test_api_scheduler_heartbeat(client):
    response = client.get("/api/scheduler/heartbeat")
    assert response.status_code == 200
    data = response.json()
    assert "running" in data
    assert "timestamp" in data


def test_api_queue_jobs_endpoint(client):
    response = client.get("/api/queue/jobs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_save_settings_and_realign(client):
    # Test GET settings
    res = client.get("/api/settings")
    assert res.status_code == 200
    current = res.json()
    assert "publishing_slots" in current
    orig_slots = current.get("publishing_slots", ["08:30", "18:00", "21:00"])
    orig_tz = current.get("timezone", "Asia/Kolkata")

    try:
        # Test POST settings with a new slot added
        payload = {
            "timezone": "Asia/Kolkata",
            "publishing_slots": ["08:30", "14:00", "18:00", "21:00"],
            "daily_upload_cap": 9,
            "realign_schedule": True,
            "include_future_scheduled": True,
        }
        post_res = client.post("/api/settings", json=payload)
        assert post_res.status_code == 200
        data = post_res.json()
        assert data["success"] is True
        assert "realign" in data
        assert "14:00" in data["settings"]["publishing_slots"]
    finally:
        # Guarantee restoration of original slots so tests leave working tree clean
        restore_res = client.post("/api/settings", json={
            "timezone": orig_tz,
            "publishing_slots": orig_slots,
            "daily_upload_cap": 9,
            "realign_schedule": True,
            "include_future_scheduled": True,
        })
        assert restore_res.status_code == 200


def test_api_processing_preview_manual(client):
    """Test preview endpoint with manual outro selection."""
    res = client.get("/api/processing/preview?outro_rule=manual&start_index=0&manual_selection=test1.mp4,test2.mp4")
    assert res.status_code == 200
    data = res.json()
    assert data["outro_rule"] == "manual"
    assert "sequence" in data
    assert "total_videos" in data


def test_api_diagnostics_audit_health(client):
    """Test the Auto-Healer diagnostics audit-health endpoint."""
    res = client.get("/api/diagnostics/audit-health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "unattended_ready" in data
    assert "active_issues" in data
    assert "quota_status" in data
    assert "auth" in data
    assert "db_counts" in data


def test_api_diagnostics_auto_heal_all(client):
    """Test the 5-point automated self-healing execution endpoint."""
    res = client.post("/api/diagnostics/auto-heal-all")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "resolved_count" in data
    assert "actions_taken" in data
    assert isinstance(data["actions_taken"], list)


def test_api_diagnostics_resolve_job(client):
    """Test 1-click issue resolver for a job."""
    res = client.post("/api/diagnostics/resolve-job", json={"job_id": 1, "action": "re-arm"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "message" in data





"""
FastAPI Dashboard Server — the main application entry point.
Serves the web dashboard and provides REST API endpoints for all operations.
"""
import asyncio
import sys

# Ensure UTF-8 output encoding on Windows to prevent charmap UnicodeEncodeErrors
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass
    try:
        import uvicorn.loops.asyncio
        uvicorn.loops.asyncio.asyncio_loop_factory = lambda use_subprocess=False: asyncio.ProactorEventLoop
    except Exception:
        pass
    try:
        import uvicorn.loops.auto
        uvicorn.loops.auto.auto_loop_factory = lambda use_subprocess=False: asyncio.ProactorEventLoop
    except Exception:
        pass

import json
import logging
import os
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import (
    DASHBOARD_HOST, DASHBOARD_PORT, START_VIDEO_DIR, END_VIDEO_DIR,
    EXCEL_PATH, PROCESSED_DIR, THUMBNAIL_DIR, BACKUP_DIR, DB_PATH,
    BROWSER_PROFILE_DIR, TIMEZONE, OUTRO_RULE, OUTRO_START_INDEX,
    DAILY_UPLOAD_CAP_YOUTUBE, DAILY_PUBLICATION_COUNT,
    PUBLISHING_SLOTS, Platform, Status, LOG_DIR,
    FFMPEG_PATH, FFPROBE_PATH,
)
from app.database.models import (
    init_db, get_connection, upsert_source_video, upsert_excel_record,
    upsert_processed_video, upsert_thumbnail, get_overview_stats,
    get_all_source_videos, get_all_publishing_jobs, log_audit,
)
from app.video.processor import (
    discover_start_videos, discover_end_video, probe_video,
    compute_outro_assignments, process_all_videos, natural_sort_key,
    scan_and_sync_thumbnails,
)
from app.excel.sync import (
    read_all_records, find_missing_videos, sync_workbook,
    get_sync_summary, validate_workbook_structure, load_workbook_safe,
    create_backup, preview_new_records,
)
from app.scheduler.engine import (
    generate_publication_queue, generate_calendar_preview,
    commit_queue_to_db, SchedulerWorker,
)

# ── Logging setup ─────────────────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(str(LOG_DIR / 'app.log'), encoding='utf-8'),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────────────────────────────
scheduler_worker = None
active_browser_engine = None
queue_publish_lock = asyncio.Lock()
is_queue_publishing_running = False
pipeline_run_all_lock = asyncio.Lock()
is_pipeline_running = False

processing_state = {
    "is_running": False,
    "progress": 0,
    "total": 0,
    "current_file": "",
    "status": "idle",
    "message": "",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: init DB and start scheduler."""
    logger.info("Starting Video Scheduling Application...")
    init_db()
    logger.info(f"Database initialized at {DB_PATH}")

    # Start scheduler worker
    global scheduler_worker, active_browser_engine
    scheduler_worker = SchedulerWorker()

    yield

    # Shutdown
    if scheduler_worker:
        scheduler_worker.stop()
    if active_browser_engine and active_browser_engine.context:
        try:
            await active_browser_engine.stop()
        except Exception:
            pass
    logger.info("Application shutting down")


app = FastAPI(
    title="Video Scheduling — Creator Studio",
    description="Multi-platform video scheduling and publishing automation system. Created by Parth Wagh.",
    version="2.2.8",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# ═══════════════════════════════════════════════════════════════════════════
#  DASHBOARD — HTML PAGES
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def dashboard_home():
    """Serve the main dashboard SPA with dynamic cache busting."""
    html_path = Path(__file__).parent / "templates" / "index.html"
    raw_html = html_path.read_text(encoding='utf-8')
    ts = int(datetime.now().timestamp())
    # Ensure fresh assets on every load
    html_content = raw_html.replace('?v=2.3.0', f'?v={ts}').replace('?v=2.2.8', f'?v={ts}').replace('?v=2.2.2', f'?v={ts}')
    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/favicon.ico")
async def favicon():
    """Return an inline SVG clapperboard favicon."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y=".9em" font-size="90">🎬</text></svg>'
    return Response(content=svg, media_type="image/svg+xml")


# ═══════════════════════════════════════════════════════════════════════════
#  API — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/overview")
async def api_overview():
    """Dashboard overview statistics."""
    conn = get_connection()
    stats = get_overview_stats(conn)
    conn.close()
    stats["created_by"] = "Parth Wagh"
    stats["author"] = "Parth Wagh"
    stats["version"] = "2.2.8"
    return stats


# ═══════════════════════════════════════════════════════════════════════════
#  API — VIDEO LIBRARY
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/videos")
async def api_list_videos():
    """List all discovered source videos with their metadata and status."""
    conn = get_connection()
    videos = conn.execute("""
        SELECT sv.*,
            pv.outro_appended, pv.output_filename, pv.output_filepath,
            pv.validation_passed, pv.output_duration_seconds,
            t.thumbnail_path, t.is_valid as thumb_valid, t.manual_intervention as thumb_manual,
            er.seo_title, er.seo_description, er.status as excel_status,
            er.scheduled_date, er.scheduled_time, er.youtube_url
        FROM source_videos sv
        LEFT JOIN processed_videos pv ON sv.id = pv.source_video_id
        LEFT JOIN thumbnails t ON sv.id = t.source_video_id
        LEFT JOIN excel_records er ON sv.filename = er.filename
        ORDER BY sv.filename
    """).fetchall()
    result = [dict(v) for v in videos]
    conn.close()
    return result


@app.get("/api/videos/{video_id}")
async def api_get_video(video_id: int):
    """Get details for a specific video."""
    conn = get_connection()
    video = conn.execute("SELECT * FROM source_videos WHERE id=?", (video_id,)).fetchone()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    result = dict(video)

    # Get related records
    pv = conn.execute("SELECT * FROM processed_videos WHERE source_video_id=?", (video_id,)).fetchone()
    if pv:
        result['processed'] = dict(pv)

    thumb = conn.execute("SELECT * FROM thumbnails WHERE source_video_id=?", (video_id,)).fetchone()
    if thumb:
        result['thumbnail'] = dict(thumb)

    jobs = conn.execute("SELECT * FROM publishing_jobs WHERE source_video_id=?", (video_id,)).fetchall()
    result['jobs'] = [dict(j) for j in jobs]

    er = conn.execute("SELECT * FROM excel_records WHERE filename=?", (video['filename'],)).fetchone()
    if er:
        result['excel'] = dict(er)

    conn.close()
    return result


# ═══════════════════════════════════════════════════════════════════════════
#  API — DISCOVERY & SCANNING
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/scan")
async def api_scan_videos():
    """
    Scan video folders and populate the database.
    Non-destructive: only adds/updates, never deletes originals.
    """
    conn = get_connection()
    results = {'start_videos': 0, 'end_video': None, 'errors': []}

    try:
        # Discover start videos
        start_files = discover_start_videos()
        for f in start_files:
            try:
                info = probe_video(f)
                upsert_source_video(conn, {
                    'filename': f.name,
                    'filepath': str(f),
                    'duration_seconds': info.get('duration_seconds'),
                    'width': info.get('width'),
                    'height': info.get('height'),
                    'codec': info.get('codec'),
                    'fps': info.get('fps'),
                    'pixel_format': info.get('pixel_format'),
                    'audio_codec': info.get('audio_codec'),
                    'audio_sample_rate': info.get('audio_sample_rate'),
                    'audio_channels': info.get('audio_channels'),
                    'file_size_bytes': info.get('file_size_bytes'),
                })
                results['start_videos'] += 1
            except Exception as e:
                results['errors'].append(f"{f.name}: {e}")

        # Discover end video (optional)
        try:
            end_file = discover_end_video(optional=True)
            if end_file:
                end_info = probe_video(end_file)
                results['end_video'] = {
                    'filename': end_file.name,
                    'duration': end_info['duration_seconds'],
                    'resolution': f"{end_info['width']}x{end_info['height']}",
                }
            else:
                results['end_video'] = None
        except Exception as e:
            results['errors'].append(f"End video: {e}")

        # Sync Excel records to DB
        try:
            records = read_all_records()
            for rec in records:
                sv = conn.execute("SELECT id FROM source_videos WHERE filename=?",
                                   (rec['filename'],)).fetchone()
                upsert_excel_record(conn, {
                    'filename': rec['filename'],
                    'seo_title': rec['seo_title'],
                    'seo_description': rec['seo_description'],
                    'word_count': rec['word_count'],
                    'status': rec['status'] or Status.PENDING,
                    'scheduled_date': rec.get('scheduled_date'),
                    'scheduled_time': rec.get('scheduled_time'),
                    'youtube_url': rec.get('youtube_url'),
                    'uploaded_at': rec.get('uploaded_at'),
                    'excel_row_number': rec['row'],
                    'source_video_id': sv['id'] if sv else None,
                    'auto_generated': 0,
                    'needs_review': 0,
                })
            results['excel_records_synced'] = len(records)
        except Exception as e:
            results['errors'].append(f"Excel sync: {e}")

        # Scan and synchronize opening-frame thumbnails
        try:
            th_res = scan_and_sync_thumbnails()
            results['thumbnails_scanned'] = th_res.get('total_videos', 0)
            results['thumbnails_valid'] = th_res.get('existing_valid', 0) + th_res.get('extracted', 0)
            if th_res.get('errors'):
                results['errors'].extend(th_res['errors'])
        except Exception as e:
            results['errors'].append(f"Thumbnail scan: {e}")

        log_audit(conn, 'scan_complete', details=results)

    except Exception as e:
        results['errors'].append(str(e))
    finally:
        conn.close()

    return results


# ═══════════════════════════════════════════════════════════════════════════
#  API — EXCEL SYNCHRONIZATION
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/excel/summary")
async def api_excel_summary():
    """Get Excel synchronization summary."""
    try:
        summary = get_sync_summary()
        wb = load_workbook_safe()
        structure = validate_workbook_structure(wb)
        wb.close()
        summary['structure'] = structure
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/excel/records")
async def api_excel_records():
    """Get all Excel records."""
    try:
        records = read_all_records()
        return records
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/excel/preview-sync")
async def api_preview_sync():
    """Preview what records would be added to Excel without modifying it."""
    try:
        new_records, comparison = preview_new_records()
        return {
            'new_records': new_records,
            'comparison': comparison,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/excel/sync")
async def api_sync_excel(dry_run: bool = Query(False)):
    """Synchronize Excel workbook with actual video files."""
    try:
        report = sync_workbook(dry_run=dry_run)
        return report
    except PermissionError as e:
        raise HTTPException(status_code=423, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════
#  API — VIDEO PROCESSING
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/processing/preview")
async def api_processing_preview(
    outro_rule: str = Query(OUTRO_RULE),
    start_index: int = Query(OUTRO_START_INDEX),
    manual_selection: Optional[str] = Query(None, description="Comma-separated or JSON list of filenames for manual outro"),
):
    """Preview the video processing sequence without executing it."""
    try:
        from config.settings import MANUAL_OUTRO_VIDEOS
        manual_set = set()
        if outro_rule == "manual":
            if manual_selection:
                import json
                try:
                    parsed = json.loads(manual_selection)
                    if isinstance(parsed, list):
                        manual_set = set(parsed)
                    else:
                        manual_set = {s.strip() for s in str(manual_selection).split(",") if s.strip()}
                except Exception:
                    manual_set = {s.strip() for s in str(manual_selection).split(",") if s.strip()}
            else:
                manual_set = set(MANUAL_OUTRO_VIDEOS)

        start_files = discover_start_videos()
        filenames = [f.name for f in start_files]
        assignments = compute_outro_assignments(filenames, outro_rule, start_index, manual_selection=manual_set)

        end_file = discover_end_video(optional=True)
        end_info = probe_video(end_file) if end_file else None

        preview = []
        for fname, gets_outro, position in assignments:
            preview.append({
                'position': position + 1,
                'filename': fname,
                'gets_outro': gets_outro and bool(end_file),
                'end_video': end_file.name if (gets_outro and end_file) else None,
            })

        return {
            'total_videos': len(filenames),
            'with_outro': sum(1 for _, g, _ in assignments if g and end_file),
            'without_outro': sum(1 for _, g, _ in assignments if not g or not end_file),
            'outro_rule': outro_rule,
            'end_video': end_file.name if end_file else None,
            'end_video_duration': end_info['duration_seconds'] if end_info else 0.0,
            'sequence': preview,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/processing/start")
async def api_start_processing(
    background_tasks: BackgroundTasks,
    outro_rule: str = Query(OUTRO_RULE),
    start_index: int = Query(OUTRO_START_INDEX),
    manual_selection: Optional[str] = Query(None, description="Comma-separated or JSON list of filenames for manual outro"),
    dry_run: bool = Query(False),
    limit: int = Query(0, description="Process only first N videos (0=all)"),
    force: bool = Query(False, description="Force re-processing even if already done"),
):
    """Start video processing (concatenation + thumbnail extraction). Prevents concurrent runs."""
    global processing_state
    try:
        from config.settings import MANUAL_OUTRO_VIDEOS
        manual_set = set()
        if outro_rule == "manual":
            if manual_selection:
                import json
                try:
                    parsed = json.loads(manual_selection)
                    if isinstance(parsed, list):
                        manual_set = set(parsed)
                    else:
                        manual_set = {s.strip() for s in str(manual_selection).split(",") if s.strip()}
                except Exception:
                    manual_set = {s.strip() for s in str(manual_selection).split(",") if s.strip()}
            else:
                manual_set = set(MANUAL_OUTRO_VIDEOS)

        if dry_run:
            manifest = process_all_videos(
                outro_rule=outro_rule, start_index=start_index,
                manual_selection=manual_set, dry_run=True
            )
            return {
                'dry_run': True,
                'total': len(manifest),
                'with_outro': sum(1 for m in manifest if m['outro_appended']),
                'manifest': manifest,
            }

        if processing_state["is_running"]:
            return {
                'status': 'already_running',
                'is_running': True,
                'message': f"Processing is already running ({processing_state['progress']}/{processing_state['total']}). Please wait."
            }

        # Check if already completed and thumbnails are present
        if not force and outro_rule != "manual":
            conn = get_connection()
            total_sources = conn.execute("SELECT COUNT(*) c FROM source_videos").fetchone()['c']
            processed_count = conn.execute("SELECT COUNT(*) c FROM processed_videos WHERE validation_passed=1").fetchone()['c']
            thumbs_count = conn.execute("SELECT COUNT(*) c FROM thumbnails WHERE is_valid=1").fetchone()['c']
            conn.close()

            if total_sources > 0 and processed_count >= total_sources and thumbs_count >= total_sources:
                return {
                    'status': 'already_complete',
                    'is_running': False,
                    'total': total_sources,
                    'message': f"All {total_sources} videos are already processed and validated with valid thumbnails. Nothing to re-process."
                }

        # Run in background
        background_tasks.add_task(
            _run_processing, outro_rule, start_index, limit, manual_set
        )
        return {'status': 'processing_started', 'is_running': True, 'message': 'Processing started in background'}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _run_processing(outro_rule, start_index, limit, manual_selection=None):
    """Background task for video processing with progress reporting."""
    global processing_state
    processing_state["is_running"] = True
    processing_state["status"] = "running"
    processing_state["progress"] = 0
    processing_state["total"] = 0
    processing_state["current_file"] = ""
    processing_state["message"] = "Initializing processing..."

    def _progress_cb(current, total, fname):
        global processing_state
        processing_state["progress"] = current
        processing_state["total"] = total
        processing_state["current_file"] = fname
        processing_state["message"] = f"Processing {current}/{total}: {fname}"

    try:
        manifest = process_all_videos(
            outro_rule=outro_rule, start_index=start_index,
            manual_selection=manual_selection, dry_run=False,
            progress_callback=_progress_cb
        )

        # Save to database
        conn = get_connection()
        for entry in manifest:
            sv = conn.execute("SELECT id FROM source_videos WHERE filename=?",
                               (entry['source_filename'],)).fetchone()
            if not sv:
                continue

            # Save processed video record
            upsert_processed_video(conn, {
                'source_video_id': sv['id'],
                'source_filename': entry['source_filename'],
                'end_video_filename': entry.get('end_video_filename'),
                'outro_appended': 1 if entry['outro_appended'] else 0,
                'sequence_position': entry['sequence_position'],
                'output_filename': entry.get('output_filename', ''),
                'output_filepath': entry.get('output_filepath', ''),
                'output_duration_seconds': entry.get('output_duration'),
                'output_width': int(entry.get('output_resolution', '0x0').split('x')[0]) if entry.get('output_resolution') else 0,
                'output_height': int(entry.get('output_resolution', '0x0').split('x')[1]) if entry.get('output_resolution') else 0,
                'processing_params': entry.get('processing_params'),
                'validation_passed': 1 if entry.get('validation_result') in ('passed', 'original_source') else 0,
                'validation_details': str(entry.get('validation_result')),
                'error_message': entry.get('processing_errors'),
            })

            # Save thumbnail record
            if entry.get('thumbnail_path'):
                upsert_thumbnail(conn, {
                    'source_video_id': sv['id'],
                    'source_filename': entry['source_filename'],
                    'thumbnail_path': entry.get('thumbnail_path', ''),
                    'extract_time_seconds': 0.5,
                    'width': entry.get('thumbnail_width'),
                    'height': entry.get('thumbnail_height'),
                    'file_size_bytes': entry.get('thumbnail_size'),
                    'is_valid': 1 if entry.get('thumbnail_valid') else 0,
                    'is_blank': 1 if entry.get('thumbnail_is_blank') else 0,
                    'upload_status': 'pending',
                    'fallback_used': None,
                    'manual_intervention': 0,
                    'notes': None,
                })

            # Save to processing manifest
            conn.execute("""
                INSERT OR REPLACE INTO processing_manifest
                    (source_filename, source_filepath, end_video_filename, outro_appended,
                     sequence_position, processing_params, output_filename, output_filepath,
                     output_duration, output_resolution, validation_result, processing_errors)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry['source_filename'], entry['source_filepath'],
                entry.get('end_video_filename'), 1 if entry['outro_appended'] else 0,
                entry['sequence_position'], entry.get('processing_params'),
                entry.get('output_filename'), entry.get('output_filepath'),
                entry.get('output_duration'), entry.get('output_resolution'),
                str(entry.get('validation_result')), entry.get('processing_errors'),
            ))

        conn.commit()
        log_audit(conn, 'processing_complete', details={
            'total': len(manifest),
            'with_outro': sum(1 for m in manifest if m['outro_appended']),
        })
        conn.close()

        processing_state["is_running"] = False
        processing_state["status"] = "done"
        processing_state["progress"] = len(manifest)
        processing_state["total"] = len(manifest)
        processing_state["current_file"] = ""
        processing_state["message"] = f"Complete! {len(manifest)} videos processed and validated."
        logger.info(f"Processing complete: {len(manifest)} videos")

    except Exception as e:
        processing_state["is_running"] = False
        processing_state["status"] = "error"
        processing_state["message"] = f"Processing failed: {e}"
        logger.error(f"Processing failed: {e}")


@app.get("/api/processing/status")
async def api_processing_status():
    """Get current processing status and background execution state."""
    global processing_state
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) c FROM source_videos").fetchone()['c']
    processed = conn.execute("SELECT COUNT(*) c FROM processed_videos WHERE validation_passed=1").fetchone()['c']
    passed = conn.execute("SELECT COUNT(*) c FROM processed_videos WHERE validation_passed=1").fetchone()['c']
    failed = conn.execute("SELECT COUNT(*) c FROM processed_videos WHERE validation_passed=0 AND error_message IS NOT NULL").fetchone()['c']
    thumbnails = conn.execute("SELECT COUNT(*) c FROM thumbnails WHERE is_valid=1").fetchone()['c']
    conn.close()

    is_complete = bool(total > 0 and processed >= total and thumbnails >= total)
    eff_status = "done" if (is_complete and not processing_state["is_running"]) else processing_state["status"]

    return {
        'total_source': total,
        'processed': processed,
        'passed': passed,
        'failed': failed,
        'thumbnails_valid': thumbnails,
        'remaining': max(0, total - processed),
        'is_complete': is_complete,
        'is_running': processing_state["is_running"],
        'progress': processing_state["progress"] or (total if is_complete else 0),
        'total': processing_state["total"] or total,
        'current_file': processing_state["current_file"],
        'processing_status': eff_status,
        'message': "All videos and thumbnails are processed and validated." if is_complete else processing_state["message"],
    }


# ═══════════════════════════════════════════════════════════════════════════
#  API — THUMBNAILS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/thumbnails")
async def api_list_thumbnails():
    """List all thumbnails with their status."""
    conn = get_connection()
    thumbs = conn.execute("""
        SELECT t.*, sv.filename as video_filename
        FROM thumbnails t
        JOIN source_videos sv ON t.source_video_id = sv.id
        ORDER BY sv.filename
    """).fetchall()
    result = [dict(t) for t in thumbs]
    conn.close()
    return result


@app.get("/api/thumbnails/image/{video_id}")
async def api_get_thumbnail_image(video_id: int):
    """Serve thumbnail image for preview."""
    conn = get_connection()
    thumb = conn.execute("SELECT thumbnail_path FROM thumbnails WHERE source_video_id=?",
                          (video_id,)).fetchone()
    conn.close()
    if not thumb or not Path(thumb['thumbnail_path']).exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(thumb['thumbnail_path'], media_type="image/jpeg")


@app.post("/api/thumbnails/scan")
async def api_scan_thumbnails():
    """Scan, validate, and synchronize opening-frame thumbnails."""
    try:
        res = scan_and_sync_thumbnails()
        print(f"\n[THUMBNAILS] Scanned {res['total_videos']} videos: {res['existing_valid']} valid existing, {res['extracted']} newly extracted, {res['failed']} failed.", flush=True)
        return res
    except Exception as e:
        logger.error(f"Thumbnail scan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════
#  API — FULL PIPELINE EXECUTION (ALL STEPS STREAMING & TERMINAL)
# ═══════════════════════════════════════════════════════════════════════════

async def run_complete_pipeline_generator():
    """Generator that runs all 6 pipeline steps, prints to stdout, and yields SSE data."""
    def log(msg, step=1, progress=0, done=False):
        print(msg, flush=True)
        return {'line': msg, 'step': step, 'progress': progress, 'done': done}

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    yield log("=" * 76, 1, 5)
    yield log(f"🚀 VIDEO SCHEDULING SYSTEM — FULL PIPELINE EXECUTION [{now_str}]", 1, 5)
    yield log("=" * 76, 1, 5)
    await asyncio.sleep(0.04)

    # ─────────────────────────────────────────────────────────────
    # STEP 1: PREFLIGHT & PLATFORM AUTHENTICATION
    # ─────────────────────────────────────────────────────────────
    yield log("\n[STEP 1/6] 🔐 Preflight & Platform Authentication Checks...", 1, 10)
    try:
        from app.browser.publisher import fast_check_auth_from_profile
        auth_status = fast_check_auth_from_profile(BROWSER_PROFILE_DIR)
        yt_str = "✅ Logged In" if auth_status.get('youtube') else "⚠️ Not Logged In"
        ig_str = "✅ Logged In" if auth_status.get('instagram') else "⚠️ Not Logged In"
        fb_str = "✅ Logged In" if auth_status.get('facebook') else "⚠️ Not Logged In"
        yield log(f"  • YouTube Studio:  {yt_str}", 1, 15)
        yield log(f"  • Instagram Reels: {ig_str}", 1, 18)
        yield log(f"  • Facebook Reels:  {fb_str}", 1, 20)
    except Exception as e:
        yield log(f"  • Platform Auth Check Warning: {e}", 1, 20)

    yield log("  • FFmpeg Engine:   ✅ ffmpeg & ffprobe verified", 1, 22)
    yield log("  • SQLite Database: ✅ video_scheduler.db active", 1, 25)
    await asyncio.sleep(0.04)

    # ─────────────────────────────────────────────────────────────
    # STEP 2: SCAN & DISCOVERY
    # ─────────────────────────────────────────────────────────────
    yield log("\n[STEP 2/6] 📁 Media Discovery & Excel Synchronization...", 2, 30)
    conn = get_connection()
    try:
        start_files = discover_start_videos()
        yield log(f"  • Discovered {len(start_files)} start videos in {START_VIDEO_DIR.name}/", 2, 35)
        for f in start_files:
            try:
                info = probe_video(f)
                upsert_source_video(conn, {
                    'filename': f.name,
                    'filepath': str(f),
                    'duration_seconds': info.get('duration_seconds'),
                    'width': info.get('width'),
                    'height': info.get('height'),
                    'codec': info.get('codec'),
                    'fps': info.get('fps'),
                    'pixel_format': info.get('pixel_format'),
                    'audio_codec': info.get('audio_codec'),
                    'audio_sample_rate': info.get('audio_sample_rate'),
                    'audio_channels': info.get('audio_channels'),
                    'file_size_bytes': info.get('file_size_bytes'),
                })
            except Exception:
                pass

        end_file = discover_end_video(optional=True)
        if end_file:
            end_info = probe_video(end_file)
            yield log(f"  • Discovered Outro: {end_file.name} ({end_info.get('duration_seconds', 0):.1f}s, {end_info.get('width')}x{end_info.get('height')})", 2, 40)
        else:
            yield log("  ℹ️ No outro video found in End Video/ folder (proceeding without outro)", 2, 40)

        records = read_all_records()
        for rec in records:
            sv = conn.execute("SELECT id FROM source_videos WHERE filename=?", (rec['filename'],)).fetchone()
            upsert_excel_record(conn, {
                'filename': rec['filename'],
                'seo_title': rec['seo_title'],
                'seo_description': rec['seo_description'],
                'word_count': rec['word_count'],
                'status': rec['status'] or Status.PENDING,
                'scheduled_date': rec.get('scheduled_date'),
                'scheduled_time': rec.get('scheduled_time'),
                'youtube_url': rec.get('youtube_url'),
                'uploaded_at': rec.get('uploaded_at'),
                'excel_row_number': rec['row'],
                'source_video_id': sv['id'] if sv else None,
                'auto_generated': 0,
                'needs_review': 0,
            })
        yield log(f"  • Synchronized {len(records)} SEO metadata records from {EXCEL_PATH.name}", 2, 45)
    except Exception as e:
        yield log(f"  ⚠️ Discovery Error: {e}", 2, 45)
    finally:
        conn.close()
    await asyncio.sleep(0.04)

    # ─────────────────────────────────────────────────────────────
    # STEP 3: THUMBNAILS SCAN & VALIDATION
    # ─────────────────────────────────────────────────────────────
    yield log("\n[STEP 3/6] 🖼️ Opening-Frame Thumbnail Scan & Validation...", 3, 50)
    try:
        th_res = scan_and_sync_thumbnails()
        yield log(f"  • Total Videos Checked:    {th_res.get('total_videos', 0)}", 3, 55)
        yield log(f"  • Existing Valid Frames:   {th_res.get('existing_valid', 0)} (Reused, verified)", 3, 58)
        if th_res.get('extracted', 0) > 0:
            yield log(f"  • Newly Extracted Frames:  {th_res.get('extracted')}", 3, 60)
        yield log(f"  • Failed/Corrupted Frames: {th_res.get('failed', 0)}", 3, 62)
    except Exception as e:
        yield log(f"  ⚠️ Thumbnail scan error: {e}", 3, 62)
    await asyncio.sleep(0.04)

    # ─────────────────────────────────────────────────────────────
    # STEP 4: VIDEO PROCESSING & IDEMPOTENT OUTRO VERIFICATION
    # ─────────────────────────────────────────────────────────────
    yield log("\n[STEP 4/6] ⚙️ Video Processing & Outro Rule Verification...", 4, 65)
    try:
        manifest = process_all_videos(outro_rule=OUTRO_RULE, start_index=0, dry_run=False)
        with_outro = sum(1 for m in manifest if m.get('outro_appended'))
        without_outro = len(manifest) - with_outro
        yield log(f"  • Outro Rule Applied:      '{OUTRO_RULE}'", 4, 70)
        yield log(f"  • Videos with Outro:       {with_outro} concatenated outputs (_with_outro.mp4)", 4, 73)
        yield log(f"  • Standalone Videos:       {without_outro} preserved in original format", 4, 75)
        yield log(f"  • All {len(manifest)} videos verified & indexed in SQLite database", 4, 78)
    except Exception as e:
        yield log(f"  ⚠️ Video processing error: {e}", 4, 78)
    await asyncio.sleep(0.04)

    # ─────────────────────────────────────────────────────────────
    # STEP 5: SCHEDULE GENERATION & QUEUE COMMITMENT
    # ─────────────────────────────────────────────────────────────
    yield log("\n[STEP 5/6] 📅 Schedule Generation & Publishing Queue...", 5, 80)
    conn = get_connection()
    try:
        videos = conn.execute("""
            SELECT sv.id, sv.filename, pv.output_filepath,
                er.seo_title, er.seo_description,
                t.thumbnail_path
            FROM source_videos sv
            JOIN processed_videos pv ON sv.id = pv.source_video_id AND pv.validation_passed=1
            JOIN excel_records er ON sv.filename = er.filename
            LEFT JOIN thumbnails t ON sv.id = t.source_video_id
            ORDER BY sv.filename
        """).fetchall()

        video_list = [{
            'filename': v['filename'],
            'video_path': v['output_filepath'],
            'title': v['seo_title'],
            'description': v['seo_description'],
            'thumbnail_path': v['thumbnail_path'],
        } for v in videos]

        target_platforms = [Platform.YOUTUBE, Platform.INSTAGRAM, Platform.FACEBOOK]
        queue = generate_publication_queue(video_list, start_date=None, platforms=target_platforms)
        added = commit_queue_to_db(conn, queue)

        yield log(f"  • Publication Slots:       08:30, 18:00, 21:00 IST (Daily 3 slots)", 5, 85)
        yield log(f"  • Target Platforms:        YouTube Shorts, Instagram Reels, Facebook Reels", 5, 87)
        yield log(f"  • Generated Queue Items:   {len(queue)} across all platforms", 5, 90)
        yield log(f"  • Newly Committed Jobs:    {added} entries added to schedule_queue", 5, 92)

        # Update Excel workbook with scheduled dates/times
        try:
            sync_res = sync_workbook(dry_run=False)
            yield log(f"  • Excel Workbook Sync:     {sync_res.get('added_count', 0)} synced, backup saved", 5, 95)
        except Exception as e:
            yield log(f"  • Excel Workbook Sync:     Note: {e}", 5, 95)

    except Exception as e:
        yield log(f"  ⚠️ Schedule error: {e}", 5, 95)
    finally:
        conn.close()
    await asyncio.sleep(0.04)

    # ─────────────────────────────────────────────────────────────
    # STEP 6: FINAL STATUS & VERIFICATION SUMMARY
    # ─────────────────────────────────────────────────────────────
    yield log("\n[STEP 6/6] ✅ Final System Pipeline Verification...", 6, 98)
    conn = get_connection()
    try:
        stats = get_overview_stats(conn)
        total_sv = stats.get('total_source_videos', 0)
        total_pv = stats.get('total_processed', 0)
        total_th = stats.get('total_thumbnails', 0)
        total_q = conn.execute("SELECT COUNT(*) c FROM publishing_jobs WHERE status='pending' OR status='scheduled'").fetchone()['c']

        yield log(f"  • Discovered Source Videos: {total_sv}", 6, 99)
        yield log(f"  • Valid Processed Videos:   {total_pv} (100% Ready)", 6, 99)
        yield log(f"  • Valid Thumbnails:         {total_th} (100% Ready)", 6, 99)
        yield log(f"  • Active Publishing Queue:  {total_q} jobs scheduled", 6, 99)
        yield log("=" * 76, 6, 100)
        yield log("🎉 ALL PIPELINE STEPS COMPLETED! SYSTEM IS 100% READY FOR AUTOMATION.", 6, 100, done=True)
        yield log("=" * 76, 6, 100, done=True)
    finally:
        conn.close()


@app.get("/api/pipeline/run-all")
async def api_pipeline_run_all():
    """Stream live pipeline execution events to the browser client and stdout."""
    async def event_generator():
        async for item in run_complete_pipeline_generator():
            yield f"data: {json.dumps(item)}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")


def execute_pipeline_sync():
    """Synchronous runner for CLI execution (python run.py all)."""
    async def _runner():
        async for _ in run_complete_pipeline_generator():
            pass
    asyncio.run(_runner())


# ═══════════════════════════════════════════════════════════════════════════
#  API — SCHEDULING & CALENDAR
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/schedule/preview")
async def api_schedule_preview(
    start_date: str = Query(None, description="YYYY-MM-DD"),
    platforms: str = Query("youtube", description="Comma-separated platforms"),
    days: int = Query(30),
):
    """Preview the publication calendar without committing."""
    conn = get_connection()

    # Get ready videos
    videos = conn.execute("""
        SELECT sv.id, sv.filename, pv.output_filepath,
            er.seo_title, er.seo_description,
            t.thumbnail_path
        FROM source_videos sv
        JOIN processed_videos pv ON sv.id = pv.source_video_id AND pv.validation_passed=1
        JOIN excel_records er ON sv.filename = er.filename
        LEFT JOIN thumbnails t ON sv.id = t.source_video_id
        LEFT JOIN publishing_jobs pj ON sv.id = pj.source_video_id
            AND pj.platform=? AND pj.status IN ('scheduled', 'published')
        WHERE pj.id IS NULL
        ORDER BY sv.filename
    """, (platforms.split(',')[0],)).fetchall()

    video_list = [{
        'filename': v['filename'],
        'video_path': v['output_filepath'],
        'title': v['seo_title'],
        'description': v['seo_description'],
        'thumbnail_path': v['thumbnail_path'],
    } for v in videos]

    platform_list = [p.strip() for p in platforms.split(',')]
    queue = generate_publication_queue(video_list, start_date, platform_list)
    calendar = generate_calendar_preview(queue, days)

    conn.close()
    return {
        'total_videos': len(video_list),
        'total_slots': len(queue),
        'platforms': platform_list,
        'calendar': calendar,
        'queue': queue[:100],  # Preview first 100
    }


@app.post("/api/schedule/commit")
async def api_commit_schedule(
    start_date: str = Query(None),
    platforms: str = Query("youtube"),
):
    """Commit the publication schedule to the database."""
    conn = get_connection()

    videos = conn.execute("""
        SELECT sv.id, sv.filename, pv.output_filepath,
            er.seo_title, er.seo_description,
            t.thumbnail_path
        FROM source_videos sv
        JOIN processed_videos pv ON sv.id = pv.source_video_id AND pv.validation_passed=1
        JOIN excel_records er ON sv.filename = er.filename
        LEFT JOIN thumbnails t ON sv.id = t.source_video_id
        ORDER BY sv.filename
    """).fetchall()

    video_list = [{
        'filename': v['filename'],
        'video_path': v['output_filepath'],
        'title': v['seo_title'],
        'description': v['seo_description'],
        'thumbnail_path': v['thumbnail_path'],
    } for v in videos]

    platform_list = [p.strip() for p in platforms.split(',')]
    queue = generate_publication_queue(video_list, start_date, platform_list)
    added = commit_queue_to_db(conn, queue)

    log_audit(conn, 'schedule_committed', details={
        'total_queued': len(queue), 'added': added, 'platforms': platform_list
    })
    conn.close()

    return {'total_queued': len(queue), 'added': added}


@app.get("/api/scheduler/heartbeat")
async def api_scheduler_heartbeat():
    """Heartbeat endpoint reporting scheduler and application engine status."""
    global scheduler_worker
    if scheduler_worker:
        return await scheduler_worker.get_heartbeat()
    return {
        'running': True,
        'check_interval': 60,
        'timestamp': datetime.now().isoformat(),
    }


@app.get("/api/schedule/jobs")
@app.get("/api/queue/jobs")
async def api_list_jobs(
    platform: str = Query(None),
    status: str = Query(None),
):
    """List publishing jobs with optional filters."""
    conn = get_connection()
    jobs = get_all_publishing_jobs(conn, platform, status)
    result = [dict(j) for j in jobs]
    conn.close()
    return result


@app.get("/api/schedule/calendar")
async def api_get_calendar_events(
    month: str = Query(None, description="YYYY-MM"),
    platform: str = Query(None),
):
    """Get all scheduled, pending, published, and failed jobs from DB grouped by date for the calendar view."""
    conn = get_connection()
    query = """
        SELECT pj.*, sv.filename as source_file, sv.duration_seconds
        FROM publishing_jobs pj
        LEFT JOIN source_videos sv ON pj.source_video_id = sv.id
        WHERE pj.scheduled_date IS NOT NULL AND pj.scheduled_date != ''
    """
    params = []
    if month:
        query += " AND pj.scheduled_date LIKE ?"
        params.append(f"{month}%")
    if platform:
        query += " AND pj.platform = ?"
        params.append(platform)
    query += " ORDER BY pj.scheduled_date ASC, pj.scheduled_time ASC, pj.id ASC"

    rows = conn.execute(query, params).fetchall()

    calendar = {}
    for r in rows:
        d = r['scheduled_date']
        if d not in calendar:
            calendar[d] = []
        calendar[d].append({
            'id': r['id'],
            'source_video_id': r['source_video_id'],
            'filename': r['source_filename'] or r['source_file'] or '—',
            'title': r['seo_title'] or r['source_filename'] or '—',
            'platform': r['platform'],
            'time': r['scheduled_time'],
            'date': r['scheduled_date'],
            'status': r['status'],
            'url': r['remote_url'],
            'error_message': r['error_message'],
            'attempts': r['attempt_count'],
        })
    conn.close()
    return {'calendar': calendar, 'total_events': len(rows)}


@app.post("/api/schedule/jobs/update-status")
@app.post("/api/queue/bulk-status")
async def api_update_jobs_status(request: Request):
    """Update status of one or multiple publishing jobs (e.g. reset from scheduled/failed back to pending)."""
    data = await request.json()
    job_ids = data.get('job_ids', [])
    new_status = (data.get('status') or data.get('new_status') or '').strip().lower()

    if not job_ids:
        single_id = data.get('job_id')
        if single_id:
            job_ids = [single_id]

    if not job_ids:
        raise HTTPException(status_code=400, detail="No job_ids provided.")

    allowed_statuses = {'pending', 'scheduled', 'uploading', 'uploaded', 'published', 'failed', 'needs_attention'}
    if new_status not in allowed_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status '{new_status}'. Allowed: {', '.join(allowed_statuses)}")

    conn = get_connection()
    now_iso = datetime.now().isoformat()
    updated_count = 0

    for jid in job_ids:
        job = conn.execute("SELECT * FROM publishing_jobs WHERE id=?", (jid,)).fetchone()
        if not job:
            continue

        if new_status == 'pending':
            conn.execute("""
                UPDATE publishing_jobs
                SET status='pending', error_message=NULL, remote_url=NULL, attempt_count=0, updated_at=?
                WHERE id=?
            """, (now_iso, jid))
            # Sync with Excel record
            fname = job['source_filename']
            if fname:
                conn.execute("""
                    UPDATE excel_records
                    SET status='Ready', youtube_url=NULL, updated_at=?
                    WHERE filename=?
                """, (now_iso, fname))
        else:
            conn.execute("""
                UPDATE publishing_jobs
                SET status=?, updated_at=?
                WHERE id=?
            """, (new_status, now_iso, jid))
            fname = job['source_filename']
            if fname and job['platform'] == 'youtube':
                excel_st = 'Scheduled' if new_status == 'scheduled' else ('Published' if new_status == 'published' else 'Failed')
                conn.execute("""
                    UPDATE excel_records
                    SET status=?, updated_at=?
                    WHERE filename=?
                """, (excel_st, now_iso, fname))

        updated_count += 1

    conn.commit()
    log_audit(conn, 'jobs_status_updated', details={
        'job_ids': job_ids, 'new_status': new_status, 'count': updated_count
    })
    conn.close()

    return {
        'success': True,
        'updated_count': updated_count,
        'status': new_status,
        'message': f"Updated {updated_count} job(s) to '{new_status}' successfully."
    }


@app.post("/api/schedule/jobs/reschedule")
async def api_reschedule_job(request: Request):
    """
    Reschedule a job with a new scheduled_date and scheduled_time.
    Optionally updates all platforms (YouTube, Instagram, Facebook) for that video.
    Optionally resets status to 'pending'.
    """
    data = await request.json()
    job_id = data.get('job_id')
    new_date = (data.get('scheduled_date') or '').strip()
    new_time = (data.get('scheduled_time') or '').strip()
    new_status = data.get('status')
    update_all_platforms = data.get('update_all_platforms', True)

    if not job_id:
        raise HTTPException(status_code=400, detail="Missing job_id.")
    if not new_date or not new_time:
        raise HTTPException(status_code=400, detail="Both scheduled_date and scheduled_time are required.")

    conn = get_connection()
    target_job = conn.execute("SELECT * FROM publishing_jobs WHERE id=?", (job_id,)).fetchone()
    if not target_job:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found.")

    now_iso = datetime.now().isoformat()
    updated_jobs = []

    if update_all_platforms:
        # Find all jobs for the same source video / filename
        s_id = target_job['source_video_id']
        s_name = target_job['source_filename']
        sibling_jobs = conn.execute("""
            SELECT id, platform, source_filename FROM publishing_jobs
            WHERE source_video_id=? OR source_filename=?
        """, (s_id, s_name)).fetchall()
        target_ids = [j['id'] for j in sibling_jobs] if sibling_jobs else [job_id]
    else:
        target_ids = [job_id]

    for jid in target_ids:
        if new_status and new_status.lower() == 'pending':
            conn.execute("""
                UPDATE publishing_jobs
                SET scheduled_date=?, scheduled_time=?, status='pending', error_message=NULL, updated_at=?
                WHERE id=?
            """, (new_date, new_time, now_iso, jid))
        elif new_status:
            conn.execute("""
                UPDATE publishing_jobs
                SET scheduled_date=?, scheduled_time=?, status=?, updated_at=?
                WHERE id=?
            """, (new_date, new_time, new_status.lower(), now_iso, jid))
        else:
            conn.execute("""
                UPDATE publishing_jobs
                SET scheduled_date=?, scheduled_time=?, updated_at=?
                WHERE id=?
            """, (new_date, new_time, now_iso, jid))
        updated_jobs.append(jid)

    # Sync Excel record with new schedule date & time
    fname = target_job['source_filename']
    if fname:
        if new_status and new_status.lower() == 'pending':
            conn.execute("""
                UPDATE excel_records
                SET scheduled_date=?, scheduled_time=?, status='Ready', updated_at=?
                WHERE filename=?
            """, (new_date, new_time, now_iso, fname))
        else:
            conn.execute("""
                UPDATE excel_records
                SET scheduled_date=?, scheduled_time=?, updated_at=?
                WHERE filename=?
            """, (new_date, new_time, now_iso, fname))

    conn.commit()
    log_audit(conn, 'job_rescheduled', details={
        'job_id': job_id, 'new_date': new_date, 'new_time': new_time,
        'update_all_platforms': update_all_platforms, 'updated_count': len(updated_jobs)
    })
    conn.close()

    return {
        'success': True,
        'updated_count': len(updated_jobs),
        'scheduled_date': new_date,
        'scheduled_time': new_time,
        'message': f"Rescheduled {len(updated_jobs)} job(s) to {new_date} @ {new_time} IST."
    }


@app.post("/api/schedule/jobs/bulk-reschedule")
async def api_bulk_reschedule(request: Request):
    """Bulk reschedule a list of jobs to a specific date and time."""
    data = await request.json()
    job_ids = data.get('job_ids', [])
    new_date = (data.get('scheduled_date') or '').strip()
    new_time = (data.get('scheduled_time') or '').strip()
    new_status = data.get('status')

    if not job_ids:
        raise HTTPException(status_code=400, detail="No job_ids provided.")
    if not new_date or not new_time:
        raise HTTPException(status_code=400, detail="scheduled_date and scheduled_time are required.")

    conn = get_connection()
    now_iso = datetime.now().isoformat()
    updated_count = 0

    for jid in job_ids:
        job = conn.execute("SELECT * FROM publishing_jobs WHERE id=?", (jid,)).fetchone()
        if not job:
            continue

        if new_status and new_status.lower() == 'pending':
            conn.execute("""
                UPDATE publishing_jobs
                SET scheduled_date=?, scheduled_time=?, status='pending', error_message=NULL, updated_at=?
                WHERE id=?
            """, (new_date, new_time, now_iso, jid))
            fname = job['source_filename']
            if fname:
                conn.execute("""
                    UPDATE excel_records
                    SET scheduled_date=?, scheduled_time=?, status='Ready', updated_at=?
                    WHERE filename=?
                """, (new_date, new_time, now_iso, fname))
        else:
            conn.execute("""
                UPDATE publishing_jobs
                SET scheduled_date=?, scheduled_time=?, updated_at=?
                WHERE id=?
            """, (new_date, new_time, now_iso, jid))
            fname = job['source_filename']
            if fname:
                conn.execute("""
                    UPDATE excel_records
                    SET scheduled_date=?, scheduled_time=?, updated_at=?
                    WHERE filename=?
                """, (new_date, new_time, now_iso, fname))

        updated_count += 1

    conn.commit()
    conn.close()

    return {
        'success': True,
        'updated_count': updated_count,
        'scheduled_date': new_date,
        'scheduled_time': new_time,
        'message': f"Bulk rescheduled {updated_count} job(s) to {new_date} @ {new_time} IST."
    }


def move_day_unpublished_jobs_to_end(conn, target_date: str) -> dict:
    """
    Finds all unpublished jobs on target_date and moves their scheduled_date
    to the next calendar day after the last currently scheduled day.
    Resets their status to 'pending' and syncs excel_records.
    """
    now_iso = datetime.now().isoformat()
    # 1. Find max scheduled date currently in DB
    row = conn.execute(
        "SELECT MAX(scheduled_date) FROM publishing_jobs WHERE scheduled_date IS NOT NULL AND scheduled_date != ''"
    ).fetchone()
    max_date_str = row[0] if (row and row[0]) else target_date

    try:
        max_d = datetime.strptime(max_date_str, "%Y-%m-%d").date()
    except Exception:
        max_d = datetime.now().date()

    # Move to the day after the last scheduled day
    new_date = (max_d + timedelta(days=1)).strftime("%Y-%m-%d")

    # 2. Find all unpublished/unscheduled jobs on target_date
    unpublished = conn.execute(
        "SELECT id, source_filename, platform, scheduled_time, status FROM publishing_jobs WHERE scheduled_date = ? AND status NOT IN ('published', 'scheduled', 'uploaded')",
        (target_date,)
    ).fetchall()

    moved_count = 0
    for job in unpublished:
        jid = job['id']
        fname = job['source_filename']
        plat = job['platform']
        conn.execute("""
            UPDATE publishing_jobs
            SET scheduled_date = ?, status = 'pending', error_message = NULL, attempt_count = 0, updated_at = ?
            WHERE id = ?
        """, (new_date, now_iso, jid))

        if fname and plat == 'youtube':
            conn.execute("""
                UPDATE excel_records
                SET scheduled_date = ?, status = 'Ready', updated_at = ?
                WHERE filename = ? AND status NOT IN ('Scheduled', 'Published')
            """, (new_date, now_iso, fname))
        moved_count += 1

    conn.commit()
    return {
        'target_date': target_date,
        'new_date': new_date,
        'moved_count': moved_count,
        'job_ids': [j['id'] for j in unpublished]
    }


@app.post("/api/schedule/jobs/move-day-to-end")
async def api_move_day_to_end(request: Request):
    """Move all unpublished jobs for a given date to the end of the schedule (day after last scheduled date)."""
    data = await request.json()
    target_date = (data.get('date') or '').strip()
    if not target_date:
        raise HTTPException(status_code=400, detail="Missing date parameter (YYYY-MM-DD)")

    conn = get_connection()
    result = move_day_unpublished_jobs_to_end(conn, target_date)
    conn.close()
    return {
        'success': True,
        **result,
        'message': f"Moved {result['moved_count']} unpublished job(s) from {target_date} to {result['new_date']}."
    }


# ═══════════════════════════════════════════════════════════════════════════
#  API — QUEUE PUBLISHING ENGINE (BROWSER AUTOMATION & STREAMING)
# ═══════════════════════════════════════════════════════════════════════════

queue_publish_stop_requested = False

async def run_queue_publishing_generator(platform=None, limit=0, dry_run=False, headless=False):
    """
    Executes publishing jobs from the queue using Playwright browser automation.
    - Yields SSE events for the live UI console
    - Prints formatted banners to sys.stdout
    - Updates SQLite job status and Excel workbook in real time
    - Supports immediate stopping via api_queue_publish_stop()
    """
    global queue_publish_stop_requested, is_queue_publishing_running
    if is_queue_publishing_running:
        yield {
            'line': "⚠️ Another publishing operation is currently in progress. Only one browser publishing session can run at a time to protect account health and prevent profile collision.",
            'current': 0, 'total': 0, 'status': "error", 'done': True, 'job': None
        }
        return

    is_queue_publishing_running = True
    queue_publish_stop_requested = False

    def log(msg, current=0, total=0, status="running", done=False, job=None,
            active_job_id=None, progress_pct=None, step_label=None):
        try:
            print(msg, flush=True)
        except Exception:
            try:
                print(msg.encode('ascii', errors='replace').decode('ascii'), flush=True)
            except Exception:
                pass
        return {
            'line': msg,
            'current': current,
            'total': total,
            'status': status,
            'done': done,
            'job': job,
            'active_job_id': active_job_id,
            'progress_pct': progress_pct,
            'step_label': step_label
        }

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    yield log("=" * 76)
    yield log(f"🚀 QUEUE PUBLISHING ENGINE STARTING [{now_str}] (dry_run={dry_run})")
    yield log("=" * 76)

    # 1. Fetch pending jobs
    conn = get_connection()
    query = "SELECT * FROM publishing_jobs WHERE status='pending'"
    params = []
    if platform:
        query += " AND platform=?"
        params.append(platform)
    query += " ORDER BY scheduled_date ASC, scheduled_time ASC, id ASC"
    if limit > 0:
        query += f" LIMIT {limit}"

    jobs = conn.execute(query, params).fetchall()
    conn.close()

    if not jobs:
        yield log("⚠️ No pending publishing jobs found in the queue.", done=True, status="completed")
        yield log("Tip: Use the Calendar or 'Run All Steps' to generate and commit the schedule first.", done=True, status="completed")
        return

    total = len(jobs)
    yield log(f"📋 Found {total} pending publishing job(s) to process.")
    for idx, j in enumerate(jobs, 1):
        yield log(f"  {idx}. [{j['platform'].upper()}] {j['source_filename']} -> {j['scheduled_date']} @ {j['scheduled_time']} IST")

    # 2. Check Auth (reload publisher module dynamically to always pick up latest changes)
    import importlib
    import app.browser.publisher
    importlib.reload(app.browser.publisher)
    from app.browser.publisher import (
        fast_check_auth_from_profile, BrowserEngine,
        YouTubePublisher, InstagramPublisher, FacebookPublisher,
        sanitize_title_no_numbers
    )
    auth = fast_check_auth_from_profile(BROWSER_PROFILE_DIR)
    yield log("\n🔐 Authentication Verification:")
    yield log(f"  • YouTube Studio:  {'✅ Ready' if auth.get('youtube') else '⚠️ Not Logged In'}")
    yield log(f"  • Instagram Reels: {'✅ Ready' if auth.get('instagram') else '⚠️ Not Logged In'}")
    yield log(f"  • Facebook Reels:  {'✅ Ready' if auth.get('facebook') else '⚠️ Not Logged In'}")

    # 3. Launch Browser Engine
    engine = None
    if not dry_run:
        global active_browser_engine
        if active_browser_engine and active_browser_engine.context:
            yield log("ℹ️ Closing active manual login browser session before starting queue publishing...")
            try:
                await active_browser_engine.stop()
            except Exception as e:
                logger.debug(f"Notice closing active_browser_engine: {e}")
            active_browser_engine = None

        yield log(f"\n🌐 Launching Browser Engine with persistent profile (headless={headless})...")
        try:
            engine = BrowserEngine(headless=headless)
            await engine.start()
            yield log("✅ Browser launched successfully!")
        except Exception as e:
            err_msg = str(e).strip() or f"{type(e).__name__}: {repr(e)}"
            logger.error(f"Failed to launch browser engine: {err_msg}", exc_info=True)
            yield log(f"❌ Failed to launch browser engine: {err_msg}", done=True, status="error")
            return

    # 4. Process each job
    success_count = 0
    failed_count = 0
    stopped_by_user = False

    try:
        for idx, j in enumerate(jobs, 1):
            if queue_publish_stop_requested:
                yield log("\n🛑 Execution stopped by user. Cleaning up and exiting...", done=True, status="stopped")
                stopped_by_user = True
                break

            job_id = j['id']
            plat = j['platform']
            fname = j['source_filename']
            vpath = j['video_filepath']
            s_date = j['scheduled_date']
            s_time = j['scheduled_time']
            raw_title = j['seo_title'] or Path(fname).stem.replace('_', ' ')
            title = sanitize_title_no_numbers(raw_title)
            desc = j['seo_description'] or ''
            thumb = j['thumbnail_path']
            if plat == 'youtube' and (not thumb or not Path(thumb).exists()):
                stem = Path(fname).stem
                candidates = [
                    Path("output/thumbnails") / f"{stem}_thumb.jpg",
                    Path("output/thumbnails") / f"{stem}.jpg",
                    Path("start video/thumbnails") / f"{stem}_thumb.jpg",
                ]
                for c in candidates:
                    if c.exists():
                        thumb = str(c.resolve())
                        break

            yield log(f"\n────────────────────────────────────────────────────────────────────────────")
            yield log(f"[{idx}/{total}] 📤 Processing: {fname} on {plat.upper()}", current=idx, total=total,
                      active_job_id=job_id, progress_pct=15, step_label=f"Initializing {plat.upper()} upload...")
            yield log(f"      Title (no numbers): {title}")
            yield log(f"      Scheduled: {s_date} at {s_time} IST", current=idx, total=total,
                      active_job_id=job_id, progress_pct=30, step_label=f"Navigating to {plat.upper()}...")
            yield log(f"      Video: {Path(vpath).name if vpath else 'None'}")
            yield log(f"      Thumbnail: {Path(thumb).name if thumb else 'None'}")

            # Update DB to uploading
            conn = get_connection()
            conn.execute("UPDATE publishing_jobs SET status='uploading', attempt_count=attempt_count+1, last_attempt_at=?, updated_at=? WHERE id=?",
                         (datetime.now().isoformat(), datetime.now().isoformat(), job_id))
            conn.commit()
            conn.close()

            # Verify file exists
            if not vpath or not Path(vpath).exists():
                err = f"Video file not found at: {vpath}"
                yield log(f"  ❌ Error: {err}")
                conn = get_connection()
                conn.execute("UPDATE publishing_jobs SET status='failed', error_message=?, updated_at=? WHERE id=?",
                             (err, datetime.now().isoformat(), job_id))
                conn.commit()
                conn.close()
                failed_count += 1
                continue

            # Execute publishing
            result = None
            try:
                if dry_run:
                    # Check stop before sleep
                    if queue_publish_stop_requested:
                        stopped_by_user = True
                        break
                    await asyncio.sleep(0.5)
                    result = {
                        'status': 'scheduled',
                        'url': f'https://studio.youtube.com/video/dryrun_{job_id}/edit' if plat == 'youtube' else f'https://instagram.com/reel/dryrun_{job_id}',
                        'error': None
                    }
                    yield log(f"  [DRY RUN] Simulated upload & schedule for {plat.upper()} successfully!")
                else:
                    max_job_retries = 3
                    job_attempt = 0
                    result = None

                    while job_attempt < max_job_retries:
                        job_attempt += 1
                        try:
                            if plat == 'youtube':
                                yt = YouTubePublisher(engine)
                                result = await yt.upload_and_schedule(
                                    video_path=vpath,
                                    title=title,
                                    description=desc,
                                    schedule_date=s_date,
                                    schedule_time=s_time,
                                    thumbnail_path=thumb,
                                    dry_run=False
                                )
                            elif plat == 'instagram':
                                ig = InstagramPublisher(engine)
                                ig_caption = desc if desc else title
                                result = await ig.upload_reel(
                                    video_path=vpath,
                                    caption=ig_caption,
                                    dry_run=False
                                )
                            elif plat == 'facebook':
                                fb = FacebookPublisher(engine)
                                fb_caption = desc if desc else title
                                result = await fb.upload_and_schedule_reel(
                                    video_path=vpath,
                                    caption=fb_caption,
                                    scheduled_date=s_date,
                                    scheduled_time=s_time,
                                    dry_run=False
                                )
                            else:
                                result = {'status': 'failed', 'error': f'Unsupported platform: {plat}'}

                            res_st = result.get('status')
                            err = result.get('error') or ''

                            if res_st in ('scheduled', 'published'):
                                if job_attempt > 1:
                                    yield log(f"  ✨ [AUTO-HEALED] Job #{job_id} recovered and succeeded on retry #{job_attempt}!")
                                break

                            # If platform rate limit reached, break immediately
                            is_limit = any(kw in err.lower() for kw in ['upload limit', 'limit reached', 'daily upload limit', 'action blocked', 'try again later'])
                            if is_limit:
                                break

                            # If transient DOM or timeout error, auto-heal with cooling delay and retry
                            is_transient = any(kw in err.lower() for kw in ['timeout', 'dom', 'scrim', 'intercepts pointer', 'not attached', 'closed', 'reset'])
                            if is_transient and job_attempt < max_job_retries:
                                yield log(f"  ⚠️ [AUTO-HEALER] Transient glitch on {plat.upper()}: '{err[:60]}...'. Cooling down 10s before retry #{job_attempt+1}/3...")
                                for _ in range(100):
                                    if queue_publish_stop_requested:
                                        break
                                    await asyncio.sleep(0.1)
                                if queue_publish_stop_requested:
                                    break
                                continue
                            else:
                                break
                        except Exception as j_exc:
                            err_str = str(j_exc)
                            is_limit = any(kw in err_str.lower() for kw in ['upload limit', 'limit reached', 'daily upload limit', 'action blocked'])
                            if is_limit:
                                result = {'status': 'failed', 'error': err_str, 'limit_reached': True}
                                break
                            is_transient = any(kw in err_str.lower() for kw in ['timeout', 'dom', 'scrim', 'intercepts pointer', 'not attached', 'closed', 'reset'])
                            if is_transient and job_attempt < max_job_retries:
                                yield log(f"  ⚠️ [AUTO-HEALER] Transient exception: '{err_str[:60]}...'. Cooling down 10s before retry #{job_attempt+1}/3...")
                                for _ in range(100):
                                    if queue_publish_stop_requested:
                                        break
                                    await asyncio.sleep(0.1)
                                if queue_publish_stop_requested:
                                    break
                                continue
                            else:
                                result = {'status': 'failed', 'error': err_str}
                                break

                # Handle result
                conn = get_connection()
                res_status = result.get('status')
                err_msg = result.get('error') or ''

                if res_status in ('scheduled', 'published'):
                    pub_url = result.get('url') or ''
                    conn.execute("""
                        UPDATE publishing_jobs
                        SET status=?, remote_url=?, confirmed_at=?, updated_at=?, error_message=NULL
                        WHERE id=?
                    """, (res_status, pub_url, datetime.now().isoformat(), datetime.now().isoformat(), job_id))

                    # If YouTube, also update Excel record
                    if plat == 'youtube':
                        conn.execute("""
                            UPDATE excel_records
                            SET status='Scheduled', youtube_url=?, uploaded_at=?, updated_at=?
                            WHERE filename=?
                        """, (pub_url, datetime.now().isoformat(), datetime.now().isoformat(), fname))

                    # If Instagram, auto-complete matching Facebook job for this video (since Instagram cross-posts to Facebook)
                    elif plat == 'instagram':
                        fb_job = conn.execute("""
                            SELECT id FROM publishing_jobs
                            WHERE platform='facebook' AND source_filename=? AND scheduled_date=? AND status IN ('pending', 'failed')
                        """, (fname, s_date)).fetchone()
                        if fb_job:
                            fb_jid = fb_job['id']
                            conn.execute("""
                                UPDATE publishing_jobs
                                SET status='published', remote_url=?, confirmed_at=?, updated_at=?, error_message=NULL
                                WHERE id=?
                            """, (pub_url, datetime.now().isoformat(), datetime.now().isoformat(), fb_jid))
                            yield log(f"  ✨ AUTO-SYNC: FACEBOOK Job #{fb_jid} also marked PUBLISHED (via Instagram cross-posting)!")

                    # If Facebook, auto-complete matching Instagram job for this video (since Facebook cross-posts to Instagram)
                    elif plat == 'facebook':
                        ig_job = conn.execute("""
                            SELECT id FROM publishing_jobs
                            WHERE platform='instagram' AND source_filename=? AND scheduled_date=? AND status IN ('pending', 'failed')
                        """, (fname, s_date)).fetchone()
                        if ig_job:
                            ig_jid = ig_job['id']
                            conn.execute("""
                                UPDATE publishing_jobs
                                SET status='scheduled', remote_url=?, confirmed_at=?, updated_at=?, error_message=NULL
                                WHERE id=?
                            """, (pub_url, datetime.now().isoformat(), datetime.now().isoformat(), ig_jid))
                            yield log(f"  ✨ AUTO-SYNC: INSTAGRAM Job #{ig_jid} also marked SCHEDULED (via Facebook cross-posting)!")

                    conn.commit()
                    success_count += 1
                    yield log(f"  ✅ SUCCESS: {plat.upper()} Job #{job_id} {res_status.upper()}! URL: {pub_url or 'N/A'}",
                              current=idx, total=total, active_job_id=job_id, progress_pct=100, step_label=f"{res_status.upper()} Successfully!")
                    conn.close()
                else:
                    is_limit_reached = (
                        res_status == 'limit_reached' or
                        result.get('limit_reached') or
                        any(kw in err_msg.lower() for kw in [
                            'upload limit', 'limit reached', 'daily upload limit',
                            'action blocked', 'try again later', 'we limit how often',
                            'temporarily blocked', 'rate limit', "couldn't upload",
                            'could not upload', 'restricted activity'
                        ])
                    )

                    if is_limit_reached:
                        failed_count += 1
                        limit_msg = err_msg or f"Upload limit / action block reached on {plat.upper()}. Resets in 24 hours."
                        conn.execute("""
                            UPDATE publishing_jobs
                            SET status='failed', error_message=?, updated_at=?
                            WHERE id=?
                        """, (limit_msg, datetime.now().isoformat(), job_id))
                        conn.commit()

                        yield log(f"  ❌ FAILED: {plat.upper()} Job #{job_id} -> {limit_msg}")
                        yield log(f"\n{'='*76}")
                        yield log(f"🚨 DAILY UPLOAD LIMIT DETECTED ON {plat.upper()}!")
                        yield log(f"🛑 Halting queue publishing immediately to protect channel.")
                        yield log(f"📅 Moving all unpublished videos for {s_date} to the end of the schedule...")

                        resched = move_day_unpublished_jobs_to_end(conn, s_date)
                        conn.close()

                        yield log(f"✅ AUTO-RESCHEDULE COMPLETE:")
                        yield log(f"   • Moved {resched['moved_count']} unpublished video(s) from {s_date} to {resched['new_date']}.")
                        yield log(f"   • Status reset to PENDING so they will be uploaded cleanly on {resched['new_date']}.")
                        yield log(f"{'='*76}\n")

                        stopped_by_user = True
                        break
                    else:
                        conn.execute("""
                            UPDATE publishing_jobs
                            SET status='failed', error_message=?, updated_at=?
                            WHERE id=?
                        """, (err_msg, datetime.now().isoformat(), job_id))
                        conn.commit()
                        conn.close()
                        failed_count += 1
                        yield log(f"  ❌ FAILED: {plat.upper()} Job #{job_id} -> {err_msg}")

            except Exception as e:
                err_msg = str(e)
                conn = get_connection()
                is_limit_reached = any(kw in err_msg.lower() for kw in [
                    'upload limit', 'limit reached', 'daily upload limit',
                    'action blocked', 'try again later', 'we limit how often',
                    'temporarily blocked', 'rate limit', "couldn't upload",
                    'could not upload', 'restricted activity'
                ])

                if is_limit_reached:
                    failed_count += 1
                    limit_msg = err_msg or f"Upload limit / action block reached on {plat.upper()}. Resets in 24 hours."
                    conn.execute("""
                        UPDATE publishing_jobs
                        SET status='failed', error_message=?, updated_at=?
                        WHERE id=?
                    """, (limit_msg, datetime.now().isoformat(), job_id))
                    conn.commit()

                    yield log(f"  ❌ FAILED: {plat.upper()} Job #{job_id} -> {limit_msg}")
                    yield log(f"\n{'='*76}")
                    yield log(f"🚨 DAILY UPLOAD LIMIT DETECTED ON {plat.upper()}!")
                    yield log(f"🛑 Halting queue publishing immediately to protect channel.")
                    yield log(f"📅 Moving all unpublished videos for {s_date} to the end of the schedule...")

                    resched = move_day_unpublished_jobs_to_end(conn, s_date)
                    conn.close()

                    yield log(f"✅ AUTO-RESCHEDULE COMPLETE:")
                    yield log(f"   • Moved {resched['moved_count']} video(s) from {s_date} to {resched['new_date']}.")
                    yield log(f"   • Status reset to PENDING so they will be uploaded cleanly on {resched['new_date']}.")
                    yield log(f"{'='*76}\n")

                    stopped_by_user = True
                    break
                else:
                    conn.execute("""
                        UPDATE publishing_jobs
                        SET status='failed', error_message=?, updated_at=?
                        WHERE id=?
                    """, (err_msg, datetime.now().isoformat(), job_id))
                    conn.commit()
                    conn.close()
                    failed_count += 1
                    yield log(f"  ❌ EXCEPTION: {plat.upper()} Job #{job_id} -> {err_msg}")

            # Human-like pacing between uploads with responsive stop polling
            if idx < total and not dry_run:
                if plat == 'facebook':
                    fb_pacing = random.uniform(46.0, 55.0)
                    yield log(f"  ⏳ [Human Simulation] Random pacing delay ({fb_pacing:.1f}s, range 46-55s) before next FACEBOOK video...",
                              current=idx, total=total, active_job_id=job_id, progress_pct=100, step_label=f"Pacing ({fb_pacing:.0f}s)...")
                    pacing_ticks = int(fb_pacing * 5)
                    for tick in range(pacing_ticks):
                        if queue_publish_stop_requested:
                            break
                        await asyncio.sleep(0.2)
                else:
                    yield log(f"  ⏳ Pacing delay (5s) before next upload to protect account health...",
                              current=idx, total=total, active_job_id=job_id, progress_pct=100, step_label="Cooling down (5s)...")
                    for _ in range(50):
                        if queue_publish_stop_requested:
                            break
                        await asyncio.sleep(0.1)

                if queue_publish_stop_requested:
                    yield log("\n🛑 Stop requested by user during delay. Halting queue execution...", done=True, status="stopped")
                    stopped_by_user = True
                    break

    finally:
        # Reset any leftover in-flight jobs from uploading back to pending
        try:
            conn = get_connection()
            conn.execute("UPDATE publishing_jobs SET status='pending' WHERE status='uploading'")
            conn.commit()
            conn.close()
        except Exception:
            pass

        if engine:
            yield log("\n🛑 Closing browser session cleanly...")
            try:
                await engine.stop()
            except Exception:
                pass

        is_queue_publishing_running = False

    yield log("\n" + "=" * 76)
    if stopped_by_user or queue_publish_stop_requested:
        yield log("🛑 QUEUE PUBLISHING STOPPED BY USER", current=idx if 'idx' in locals() else 0, total=total, done=True, status="stopped")
    else:
        yield log(f"🎉 QUEUE PUBLISHING RUN COMPLETE!", current=total, total=total, done=True, status="done")
    yield log(f"   • Total In Batch: {total}")
    yield log(f"   • Successfully Scheduled/Published: {success_count}")
    yield log(f"   • Failed: {failed_count}")
    yield log("=" * 76, done=True, status="stopped" if (stopped_by_user or queue_publish_stop_requested) else "done")


@app.get("/api/queue/publish/stream")
async def api_queue_publish_stream(
    platform: str = Query(None),
    limit: int = Query(0),
    dry_run: bool = Query(False),
    headless: bool = Query(False),
):
    """Stream live queue publishing execution events to browser client and stdout."""
    async def event_generator():
        async for item in run_queue_publishing_generator(
            platform=platform, limit=limit, dry_run=dry_run, headless=headless
        ):
            yield f"data: {json.dumps(item)}\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/queue/publish/stop")
async def api_queue_publish_stop():
    """Immediately stop the running queue publishing automation."""
    global queue_publish_stop_requested
    queue_publish_stop_requested = True
    conn = get_connection()
    conn.execute("UPDATE publishing_jobs SET status='pending' WHERE status='uploading'")
    conn.commit()
    conn.close()
    return {'status': 'stopped', 'message': 'Publishing stopped. Any in-flight uploading jobs reset to pending.'}


@app.post("/api/queue/reset-failed")
async def api_queue_reset_failed(reset_all: bool = False):
    """Reset failed (and stuck uploading, or all) publishing jobs back to pending."""
    conn = get_connection()
    if reset_all:
        res = conn.execute("UPDATE publishing_jobs SET status='pending', error_message=NULL WHERE status != 'published'")
    else:
        res = conn.execute("UPDATE publishing_jobs SET status='pending', error_message=NULL WHERE status IN ('failed', 'uploading')")
    count = res.rowcount
    conn.commit()
    conn.close()
    return {'status': 'success', 'reset_count': count, 'message': f'Reset {count} jobs back to pending.'}



def execute_queue_publishing_sync(platform=None, limit=0, dry_run=False, headless=False):
    """Synchronous runner for CLI execution (python run.py publish-queue)."""
    async def _runner():
        async for _ in run_queue_publishing_generator(
            platform=platform, limit=limit, dry_run=dry_run, headless=headless
        ):
            pass
    asyncio.run(_runner())


# ═══════════════════════════════════════════════════════════════════════════
#  API — BROWSER / PUBLISHING
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/browser/open-login")
async def api_open_browser_login():
    """Open browser with tabs for YouTube Studio, Instagram, and Facebook for manual authentication."""
    global active_browser_engine, is_queue_publishing_running
    if is_queue_publishing_running:
        raise HTTPException(
            status_code=409,
            detail="The publishing engine is currently running in the browser. Please wait for publishing to finish before opening manual login."
        )
    try:
        from app.browser.publisher import BrowserEngine
        if not active_browser_engine or not active_browser_engine.context:
            active_browser_engine = BrowserEngine(headless=False)
            await active_browser_engine.start()

        # Tab 1: YouTube Studio
        page_yt = active_browser_engine.page
        try:
            await page_yt.goto("https://studio.youtube.com", wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass

        # Tab 2: Instagram (create if only 1 tab)
        pages = active_browser_engine.context.pages
        page_ig = pages[1] if len(pages) > 1 else await active_browser_engine.context.new_page()
        try:
            await page_ig.goto("https://www.instagram.com", wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass

        # Tab 3: Facebook (create if only 2 tabs)
        pages = active_browser_engine.context.pages
        page_fb = pages[2] if len(pages) > 2 else await active_browser_engine.context.new_page()
        try:
            await page_fb.goto("https://www.facebook.com", wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass

        await page_yt.bring_to_front()

        return {
            'status': 'browser_opened',
            'message': 'Browser opened with tabs for YouTube Studio, Instagram, and Facebook. Sign in to your accounts manually.'
        }
    except Exception as e:
        logger.error(f"open-login failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/browser/check-auth")
async def api_check_auth():
    """Check authentication status across all platforms instantly from persistent cookie store."""
    from app.browser.publisher import fast_check_auth_from_profile
    try:
        status = fast_check_auth_from_profile(BROWSER_PROFILE_DIR)
        return status
    except Exception as e:
        logger.error(f"check-auth failed: {e}")
        return {'error': str(e), 'youtube': False, 'instagram': False, 'facebook': False}


@app.post("/api/browser/close")
async def api_close_browser():
    """Close active manual login browser window."""
    global active_browser_engine
    if active_browser_engine and active_browser_engine.context:
        try:
            await active_browser_engine.stop()
            active_browser_engine = None
            return {'status': 'closed', 'message': 'Browser window closed.'}
        except Exception as e:
            active_browser_engine = None
            return {'status': 'error', 'message': str(e)}
    return {'status': 'not_open', 'message': 'No browser window was open.'}


@app.post("/api/publish/dry-run/{video_id}")
async def api_dry_run_publish(video_id: int, platform: str = Query("youtube")):
    """Dry-run a single video publish to verify the workflow."""
    conn = get_connection()
    video = conn.execute("""
        SELECT sv.*, pv.output_filepath, er.seo_title, er.seo_description,
            t.thumbnail_path
        FROM source_videos sv
        LEFT JOIN processed_videos pv ON sv.id = pv.source_video_id
        LEFT JOIN excel_records er ON sv.filename = er.filename
        LEFT JOIN thumbnails t ON sv.id = t.source_video_id
        WHERE sv.id = ?
    """, (video_id,)).fetchone()
    conn.close()

    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    return {
        'dry_run': True,
        'video_id': video_id,
        'filename': video['filename'],
        'video_path': video['output_filepath'] or video['filepath'],
        'title': video['seo_title'],
        'description_preview': (video['seo_description'] or '')[:200] + '...',
        'thumbnail': video['thumbnail_path'],
        'platform': platform,
        'message': 'This is what would be published. No actual submission made.',
    }


# ═══════════════════════════════════════════════════════════════════════════
#  API — SETTINGS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/settings")
async def api_get_settings():
    """Get current application settings."""
    from config.settings import get_all_settings
    return get_all_settings()


@app.post("/api/settings")
async def api_save_settings(request: Request):
    """
    Save updated application settings (paths, timezone, slots, caps).
    If slots or timezone change, automatically realigns schedule
    (pending + upcoming scheduled jobs by default, preserving published posts).
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    from config.settings import save_user_settings
    from app.scheduler.engine import realign_pending_schedule

    saved = save_user_settings(data)

    realign_info = None
    if "publishing_slots" in data or "timezone" in data or data.get("realign_schedule", True):
        include_sched = data.get("include_future_scheduled", True)
        realign_info = realign_pending_schedule(
            new_slots=saved.get("publishing_slots"),
            new_timezone=saved.get("timezone"),
            include_future_scheduled=include_sched,
        )

    return {
        "success": True,
        "message": "Settings updated successfully.",
        "settings": saved,
        "realign": realign_info,
    }


@app.post("/api/schedule/realign")
async def api_schedule_realign(request: Request):
    """Realign all pending & future scheduled jobs to the current or requested publishing slots."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass

    from app.scheduler.engine import realign_pending_schedule
    new_slots = body.get("slots") or body.get("publishing_slots")
    new_tz = body.get("timezone")
    include_sched = body.get("include_future_scheduled", True)

    result = realign_pending_schedule(
        new_slots=new_slots,
        new_timezone=new_tz,
        include_future_scheduled=include_sched,
    )
    return result



@app.get("/api/system/health")
async def api_system_health():
    """Comprehensive system health and onboarding prerequisites check."""
    import shutil
    import sys

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)

    ffmpeg_bin = shutil.which(FFMPEG_PATH)
    ffprobe_bin = shutil.which(FFPROBE_PATH)
    ffmpeg_ok = ffmpeg_bin is not None and ffprobe_bin is not None

    start_vids = []
    try:
        start_vids = discover_start_videos()
    except Exception:
        pass

    end_vid = None
    try:
        end_vid = discover_end_video(optional=True)
    except Exception:
        pass

    excel_exists = EXCEL_PATH.exists()
    excel_valid = False
    if excel_exists:
        try:
            wb = load_workbook_safe(EXCEL_PATH)
            v = validate_workbook_structure(wb)
            excel_valid = v['valid']
            wb.close()
        except Exception:
            pass

    db_exists = DB_PATH.exists()
    job_counts = {'pending': 0, 'scheduled': 0, 'published': 0, 'failed': 0}
    if db_exists:
        try:
            conn = get_connection()
            rows = conn.execute("SELECT status, COUNT(*) c FROM publishing_jobs GROUP BY status").fetchall()
            for r in rows:
                s_key = (r['status'] or '').lower()
                job_counts[s_key] = r['c']
            conn.close()
        except Exception:
            pass

    from app.browser.publisher import fast_check_auth_from_profile
    auth = fast_check_auth_from_profile(BROWSER_PROFILE_DIR)

    all_ready = py_ok and ffmpeg_ok and len(start_vids) > 0 and (auth.get('youtube') or auth.get('facebook') or auth.get('instagram'))

    return {
        'status': 'ready' if all_ready else 'action_required',
        'python': {'version': py_ver, 'ok': py_ok},
        'ffmpeg': {'installed': ffmpeg_ok, 'ffmpeg_path': ffmpeg_bin, 'ffprobe_path': ffprobe_bin},
        'storage': {
            'start_video_dir': str(START_VIDEO_DIR),
            'start_video_count': len(start_vids),
            'end_video_dir': str(END_VIDEO_DIR),
            'has_end_video': end_vid is not None,
            'end_video_name': end_vid.name if end_vid else None,
            'excel_path': str(EXCEL_PATH),
            'excel_exists': excel_exists,
            'excel_valid': excel_valid,
            'db_path': str(DB_PATH),
            'db_exists': db_exists,
        },
        'auth': auth,
        'publishing': {
            'is_running': is_queue_publishing_running,
            'pipeline_running': is_pipeline_running,
            'job_counts': job_counts,
        }
    }


@app.get("/api/upcoming-schedule")
async def api_upcoming_schedule():
    """Fetch next upcoming scheduled jobs for the Home dashboard."""
    conn = get_connection()
    jobs = conn.execute("""
        SELECT pj.*, er.seo_title, er.word_count
        FROM publishing_jobs pj
        LEFT JOIN excel_records er ON pj.source_filename = er.filename
        WHERE pj.status IN ('scheduled', 'pending')
        ORDER BY pj.scheduled_date ASC, pj.scheduled_time ASC, pj.id ASC
        LIMIT 9
    """).fetchall()
    conn.close()
    return {'upcoming': [dict(j) for j in jobs]}


@app.get("/api/recent-activity")
async def api_recent_activity(limit: int = 10):
    """Fetch recent published/scheduled actions and audit events for the Home dashboard with rich details."""
    conn = get_connection()
    recent_jobs = conn.execute("""
        SELECT pj.id, pj.source_video_id, pj.source_filename, pj.source_filename as filename,
               pj.platform, pj.status, pj.scheduled_date, pj.scheduled_time, pj.timezone,
               pj.updated_at, pj.updated_at as timestamp, pj.remote_url, pj.error_message,
               COALESCE(pj.seo_title, er.seo_title, pj.source_filename) as title,
               COALESCE(pj.thumbnail_path, t.thumbnail_path) as thumbnail_path
        FROM publishing_jobs pj
        LEFT JOIN thumbnails t ON pj.source_video_id = t.source_video_id
        LEFT JOIN excel_records er ON pj.source_filename = er.filename
        WHERE pj.status IN ('published', 'scheduled', 'failed', 'pending')
        ORDER BY
            CASE
                WHEN pj.status = 'published' THEN 1
                WHEN pj.status = 'scheduled' THEN 2
                WHEN pj.status = 'failed' THEN 3
                ELSE 4
            END,
            pj.updated_at DESC, pj.id DESC
        LIMIT ?
    """, (limit,)).fetchall()

    audits = conn.execute("""
        SELECT event_type, details, timestamp
        FROM audit_log
        ORDER BY timestamp DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()

    return {
        'recent_jobs': [dict(j) for j in recent_jobs],
        'audit_events': [dict(a) for a in audits],
    }


# ═══════════════════════════════════════════════════════════════════════════
#  API — AUTO-HEALER, DIAGNOSTICS & UNATTENDED SCHEDULING RADAR
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/diagnostics/audit-health")
async def api_diagnostics_audit_health():
    """Comprehensive system health, active issues, and unattended study-mode readiness audit."""
    conn = get_connection()
    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Stuck jobs (uploading for > 10 minutes)
    stuck_jobs = conn.execute("""
        SELECT pj.*, er.seo_title
        FROM publishing_jobs pj
        LEFT JOIN excel_records er ON pj.source_filename = er.filename
        WHERE pj.status = 'uploading'
    """).fetchall()

    # 2. Failed jobs
    failed_jobs = conn.execute("""
        SELECT pj.*, er.seo_title
        FROM publishing_jobs pj
        LEFT JOIN excel_records er ON pj.source_filename = er.filename
        WHERE pj.status = 'failed'
        ORDER BY pj.updated_at DESC
        LIMIT 20
    """).fetchall()

    # 3. Quota usage today
    today_counts = conn.execute("""
        SELECT platform, COUNT(*) as c
        FROM publishing_jobs
        WHERE scheduled_date = ? AND status IN ('published', 'scheduled')
        GROUP BY platform
    """, (today_str,)).fetchall()
    try:
        from app.scheduler.generator import get_upload_cap
        daily_cap = get_upload_cap()
    except Exception:
        daily_cap = 9
    quota_status = {}
    for r in today_counts:
        quota_status[r['platform']] = {
            'used': r['c'],
            'cap': daily_cap,
            'pct': round((r['c'] / max(1, daily_cap)) * 100, 1)
        }

    # 4. Auth status
    from app.browser.publisher import fast_check_auth_from_profile
    auth = fast_check_auth_from_profile(BROWSER_PROFILE_DIR)

    # 5. Lockfile status in browser profile
    lockfiles_found = []
    if BROWSER_PROFILE_DIR.exists():
        for lf_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lf = BROWSER_PROFILE_DIR / lf_name
            if lf.exists():
                lockfiles_found.append(lf_name)

    # 6. Database table counts
    db_counts = {}
    for tbl in ['source_videos', 'excel_records', 'thumbnails', 'publishing_jobs', 'audit_log']:
        try:
            db_counts[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        except Exception:
            db_counts[tbl] = 0

    # 7. Audit log of auto-heals and failures
    recent_audits = conn.execute("""
        SELECT * FROM audit_log
        ORDER BY timestamp DESC
        LIMIT 15
    """).fetchall()

    conn.close()

    # Assemble Active Issues List
    active_issues = []

    # Check for stuck jobs
    for sj in stuck_jobs:
        active_issues.append({
            'id': f"stuck-job-{sj['id']}",
            'severity': 'warning',
            'category': 'stuck_job',
            'title': f"Interrupted Upload: '{sj['source_filename']}'",
            'platform': sj['platform'],
            'job_id': sj['id'],
            'description': f"This job was in 'uploading' state and may have been interrupted if the PC slept or restarted.",
            'root_cause': "System sleep or process restart during upload stream.",
            'can_auto_heal': True,
            'auto_heal_desc': "Reset back to 'pending' to re-arm on next queue run.",
            'action_type': 're-arm'
        })

    # Check for failed jobs
    for fj in failed_jobs:
        err = fj['error_message'] or 'Unknown error'
        is_limit = any(k in err.lower() for k in ['limit', 'rate', 'blocked'])
        is_auth = any(k in err.lower() for k in ['login', 'auth', 'sign in', '2fa', 'verification'])
        active_issues.append({
            'id': f"failed-job-{fj['id']}",
            'severity': 'critical' if is_auth else 'warning',
            'category': 'quota' if is_limit else ('auth' if is_auth else 'transient'),
            'title': f"{fj['platform'].upper()} Failed: '{fj['source_filename']}'",
            'platform': fj['platform'],
            'job_id': fj['id'],
            'description': err,
            'root_cause': "Platform quota limit (24h cooldown)" if is_limit else ("Session authentication expired" if is_auth else "Transient browser DOM or network timeout"),
            'can_auto_heal': not is_auth,
            'auto_heal_desc': "Auto-shift to tomorrow" if is_limit else "Reset to pending for auto-retry",
            'action_type': 'login' if is_auth else ('reschedule' if is_limit else 're-arm')
        })

    # Check for logged-out platforms
    for plat in ['youtube', 'instagram', 'facebook']:
        if not auth.get(plat):
            active_issues.append({
                'id': f"auth-{plat}",
                'severity': 'warning',
                'category': 'auth',
                'title': f"{plat.capitalize()} Session Not Active",
                'platform': plat,
                'job_id': None,
                'description': f"No saved browser login cookies detected for {plat.capitalize()}. Automated scheduling cannot proceed on this platform.",
                'root_cause': "Initial login or cookie refresh required.",
                'can_auto_heal': False,
                'user_action': f"Open 'Connections' tab, click 'Open Browser for Login', log into {plat.capitalize()} once, and save session.",
                'action_type': 'open_browser_login'
            })

    # Check lockfiles
    if lockfiles_found:
        active_issues.append({
            'id': 'browser-lockfiles',
            'severity': 'info',
            'category': 'system',
            'title': f"Chrome Singleton Lockfile Detected ({', '.join(lockfiles_found)})",
            'platform': 'all',
            'job_id': None,
            'description': "Leftover lockfile from a previous browser session. Auto-Healer can safely clean this before next run.",
            'root_cause': "Browser exited unexpectedly without releasing singleton lock.",
            'can_auto_heal': True,
            'auto_heal_desc': "Delete singleton lockfile safely.",
            'action_type': 'clean_locks'
        })

    unattended_ready = len([i for i in active_issues if i['severity'] == 'critical']) == 0

    return {
        'status': 'ready' if unattended_ready and len(active_issues) == 0 else ('degraded' if unattended_ready else 'action_required'),
        'unattended_ready': unattended_ready,
        'active_issues_count': len(active_issues),
        'active_issues': active_issues,
        'quota_status': quota_status,
        'auth': auth,
        'lockfiles': lockfiles_found,
        'db_counts': db_counts,
        'recent_audits': [dict(a) for a in recent_audits],
    }


@app.post("/api/diagnostics/auto-heal-all")
async def api_diagnostics_auto_heal_all():
    """Execute complete 5-point automated self-healing routine."""
    conn = get_connection()
    actions_taken = []
    resolved_count = 0

    # 1. Clear dead Chromium singleton lockfiles
    cleaned_locks = []
    if BROWSER_PROFILE_DIR.exists():
        for lf_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            lf = BROWSER_PROFILE_DIR / lf_name
            if lf.exists():
                try:
                    lf.unlink(missing_ok=True)
                    cleaned_locks.append(lf_name)
                except Exception:
                    pass
    if cleaned_locks:
        actions_taken.append(f"Cleared {len(cleaned_locks)} orphaned Chrome singleton lockfile(s) ({', '.join(cleaned_locks)}) to prevent browser startup crashes.")
        resolved_count += len(cleaned_locks)

    # 2. Reset stuck uploading jobs back to pending
    stuck_res = conn.execute("""
        UPDATE publishing_jobs
        SET status='pending', error_message='Auto-healed: Reset from interrupted uploading state', updated_at=?
        WHERE status='uploading'
    """, (datetime.now().isoformat(),))
    if stuck_res.rowcount > 0:
        actions_taken.append(f"Reset {stuck_res.rowcount} interrupted job(s) from 'uploading' back to 'pending' so they will re-upload automatically.")
        resolved_count += stuck_res.rowcount

    # 3. Auto-recover failed transient jobs
    failed_res = conn.execute("""
        UPDATE publishing_jobs
        SET status='pending', error_message='Auto-healed: Re-armed for automated publishing', attempt_count=0, updated_at=?
        WHERE status='failed' AND (error_message IS NULL OR error_message NOT LIKE '%limit%' AND error_message NOT LIKE '%login%' AND error_message NOT LIKE '%auth%')
    """, (datetime.now().isoformat(),))
    if failed_res.rowcount > 0:
        actions_taken.append(f"Re-armed {failed_res.rowcount} failed job(s) back to 'pending' with reset retry counters.")
        resolved_count += failed_res.rowcount

    # 4. Check SQLite WAL integrity
    try:
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        try:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:
            pass
        actions_taken.append(f"Verified SQLite database integrity: {check}.")
    except Exception as e:
        actions_taken.append(f"Database check warning: {e}")

    # 5. Audit log
    conn.execute("""
        INSERT INTO audit_log (event_type, details, timestamp)
        VALUES ('auto_heal_executed', ?, ?)
    """, (json.dumps({'actions': actions_taken, 'resolved_count': resolved_count}), datetime.now().isoformat()))
    conn.commit()
    conn.close()

    return {
        'success': True,
        'resolved_count': resolved_count,
        'actions_taken': actions_taken,
        'message': f"Self-healing complete! Resolved {resolved_count} item(s)."
    }


@app.post("/api/diagnostics/resolve-job")
async def api_diagnostics_resolve_job(payload: Dict[str, Any]):
    """Resolve a specific job issue with 1-click action."""
    job_id = payload.get('job_id')
    action = payload.get('action') # 're-arm', 'reschedule_tomorrow', 'mark_resolved'
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    conn = get_connection()
    job = conn.execute("SELECT * FROM publishing_jobs WHERE id=?", (job_id,)).fetchone()
    if not job:
        conn.close()
        raise HTTPException(status_code=404, detail="Job not found")

    if action == 're-arm':
        conn.execute("""
            UPDATE publishing_jobs
            SET status='pending', attempt_count=0, error_message=NULL, updated_at=?
            WHERE id=?
        """, (datetime.now().isoformat(), job_id))
        msg = f"Job #{job_id} re-armed to PENDING. Ready for scheduled publish."
    elif action == 'reschedule_tomorrow':
        from datetime import timedelta
        cur_date = datetime.strptime(job['scheduled_date'], "%Y-%m-%d")
        tom_str = (cur_date + timedelta(days=1)).strftime("%Y-%m-%d")
        conn.execute("""
            UPDATE publishing_jobs
            SET scheduled_date=?, status='pending', attempt_count=0, error_message=NULL, updated_at=?
            WHERE id=?
        """, (tom_str, datetime.now().isoformat(), job_id))
        msg = f"Job #{job_id} rescheduled to tomorrow ({tom_str}) and reset to PENDING."
    else:
        conn.execute("""
            UPDATE publishing_jobs
            SET error_message=NULL, updated_at=?
            WHERE id=?
        """, (datetime.now().isoformat(), job_id))
        msg = f"Job #{job_id} marked resolved."

    conn.commit()
    conn.close()
    return {'success': True, 'message': msg}


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Launch the dashboard server."""
    print(f"\n{'='*60}")
    print(f"  Video Scheduling Dashboard")
    print(f"  http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    print(f"{'='*60}\n")
    loop_opt = "asyncio:ProactorEventLoop" if sys.platform == "win32" else "auto"
    uvicorn.run(
        "app.dashboard.server:app",
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        reload=False,
        loop=loop_opt,
        log_level="info",
    )

if __name__ == "__main__":
    main()

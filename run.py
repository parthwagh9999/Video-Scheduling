"""
CLI and Application Entrypoint for Video Scheduling Automation System.
Provides commands to run dashboard, scan media, sync Excel, process videos, and manage publishing.
"""
import sys
import argparse
import subprocess
from pathlib import Path

# Fix Windows console unicode issues
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Enforce ProactorEventLoop on Windows for Playwright subprocess compatibility
if sys.platform == "win32":
    import asyncio
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

from config.settings import DASHBOARD_HOST, DASHBOARD_PORT, DB_PATH
from app.database.models import init_db


def cmd_dashboard(args):
    """Start the FastAPI Dashboard server."""
    print(f"\n========================================================")
    print(f"  🎬 Video Scheduling Dashboard Launching")
    print(f"  URL: http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    print(f"  Database: {DB_PATH}")
    print(f"========================================================\n")
    import uvicorn
    import sys
    loop_opt = "asyncio:ProactorEventLoop" if sys.platform == "win32" else "auto"
    uvicorn.run(
        "app.dashboard.server:app",
        host=args.host or DASHBOARD_HOST,
        port=args.port or DASHBOARD_PORT,
        reload=args.reload,
        loop=loop_opt,
        log_level="info",
    )


def cmd_scan(args):
    """Scan video folders and sync with database."""
    print("🔍 Discovering video files and synchronizing database...")
    import asyncio
    from app.dashboard.server import api_scan_videos
    results = asyncio.run(api_scan_videos())
    print(f"✅ Discovered {results.get('start_videos', 0)} start videos.")
    if results.get('end_video'):
        print(f"✅ End video identified: {results['end_video']['filename']} ({results['end_video']['duration']:.1f}s)")
    print(f"✅ Synced {results.get('excel_records_synced', 0)} Excel records to database.")
    if results.get('errors'):
        print(f"⚠️ Warnings/Errors ({len(results['errors'])}):")
        for err in results['errors']:
            print(f"  - {err}")


def cmd_sync_excel(args):
    """Synchronize Excel workbook with actual video files."""
    print("📋 Checking Excel workbook synchronization...")
    from app.excel.sync import sync_workbook, preview_new_records
    if args.dry_run:
        new_records, comp = preview_new_records()
        print(f"🔍 Dry run preview: {len(new_records)} missing videos found.")
        for r in new_records:
            print(f"  + {r['filename']}")
    else:
        report = sync_workbook(dry_run=False)
        print(f"✅ Workbook synchronized successfully!")
        print(f"  Backup saved to: {report['backup_path']}")
        print(f"  Rows added: {report['added_count']}")


def cmd_process(args):
    """Process videos (concatenation with outro & opening frame thumbnail extraction)."""
    print(f"⚙️ Running video processing (dry_run={args.dry_run}, rule={args.rule})...")
    from app.video.processor import process_all_videos
    manifest = process_all_videos(outro_rule=args.rule, start_index=0, dry_run=args.dry_run)
    print(f"✅ Processed {len(manifest)} videos.")
    with_outro = sum(1 for m in manifest if m['outro_appended'])
    print(f"  With outro: {with_outro}")
    print(f"  Without outro: {len(manifest) - with_outro}")


def cmd_login(args):
    """Open Chrome with persistent browser profile for manual account sign-in."""
    print("🔓 Opening browser for manual sign-in...")
    import asyncio
    from app.browser.publisher import BrowserEngine
    async def _open():
        engine = BrowserEngine(headless=False)
        await engine.start()
        print("🌐 Opening tabs for YouTube Studio, Instagram, and Facebook...")

        page_yt = engine.page
        try:
            await page_yt.goto("https://studio.youtube.com", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        page_ig = await engine.context.new_page()
        try:
            await page_ig.goto("https://www.instagram.com", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        page_fb = await engine.context.new_page()
        try:
            await page_fb.goto("https://www.facebook.com", wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        await page_yt.bring_to_front()

        print("\n✅ All 3 platform tabs opened in browser:")
        print("  • Tab 1: YouTube Studio (https://studio.youtube.com)")
        print("  • Tab 2: Instagram      (https://www.instagram.com)")
        print("  • Tab 3: Facebook       (https://www.facebook.com)")
        print("\nKeep browser open until done, then press Enter here to save session & close.")
        input("Press [Enter] after you have completed logging in: ")
        await engine.stop()
    asyncio.run(_open())


def cmd_check_auth(args):
    """Check browser authentication status on all 3 platforms."""
    print("🔍 Checking platform authentication status...")
    import asyncio
    from app.browser.publisher import BrowserEngine, check_all_auth
    async def _check():
        engine = BrowserEngine(headless=False)
        await engine.start()
        status = await check_all_auth(engine)
        await engine.stop()
        print("\nAuthentication Status:")
        print(f"  YouTube Studio:  {'✅ Logged In' if status['youtube'] else '❌ Not Logged In'}")
        print(f"  Instagram Reels: {'✅ Logged In' if status['instagram'] else '❌ Not Logged In'}")
        print(f"  Facebook Reels:  {'✅ Logged In' if status['facebook'] else '❌ Not Logged In'}")
    asyncio.run(_check())


def cmd_all(args):
    """Execute all pipeline steps sequentially with full terminal output."""
    from app.dashboard.server import execute_pipeline_sync
    execute_pipeline_sync()


def cmd_scan_thumbnails(args):
    """Scan and synchronize opening-frame thumbnails."""
    print("🖼️ Scanning and verifying opening-frame thumbnails...")
    from app.video.processor import scan_and_sync_thumbnails
    res = scan_and_sync_thumbnails()
    print(f"✅ Thumbnails Scanned: {res['total_videos']} total videos.")
    print(f"  • Existing valid: {res['existing_valid']}")
    print(f"  • Extracted: {res['extracted']}")
    print(f"  • Failed: {res['failed']}")
    if res['errors']:
        for err in res['errors']:
            print(f"  ⚠️ {err}")


def cmd_publish_queue(args):
    """Execute queued publishing jobs via browser automation."""
    from app.dashboard.server import execute_queue_publishing_sync
    execute_queue_publishing_sync(
        platform=args.platform,
        limit=args.limit,
        dry_run=args.dry_run,
        headless=args.headless
    )


def cmd_test(args):
    """Run test suite."""
    print("🧪 Running Pytest suite...")
    subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"])


def main():
    parser = argparse.ArgumentParser(
        description="Video Scheduling & Multi-Platform Publishing System"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # all (full pipeline)
    subparsers.add_parser("all", help="Execute all pipeline steps sequentially (Preflight, Scan, Thumbnails, Processing, Schedule, Queue)")

    # scan-thumbnails
    subparsers.add_parser("scan-thumbnails", help="Scan and verify opening-frame thumbnails")

    # publish-queue
    p_pub = subparsers.add_parser("publish-queue", help="Execute queued video uploads & scheduling via browser automation")
    p_pub.add_argument("--platform", choices=["youtube", "instagram", "facebook"], default=None, help="Filter by platform")
    p_pub.add_argument("--limit", type=int, default=0, help="Maximum number of jobs to execute (0 = all)")
    p_pub.add_argument("--dry-run", action="store_true", help="Simulate upload and scheduling without launching browser or uploading")
    p_pub.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Start the FastAPI web dashboard")
    p_dash.add_argument("--host", default=DASHBOARD_HOST, help="Host to bind")
    p_dash.add_argument("--port", type=int, default=DASHBOARD_PORT, help="Port to bind")
    p_dash.add_argument("--reload", action="store_true", help="Auto reload on code change")

    # scan
    subparsers.add_parser("scan", help="Scan folders and update database")

    # sync-excel
    p_sync = subparsers.add_parser("sync-excel", help="Sync Excel workbook with videos")
    p_sync.add_argument("--dry-run", action="store_true", help="Preview without writing")

    # process
    p_proc = subparsers.add_parser("process", help="Concatenate videos and extract thumbnails")
    p_proc.add_argument("--rule", default="every_second", choices=["every_second", "every", "none"])
    p_proc.add_argument("--dry-run", action="store_true", help="Simulate without encoding")

    # login
    subparsers.add_parser("login", help="Open browser with profile to log in to accounts")

    # check-auth
    subparsers.add_parser("check-auth", help="Check session login on YouTube, Instagram, Facebook")

    # test
    subparsers.add_parser("test", help="Run pytest test suite")

    args = parser.parse_args()

    # Ensure DB initialized
    init_db()

    commands = {
        "all": cmd_all,
        "scan-thumbnails": cmd_scan_thumbnails,
        "publish-queue": cmd_publish_queue,
        "dashboard": cmd_dashboard,
        "scan": cmd_scan,
        "sync-excel": cmd_sync_excel,
        "process": cmd_process,
        "login": cmd_login,
        "check-auth": cmd_check_auth,
        "test": cmd_test,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        # Default action: run dashboard
        cmd_dashboard(argparse.Namespace(host=DASHBOARD_HOST, port=DASHBOARD_PORT, reload=False))


if __name__ == "__main__":
    main()

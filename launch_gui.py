"""
GUI Launcher for Video Scheduling Automation System.
Starts the FastAPI backend and automatically opens the dashboard in your default browser.
"""
import sys
import os
import time
import threading
import webbrowser
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


def free_port_if_in_use(port: int):
    """If another process is holding the port, terminate it cleanly so Uvicorn can bind."""
    if sys.platform != "win32":
        return
    import subprocess
    try:
        output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
        current_pid = os.getpid()
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in parts:
                pid = int(parts[-1])
                if pid != current_pid and pid != 0:
                    print(f"⚠️ Port {port} was occupied by background process (PID {pid}). Freeing port...")
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                    time.sleep(1)
    except Exception:
        pass


def open_browser_delayed(url: str, delay: float = 1.2):
    """Wait briefly for Uvicorn to bind the port, then open default web browser."""
    def _target():
        time.sleep(delay)
        print(f"\n🌐 Opening GUI in your browser: {url}\n")
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Could not automatically launch browser: {e}")
            print(f"Please open manually in your browser: {url}")
    t = threading.Thread(target=_target, daemon=True)
    t.start()


def main():
    free_port_if_in_use(DASHBOARD_PORT)
    init_db()
    url = f"http://{DASHBOARD_HOST}:{DASHBOARD_PORT}"
    print("\n" + "=" * 64)
    print("  🎬 Video Scheduling Automation — Web GUI")
    print(f"  URL: {url}")
    print(f"  Database: {DB_PATH}")
    print("=" * 64 + "\n")

    open_browser_delayed(url, delay=1.2)

    import uvicorn
    loop_opt = "asyncio:ProactorEventLoop" if sys.platform == "win32" else "auto"
    try:
        uvicorn.run(
            "app.dashboard.server:app",
            host=DASHBOARD_HOST,
            port=DASHBOARD_PORT,
            reload=False,
            loop=loop_opt,
            log_level="info",
        )
    except KeyboardInterrupt:
        print("\n👋 GUI server stopped cleanly.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

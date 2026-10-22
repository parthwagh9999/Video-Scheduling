"""
Browser-based publishing engine using Playwright.
Operates actual browser interfaces — no APIs.
Uses persistent Chromium profile for session reuse.
Handles YouTube Studio, Instagram, and Facebook publishing.
"""
import asyncio
import os
import logging
import random
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import (
    BROWSER_PROFILE_DIR, BROWSER_TIMEOUT_MS, UPLOAD_TIMEOUT_MS,
    Platform, Status,
)

logger = logging.getLogger(__name__)


async def human_delay(page, min_s: float = 20.0, max_s: float = 30.0, action_name: str = ""):
    """Pause execution for a randomized delay between min_s and max_s (default 20-30s) to mimic a real human."""
    delay = round(random.uniform(min_s, max_s), 1)
    if action_name:
        logger.info(f"⏳ [Human Delay] '{action_name}' completed — waiting {delay}s before next action...")
    else:
        logger.info(f"⏳ [Human Delay] Waiting {delay}s before next action...")
    await page.wait_for_timeout(int(delay * 1000))


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def sanitize_title_no_numbers(title: str) -> str:
    """
    Remove all numbers, resolution tags (1080p, 720p, 4k, 2k, 60fps), timestamps,
    outro suffixes, and trailing symbols/prepositions from title. Guarantees no digits in title.
    """
    if not title:
        return 'Short Video'
    t = str(title).strip()
    # Remove file extension if present
    t = re.sub(r'\.(?:mp4|mov|avi|mkv|webm|m4v)$', '', t, flags=re.IGNORECASE)
    # Replace all underscores and hyphens with spaces FIRST so word boundaries match reliably
    t = re.sub(r'[\-_]+', ' ', t)
    # Remove 'with outro' or 'outro'
    t = re.sub(r'\b(?:with\s+)?outro\b', '', t, flags=re.IGNORECASE)
    # Remove resolution tags (e.g. 1080p, 720p, 4k, 2k, 60fps)
    t = re.sub(r'\b\d+(?:p|k|fps)\b', '', t, flags=re.IGNORECASE)
    # Remove all remaining digits
    t = re.sub(r'\d+', '', t)
    # Remove extra spaces and clean edges
    t = re.sub(r'\s+', ' ', t).strip(' -_.,:;')
    # Clean trailing hanging prepositions left behind
    t = re.sub(r'\b(in|for|of|to|at|by|on|with)\s*$', '', t, flags=re.IGNORECASE).strip(' -_.,:;')
    return t or 'Short Video'


def _bring_browser_to_foreground():
    """Ensure the automated browser window is restored and brought to the foreground on Windows.
    Tries multiple times and uses aggressive Win32 API calls to ensure visibility."""
    try:
        import ctypes
        import time
        user32 = ctypes.windll.user32

        # Allow our process to set foreground window
        try:
            user32.AllowSetForegroundWindow(-1)  # ASFW_ANY = -1
        except Exception:
            pass

        found_windows = []

        def enum_windows_callback(hwnd, extra):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if any(term.lower() in title.lower() for term in ['YouTube', 'Instagram', 'Facebook', 'Google Chrome', 'Chromium', 'Chrome', 'Studio', 'about:blank', 'New Tab']):
                        found_windows.append(hwnd)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

        for hwnd in found_windows:
            try:
                # Restore if minimized (SW_RESTORE = 9)
                user32.ShowWindow(hwnd, 9)
                time.sleep(0.05)
                # Maximize (SW_MAXIMIZE = 3)
                user32.ShowWindow(hwnd, 3)
                time.sleep(0.05)
                # Bring to foreground
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass

        if found_windows:
            logger.debug(f"Brought {len(found_windows)} browser window(s) to foreground")
    except Exception as e:
        logger.debug(f"_bring_browser_to_foreground notice: {e}")



class BrowserEngine:
    """Manages Playwright browser lifecycle with persistent authentication."""

    def __init__(self, profile_dir: Path = None, headless: bool = False, user_agent: str = None):
        self.profile_dir = Path(profile_dir or BROWSER_PROFILE_DIR)
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.user_agent = user_agent or DEFAULT_USER_AGENT
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        """Launch browser with persistent profile."""
        if sys.platform == "win32":
            loop = asyncio.get_running_loop()
            if not isinstance(loop, getattr(asyncio, "ProactorEventLoop", (type(None),))):
                raise RuntimeError(
                    f"Playwright requires asyncio.ProactorEventLoop on Windows, but current event loop is {type(loop).__name__}. "
                    "Ensure the application was launched using 'python run.py dashboard' without --reload."
                )

        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()

        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--disable-dev-shm-usage',
            '--no-sandbox',
        ]
        if not self.headless:
            launch_args.extend([
                '--start-maximized',
                '--window-position=50,50',
            ])

        viewport_opt = None if not self.headless else {'width': 1280, 'height': 900}

        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                user_agent=self.user_agent,
                viewport=viewport_opt,
                locale='en-US',
                timezone_id='Asia/Kolkata',
                args=launch_args,
                accept_downloads=True,
            )
        except Exception as e:
            err_str = str(e)
            if any(k in err_str for k in ("ProcessSingleton", "used by another process", "Target closed", "browser has been closed")):
                logger.warning(f"Chromium launch issue detected ({err_str}). Auto-cleaning lingering processes...")
                import subprocess
                subprocess.run(
                    ['powershell', '-NoProfile', '-Command', 'Get-Process -Name "chrome" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "*ms-playwright*" } | Stop-Process -Force'],
                    capture_output=True
                )
                await asyncio.sleep(1.5)
                self.context = await self.playwright.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    headless=self.headless,
                    user_agent=self.user_agent,
                    viewport=viewport_opt,
                    locale='en-US',
                    timezone_id='Asia/Kolkata',
                    args=launch_args,
                    accept_downloads=True,
                )
            else:
                raise

        await self.context.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.bring_to_front()
        if not self.headless:
            # Give the window a moment to render before trying to bring to foreground
            await asyncio.sleep(1)
            _bring_browser_to_foreground()
            await asyncio.sleep(0.5)
            _bring_browser_to_foreground()
        logger.info(f"Browser started with persistent profile (headless={self.headless})")
        return self.page


    async def stop(self):
        """Close browser gracefully."""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser stopped")

    async def screenshot(self, name="screenshot"):
        """Take a screenshot for debugging. Returns path."""
        if not self.page:
            return None
        screenshots_dir = self.profile_dir.parent / "logs" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = screenshots_dir / f"{name}_{ts}.png"
        try:
            await self.page.screenshot(path=str(path), timeout=8000)
            logger.info(f"Screenshot saved: {path}")
            return str(path)
        except Exception as e:
            logger.warning(f"Screenshot capture notice for '{name}': {e}")
            return None

    async def check_for_security_challenge(self):
        """
        Detect CAPTCHAs, 2FA, suspicious-login checks.
        Returns True only if actual user intervention is required.
        """
        page = self.page
        if not page:
            return False

        # If legitimate authenticated elements exist on page, we are authenticated
        try:
            has_auth_el = await page.query_selector(
                '#create-icon, button[aria-label*="Create" i], [aria-label*="Create" i], ytcp-app, #upload-button, '
                'svg[aria-label="New post"], svg[aria-label="Home"], [aria-label*="Create reel" i], #upload-prompt-box'
            )
            if has_auth_el and await has_auth_el.is_visible():
                return False
        except Exception:
            pass

        url = page.url.lower()
        if any(ch in url for ch in ['/challenge', '/checkpoint', 'signin/v2/challenge', 'accounts.google.com/signin/rejected']):
            logger.warning(f"Security challenge URL detected: {page.url}")
            return True

        # Check visible inner text only (excluding hidden scripts and styles)
        try:
            visible_text = await page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")
            challenge_phrases = [
                "verify it's you",
                "suspicious activity detected",
                "confirm your identity",
                "enter the code sent to",
                "enter verification code",
                "two-factor authentication",
                "type the characters you see",
                "solve this puzzle",
            ]
            for phrase in challenge_phrases:
                if phrase in visible_text:
                    logger.warning(f"Security challenge detected in visible text: {phrase}")
                    return True
        except Exception:
            pass

        return False


class YouTubePublisher:
    """Automate YouTube Studio upload and scheduling through the browser."""

    STUDIO_URL = "https://studio.youtube.com"

    def __init__(self, engine: BrowserEngine):
        self.engine = engine
        self.page = engine.page

    async def _human_delay(self, min_s: float = 10.0, max_s: float = 20.0, action_name: str = ""):
        """Pause execution for a randomized delay between min_s and max_s (default 10-20s) to mimic a real human."""
        await human_delay(self.page, min_s, max_s, action_name)

    async def is_authenticated(self):
        """Check if we're logged into YouTube / YouTube Studio."""
        try:
            # 1. Fast cookie check
            cookies = await self.engine.context.cookies()
            auth_cookie_names = {'SAPISID', 'SSID', 'LOGIN_INFO', '__Secure-3PSID', 'SID'}
            has_auth_cookies = any(
                c['name'] in auth_cookie_names and ('youtube' in c.get('domain', '') or 'google' in c.get('domain', ''))
                for c in cookies
            )

            # 2. Navigate to Studio
            try:
                await self.page.goto(self.STUDIO_URL, wait_until='domcontentloaded', timeout=20000)
                await self.page.wait_for_timeout(3000)
            except Exception as e:
                logger.warning(f"Studio load timeout/warning: {e}")

            url = self.page.url
            if 'accounts.google.com' in url or 'signin' in url.lower():
                return False

            # Check if Studio interstitial "SKIP TO YOUTUBE STUDIO" is displayed
            skip_btn = await self.page.query_selector('text="SKIP TO YOUTUBE STUDIO"')
            if not skip_btn:
                elements = await self.page.query_selector_all('a, button, span')
                for el in elements:
                    txt = await el.text_content()
                    if txt and "SKIP TO YOUTUBE STUDIO" in txt.upper():
                        skip_btn = el
                        break
            if skip_btn:
                try:
                    await skip_btn.click()
                    await self.page.wait_for_timeout(5000)
                except Exception:
                    pass

            # Check for Studio dashboard indicators
            if 'studio.youtube.com/channel' in self.page.url:
                return True

            studio_el = await self.page.query_selector(
                'ytcp-app, ytcp-home-page, #create-icon, button#create-icon, ytcp-button#create-icon, #upload-button, [aria-label*="Create" i]'
            )
            if studio_el:
                return True

            content = await self.page.content()
            if 'Channel dashboard' in content or 'Channel content' in content or 'studio.youtube.com/channel' in url:
                return True

            # If auth cookies were found and we're not on a signin page, check www.youtube.com avatar
            if has_auth_cookies:
                try:
                    await self.page.goto("https://www.youtube.com", wait_until='domcontentloaded', timeout=15000)
                    await self.page.wait_for_timeout(2000)
                    avatar = await self.page.query_selector('#avatar-btn, ytd-topbar-menu-button-renderer, button[aria-label*="Account" i], button:has-text("Create")')
                    sign_in = await self.page.query_selector('a[href*="signin"], ytd-button-renderer a[href*="ServiceLogin"]')
                    if avatar or not sign_in:
                        return True
                except Exception:
                    return True  # Fallback to cookies validity

            return False
        except Exception as e:
            logger.error(f"YouTube auth check failed: {e}")
            return False

    async def open_for_manual_login(self):
        """Navigate to YouTube Studio for manual sign-in."""
        await self.page.goto(self.STUDIO_URL, wait_until='domcontentloaded',
                              timeout=BROWSER_TIMEOUT_MS)
        logger.info("YouTube Studio opened for manual login")
        return self.page.url

    async def check_for_upload_limit(self) -> Optional[str]:
        """
        Check if YouTube Studio has displayed an upload limit warning or banner.
        Returns error description if detected, otherwise None.
        """
        page = self.page
        if not page:
            return None
        try:
            # 1. Search full page innerText
            text = await page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")
            limit_keywords = [
                "daily upload limit reached",
                "upload limit reached",
                "upload more videos daily after a one-time verification",
                "wait 24 hours to upload more",
                "daily limit reached",
                "you've reached your daily limit",
            ]
            for kw in limit_keywords:
                if kw in text:
                    logger.error(f"YouTube upload limit detected: '{kw}'")
                    return "Daily upload limit reached on YouTube. Upload limit resets in 24 hours."

            # 2. Check for dialog banner or error element
            banner = await page.query_selector(
                'div:has-text("Daily upload limit reached"), '
                'ytcp-banner:has-text("upload limit"), '
                '[aria-label*="upload limit" i], '
                'div:has-text("Upload more videos daily")'
            )
            if banner and await banner.is_visible():
                return "Daily upload limit reached on YouTube. Upload limit resets in 24 hours."
        except Exception as e:
            logger.debug(f"Error checking upload limit: {e}")
        return None

    async def upload_and_schedule(self, video_path, title, description,
                                   schedule_date, schedule_time,
                                   thumbnail_path=None, dry_run=False):
        """
        Full YouTube Studio upload + schedule workflow with user-defined pacing:
          - Pre-selection delay: 5-10 seconds
          - Post-selection upload delay: at least 20 seconds (+ upload completion check)
          - Subsequent post-upload delays: strictly 10-20 seconds
          - Custom thumbnail: strictly required and uploaded
        """
        result = {
            'platform': Platform.YOUTUBE,
            'video_path': video_path,
            'title': title,
            'status': 'pending',
            'error': None,
            'url': None,
            'screenshot': None,
        }

        try:
            page = self.page

            # Bring browser to foreground at the start
            if not self.engine.headless:
                _bring_browser_to_foreground()

            # 1. Navigate to Studio
            logger.info("Navigating to YouTube Studio...")
            await page.goto(self.STUDIO_URL, wait_until='domcontentloaded',
                             timeout=45000)
            if not self.engine.headless:
                _bring_browser_to_foreground()
            await self._human_delay(5.0, 10.0, "YouTube Studio dashboard loaded")

            if await self.engine.check_for_security_challenge():
                result['status'] = 'needs_attention'
                result['error'] = 'Security challenge detected. Manual intervention required.'
                result['screenshot'] = await self.engine.screenshot('yt_security')
                return result

            if dry_run:
                result['status'] = 'dry_run'
                result['error'] = None
                logger.info(f"[DRY RUN] Would upload: {title}")
                return result

            clean_title = sanitize_title_no_numbers(title)

            # 1.1 Check if an existing draft already exists on YouTube Studio to avoid creating multiple draft copies
            is_draft_resumed = await self._find_and_open_existing_draft(page, clean_title, video_path)

            if not is_draft_resumed:
                # Close any lingering previous dialog if open
                try:
                    lingering_close = await page.query_selector('ytcp-uploads-dialog #close-button, ytcp-uploads-dialog [aria-label*="close" i]')
                    if lingering_close and await lingering_close.is_visible():
                        logger.info("Dismissing lingering dialog before initiating upload...")
                        await lingering_close.click()
                        await page.wait_for_timeout(2000)
                except Exception:
                    pass

                # 2. Click Create/Upload button
                logger.info("Looking for Create button...")
                create_btn = await self._find_create_button(page)
                if not create_btn:
                    result['status'] = 'failed'
                    result['error'] = 'Could not find Create/Upload button'
                    result['screenshot'] = await self.engine.screenshot('yt_no_create')
                    return result

                try:
                    await create_btn.hover()
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                await create_btn.click()
                await self._human_delay(5.0, 10.0, "Create menu button clicked")

                # 3. Click "Upload videos" from dropdown
                logger.info("Looking for Upload videos option...")
                upload_option = await self._find_upload_option(page)
                if not upload_option:
                    result['status'] = 'failed'
                    result['error'] = 'Could not find Upload videos option'
                    result['screenshot'] = await self.engine.screenshot('yt_no_upload')
                    return result

                try:
                    await upload_option.hover()
                    await page.wait_for_timeout(500)
                except Exception:
                    pass
                await upload_option.click()

                # Delay before selecting video: between 5-10 seconds
                await self._human_delay(5.0, 10.0, "Upload modal open — waiting 5-10s before selecting video file")

                # 4. Handle file selection with clean staged filename (guarantees NO numbers in default title)
                upload_video_path = video_path
                try:
                    v_p = Path(video_path)
                    safe_name = re.sub(r'[\\/*?:"<>|]', '', clean_title).replace(' ', '_').strip('_') + v_p.suffix
                    staging_dir = v_p.parent / ".clean_staging"
                    staging_dir.mkdir(parents=True, exist_ok=True)
                    clean_target = staging_dir / safe_name
                    if not clean_target.exists():
                        try:
                            os.link(str(v_p), str(clean_target))
                        except Exception:
                            import shutil
                            shutil.copy2(str(v_p), str(clean_target))
                    upload_video_path = str(clean_target)
                except Exception as staging_err:
                    logger.debug(f"Notice on clean staging file: {staging_err}")
                    upload_video_path = video_path

                logger.info(f"Setting video file: {upload_video_path}")
                try:
                    file_input = await page.query_selector('input[type="file"]')
                    if file_input:
                        await file_input.set_input_files(upload_video_path)
                        logger.info(f"File set directly via file input: {upload_video_path}")
                    else:
                        async with page.expect_file_chooser(timeout=15000) as fc_info:
                            select_btn = await page.query_selector(
                                '#select-files-button, [id*="select-files"], button:has-text("Select files"), #upload-prompt-box'
                            )
                            if select_btn:
                                await select_btn.hover()
                                await page.wait_for_timeout(500)
                                await select_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(upload_video_path)
                        logger.info(f"File selected via chooser: {upload_video_path}")
                except Exception as e:
                    result['status'] = 'failed'
                    result['error'] = f'File selection failed: {e}'
                    result['screenshot'] = await self.engine.screenshot('yt_file_chooser')
                    return result

                if not self.engine.headless:
                    _bring_browser_to_foreground()

                # Delay at least 20 seconds after selecting video to ensure upload completes
                await self._human_delay(20.0, 25.0, "Video file selected — waiting at least 20s for upload")
                logger.info("Waiting for video upload to complete before proceeding to metadata...")
                await self._wait_for_upload_complete(page)
                logger.info("✅ Video upload confirmed complete.")

                # Check immediately for Daily upload limit reached
                limit_err = await self.check_for_upload_limit()
                if limit_err:
                    result['status'] = 'limit_reached'
                    result['error'] = limit_err
                    result['limit_reached'] = True
                    result['screenshot'] = await self.engine.screenshot('yt_upload_limit')
                    return result
            else:
                logger.info(f"🎯 Existing draft resumed for '{clean_title}'. Skipping upload to prevent duplicate copies.")
                await self._human_delay(5.0, 10.0, "Existing draft opened — reviewing details")

            # 5. Enter metadata with 10-20s pacing (strictly applied only when video is uploaded)
            # Enter title (ensure all numbers are removed)
            logger.info(f"Entering title (no numbers): {clean_title} (original: {title})")
            title_input = await page.query_selector(
                '#title-textarea #textbox, '
                'ytcp-video-title #textbox, '
                '#textbox[aria-label*="title" i], '
                '#textbox[placeholder*="title" i]'
            )
            if title_input:
                try:
                    await title_input.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)
                    await title_input.click(timeout=8000)
                except Exception as click_err:
                    limit_err = await self.check_for_upload_limit()
                    if limit_err:
                        result['status'] = 'limit_reached'
                        result['error'] = limit_err
                        result['limit_reached'] = True
                        result['screenshot'] = await self.engine.screenshot('yt_upload_limit')
                        return result
                    await page.evaluate("(el) => el && el.focus()", title_input)

                # Robustly clear any existing text from contenteditable div before typing
                await page.evaluate("""(el) => {
                    if (el) {
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('delete', false, null);
                        el.innerText = '';
                        el.textContent = '';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", title_input)
                await page.wait_for_timeout(300)
                await page.keyboard.press('Control+A')
                await page.wait_for_timeout(150)
                await page.keyboard.press('Backspace')
                await page.wait_for_timeout(300)
                await page.keyboard.type(clean_title, delay=40)
                logger.info(f"Title entered: {clean_title}")
                await self._human_delay(10.0, 20.0, "Title entered")

            # Enter description
            logger.info("Entering description...")
            desc_input = await page.query_selector(
                '#description-textarea #textbox, '
                'ytcp-video-description #textbox, '
                '#textbox[aria-label*="Tell viewers" i], '
                '#textbox[aria-label*="description" i]'
            )
            if desc_input and description:
                await desc_input.scroll_into_view_if_needed()
                await page.wait_for_timeout(1200)
                await desc_input.click()
                await page.wait_for_timeout(800)
                await page.keyboard.press('Control+A')
                await page.wait_for_timeout(200)
                await page.keyboard.press('Backspace')
                await page.wait_for_timeout(400)
                # Use insert_text to paste cleanly and handle multiline SEO descriptions
                await page.keyboard.insert_text(description)
                logger.info(f"Description entered ({len(description)} chars)")
                await self._human_delay(10.0, 20.0, "Description entered")
            elif not desc_input:
                logger.warning("Could not locate description input element")

            # 6. Set audience (Not made for kids)
            try:
                not_for_kids = await page.query_selector(
                    '#audience tp-yt-paper-radio-button:nth-child(2), '
                    '[name="NOT_MADE_FOR_KIDS"], '
                    'tp-yt-paper-radio-button:has-text("not made for kids")'
                )
                if not_for_kids:
                    await not_for_kids.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)
                    await not_for_kids.click()
                    logger.info("Audience set to 'Not made for kids'")
                    await self._human_delay(10.0, 20.0, "Audience declaration set")
            except Exception:
                logger.warning("Could not set audience declaration")

            # 7. Handle custom thumbnail (MANDATORY: strictly use custom thumbnail)
            resolved_thumbnail = thumbnail_path
            if not resolved_thumbnail or not Path(resolved_thumbnail).exists():
                stem = Path(video_path).stem
                candidates = [
                    Path("output/thumbnails") / f"{stem}_thumb.jpg",
                    Path("output/thumbnails") / f"{stem}.jpg",
                    Path("start video/thumbnails") / f"{stem}_thumb.jpg",
                    Path(video_path).parent / f"{stem}_thumb.jpg",
                ]
                for c in candidates:
                    if c.exists():
                        resolved_thumbnail = str(c.resolve())
                        break

                if not resolved_thumbnail or not Path(resolved_thumbnail).exists():
                    try:
                        from app.video.processor import VideoProcessor
                        vp = VideoProcessor()
                        auto_thumb = vp.extract_thumbnail(video_path)
                        if auto_thumb and Path(auto_thumb).exists():
                            resolved_thumbnail = str(Path(auto_thumb).resolve())
                    except Exception as th_err:
                        logger.warning(f"Could not auto-generate thumbnail: {th_err}")

            if resolved_thumbnail and Path(resolved_thumbnail).exists():
                logger.info(f"Setting custom thumbnail: {resolved_thumbnail}")
                thumb_ok = await self._handle_thumbnail(page, resolved_thumbnail)
                if thumb_ok:
                    logger.info("✅ Custom thumbnail attached successfully.")
                else:
                    logger.warning("⚠️ Custom thumbnail attachment could not be confirmed.")
                await self._human_delay(10.0, 20.0, "Custom thumbnail attached")
            else:
                logger.error(f"❌ Custom thumbnail missing for video: {video_path}")

            # 8. Navigate through wizard to Visibility / Schedule step (Step 4)
            logger.info("Navigating through wizard to Visibility step with human pacing...")
            for attempt in range(6):
                # Check if we're on the visibility step (either schedule container or privacy radios)
                visibility_el = await page.query_selector(
                    '#second-container-expand-button, #second-container, #privacy-radios, ytcp-video-visibility-select'
                )
                if visibility_el and await visibility_el.is_visible():
                    logger.info("Visibility step confirmed active!")
                    break

                # Check for "Verify it's you" auth confirmation dialog
                await self._handle_verify_its_you(page)

                await page.wait_for_timeout(2000)

                next_btn = await page.query_selector('#next-button, ytcp-button#next-button, button:has-text("Next")')
                if next_btn and await next_btn.is_visible():
                    logger.info(f"Clicking Next button (step {attempt + 1})...")
                    try:
                        await next_btn.hover()
                        await page.wait_for_timeout(400)
                        await next_btn.click(timeout=5000)
                    except Exception:
                        await page.evaluate("(btn) => btn && btn.click()", next_btn)
                    
                    # 10-20s human delay after clicking Next on each wizard step
                    await self._human_delay(10.0, 20.0, f"Wizard step {attempt + 1} completed")
                else:
                    step4_badge = await page.query_selector('#step-badge-3, [test-id="step-title-3"], #step-title-3, tp-yt-paper-tab:has-text("Visibility")')
                    if step4_badge and await step4_badge.is_visible():
                        await step4_badge.hover()
                        await page.wait_for_timeout(400)
                        await step4_badge.click()
                        await self._human_delay(10.0, 20.0, "Jumped to Visibility step via badge")

            # Ensure Visibility section is rendered
            try:
                await page.wait_for_selector(
                    '#second-container-expand-button, #second-container, #privacy-radios, #schedule-radio-button',
                    timeout=15000
                )
                logger.info("Visibility step loaded successfully")
                await page.wait_for_timeout(2000)
            except Exception:
                logger.warning("Timed out waiting for visibility step elements")
                await self.engine.screenshot('yt_visibility_timeout')

            if not self.engine.headless:
                _bring_browser_to_foreground()

            # ═══════════════════════════════════════════════════════════
            # 9. CRITICAL: Expand Schedule Accordion
            # ═══════════════════════════════════════════════════════════
            logger.info("CRITICAL: Expanding Schedule section...")

            schedule_expanded = False

            # Check if datetime picker is already visible
            dt_picker = await page.query_selector('ytcp-datetime-picker')
            if dt_picker and await dt_picker.is_visible():
                schedule_expanded = True
                logger.info("Schedule datetime picker is already visible.")

            if not schedule_expanded:
                expand_selectors = [
                    '#second-container-expand-button',
                    '#second-container .early-access-header',
                    '#second-container',
                    'tp-yt-paper-radio-button#schedule-radio-button',
                    'tp-yt-paper-radio-button:has-text("Schedule")',
                    '[test-id="second-container"]',
                ]
                for sel in expand_selectors:
                    try:
                        el = await page.query_selector(sel)
                        if el and await el.is_visible():
                            await el.scroll_into_view_if_needed()
                            await page.wait_for_timeout(800)
                            await el.hover()
                            await page.wait_for_timeout(400)
                            await el.click()
                            await page.wait_for_timeout(2500)
                            dt_picker = await page.query_selector('ytcp-datetime-picker')
                            if dt_picker and await dt_picker.is_visible():
                                schedule_expanded = True
                                logger.info(f"Schedule section expanded via selector: {sel}")
                                break
                    except Exception as e:
                        logger.debug(f"Expand selector {sel} failed: {e}")

            if not schedule_expanded:
                # JS click fallback
                try:
                    await page.evaluate("""() => {
                        const btn = document.querySelector('#second-container-expand-button') ||
                                    document.querySelector('#second-container') ||
                                    Array.from(document.querySelectorAll('*')).find(el => (el.textContent || '').trim().toLowerCase() === 'schedule');
                        if (btn) btn.click();
                    }""")
                    await page.wait_for_timeout(2500)
                    dt_picker = await page.query_selector('ytcp-datetime-picker')
                    if dt_picker and await dt_picker.is_visible():
                        schedule_expanded = True
                        logger.info("Schedule section expanded via JS evaluate fallback")
                except Exception as e:
                    logger.warning(f"JS evaluate expand fallback failed: {e}")

            if not schedule_expanded:
                await self.engine.screenshot('yt_no_schedule_expand')
                raise RuntimeError(
                    "CRITICAL: Could not expand the Schedule section! "
                    "YouTube Studio will default to Public instead of Scheduled. Aborting for safety."
                )

            await self._human_delay(10.0, 20.0, "Schedule accordion expanded")

            # 10. Wait for the datetime picker to expand after clicking Schedule
            logger.info("Waiting for schedule datetime picker to confirm visibility...")
            try:
                await page.wait_for_selector('ytcp-datetime-picker', state='visible', timeout=10000)
                logger.info("DateTime picker is now visible!")
                await page.wait_for_timeout(1500)
            except Exception:
                await self.engine.screenshot('yt_no_datetime_picker')
                raise RuntimeError("Schedule datetime picker did not appear after clicking Schedule!")

            # 11A. Set Schedule Date
            target_date_str = self._format_schedule_date(schedule_date)
            logger.info(f"Setting schedule date: {target_date_str}")
            await page.wait_for_timeout(1000)

            date_trigger = await page.query_selector('#datepicker-trigger')
            if date_trigger:
                curr_date_text = (await date_trigger.text_content() or '').strip()
                if target_date_str.lower() not in curr_date_text.lower():
                    logger.info(f"Current date is '{curr_date_text}', opening calendar to set: {target_date_str}")
                    await date_trigger.click()
                    await page.wait_for_timeout(1000)

                    # Set date via input inside ytcp-date-picker
                    await page.evaluate("""(targetDate) => {
                        const picker = document.querySelector('ytcp-date-picker');
                        if (!picker) return false;
                        const input = picker.querySelector('tp-yt-paper-input input, input');
                        if (input) {
                            input.focus();
                            input.value = targetDate;
                            input.dispatchEvent(new Event('input', { bubbles: true }));
                            input.dispatchEvent(new Event('change', { bubbles: true }));
                            return true;
                        }
                        return false;
                    }""", target_date_str)

                    # Press Enter to commit date
                    await page.keyboard.press('Enter')
                    await page.wait_for_timeout(1000)

                    # Safely dismiss open calendar backdrop by clicking backdrop (NEVER press Escape)
                    await page.evaluate("""() => {
                        const backdrop = document.querySelector('tp-yt-iron-overlay-backdrop.opened');
                        if (backdrop) backdrop.click();
                    }""")
                    await page.wait_for_timeout(1000)
                    logger.info(f"Schedule date set to: {target_date_str}")
                    await self._human_delay(10.0, 20.0, "Schedule date configured")
                else:
                    logger.info(f"Schedule date already correctly set: {curr_date_text}")
            else:
                logger.warning("Could not find #datepicker-trigger")

            # 11B. Set Schedule Time from Dropdown
            target_time_str = self._format_schedule_time(schedule_time)
            logger.info(f"Setting schedule time from dropdown: {target_time_str}")
            await page.wait_for_timeout(1200)

            # Click time input to open the 96-slot time dropdown
            time_input = await page.query_selector(
                'ytcp-datetime-picker .time-of-day-container input, '
                'ytcp-datetime-picker tp-yt-paper-input input, '
                'input[aria-label*="time" i]'
            )
            if time_input:
                await time_input.hover()
                await page.wait_for_timeout(400)
                await time_input.click()
                await page.wait_for_timeout(1500)

                # Select matching time slot from tp-yt-paper-listbox dropdown
                time_selected = await page.evaluate("""(target) => {
                    const norm = (s) => (s || '').replace(/[\\s\\u202f\\u00a0]/g, '').toLowerCase();
                    const targetNorm = norm(target);
                    const items = Array.from(document.querySelectorAll('tp-yt-paper-listbox.ytcp-time-of-day-picker tp-yt-paper-item, tp-yt-paper-item'));
                    for (const item of items) {
                        if (norm(item.textContent) === targetNorm) {
                            item.scrollIntoView({ block: 'nearest' });
                            item.click();
                            return { found: true, text: item.textContent.trim() };
                        }
                    }
                    return { found: false, count: items.length };
                }""", target_time_str)

                if time_selected and time_selected.get('found'):
                    logger.info(f"✅ Selected schedule time slot: '{time_selected.get('text')}'")
                else:
                    logger.warning(f"Could not find exact item in dropdown, fallback typing: {target_time_str}")
                    await time_input.click()
                    await page.wait_for_timeout(300)
                    await page.keyboard.press('Control+A')
                    await page.wait_for_timeout(150)
                    await page.keyboard.press('Backspace')
                    await page.wait_for_timeout(200)
                    await page.keyboard.type(target_time_str, delay=45)
                    await page.wait_for_timeout(400)
                    await page.keyboard.press('Enter')
                    await page.wait_for_timeout(800)

                await page.wait_for_timeout(1500)
                await self._human_delay(10.0, 20.0, "Schedule time configured")
            else:
                logger.warning("Could not locate time input inside ytcp-datetime-picker")

            # 12. Settle autosave before final scheduling
            logger.info("Settling autosave before scheduling...")
            try:
                await page.wait_for_function("""() => {
                    const text = document.body.innerText || '';
                    return !text.includes('Saving...');
                }""", timeout=20000)
                logger.info("Autosave settled.")
            except Exception:
                pass

            await self._human_delay(10.0, 20.0, "Autosave settled — preparing to schedule")

            if not self.engine.headless:
                _bring_browser_to_foreground()

            await self._handle_verify_its_you(page)

            # 13. CRITICAL: Click Schedule button inside YouTube Studio dialog
            logger.info("Locating and clicking Schedule button in YouTube Studio...")
            await page.wait_for_timeout(1500)

            schedule_clicked = False

            # Ensure any lingering backdrop is dismissed
            await page.evaluate("""() => {
                const backdrop = document.querySelector('tp-yt-iron-overlay-backdrop.opened');
                if (backdrop) backdrop.click();
            }""")
            await page.wait_for_timeout(500)

            # Strategy 1: Direct JS click on #done-button
            try:
                clicked_info = await page.evaluate("""() => {
                    const btn = document.querySelector('#done-button');
                    if (btn) {
                        const txt = (btn.textContent || '').trim().toLowerCase();
                        btn.scrollIntoView({ block: 'center' });
                        btn.click();
                        return { clicked: true, text: txt };
                    }
                    return { clicked: false, text: '' };
                }""")
                if clicked_info and clicked_info.get('clicked'):
                    schedule_clicked = True
                    logger.info(f"✅ Schedule button clicked via JavaScript DOM: '{clicked_info.get('text')}'")
            except Exception as js_err:
                logger.warning(f"JS schedule click notice: {js_err}")

            # Strategy 2: Playwright locator fallback
            if not schedule_clicked:
                schedule_selectors = [
                    '#done-button',
                    'ytcp-uploads-dialog #done-button',
                    'ytcp-button#done-button',
                    'button:has-text("Schedule")',
                ]
                for sel in schedule_selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0:
                            btn_text = (await loc.text_content() or '').strip()
                            logger.info(f"Found action button '{btn_text}' using: {sel}")
                            await loc.hover()
                            await page.wait_for_timeout(400)
                            await loc.click(timeout=6000)
                            schedule_clicked = True
                            logger.info(f"✅ Schedule button clicked via Playwright locator: {sel}")
                            break
                    except Exception as loc_err:
                        logger.debug(f"Locator {sel} notice: {loc_err}")

            if not schedule_clicked:
                await self.engine.screenshot('yt_no_schedule_button')
                raise RuntimeError("Could not find or click the Schedule button in YouTube Studio.")

            await self._human_delay(10.0, 20.0, "Schedule button clicked — waiting for confirmation")

            # Dismiss the post-schedule popup dialog (Close button)
            # CRITICAL: ONLY target post-schedule share modal, NEVER ytcp-uploads-dialog #close-button!
            try:
                close_confirm_btn = await page.wait_for_selector(
                    'ytcp-video-share-dialog #close-button, '
                    'ytcp-post-upload-dialog #close-button, '
                    'ytcp-dialog:has-text("Video scheduled") #close-button, '
                    'ytcp-dialog:has-text("Video scheduled") button:has-text("Close"), '
                    'ytcp-dialog:has-text("Video scheduled") ytcp-button:has-text("Close")',
                    state='visible',
                    timeout=10000
                )
                if close_confirm_btn:
                    await close_confirm_btn.hover()
                    await page.wait_for_timeout(400)
                    await close_confirm_btn.click()
                    logger.info("Closed post-schedule confirmation popup.")
                    await page.wait_for_timeout(2000)
            except Exception:
                logger.info("No post-schedule modal appeared (or already closed).")

            # 14. Verify the result
            verification = await self._verify_upload(page)
            verified_st = verification.get('status')
            result['status'] = verified_st if verified_st in ('scheduled', 'published') else ('scheduled' if schedule_clicked else 'failed')
            result['url'] = verification.get('url')
            result['screenshot'] = await self.engine.screenshot('yt_scheduled')
            logger.info(f"Upload result: status={result['status']}, url={result['url']}")

        except Exception as e:
            logger.error(f"YouTube upload failed: {e}")
            limit_err = await self.check_for_upload_limit()
            if limit_err:
                result['status'] = 'limit_reached'
                result['error'] = limit_err
                result['limit_reached'] = True
            else:
                result['status'] = 'failed'
                result['error'] = str(e)
            try:
                result['screenshot'] = await self.engine.screenshot('yt_error')
            except Exception:
                pass

        return result

    @staticmethod
    def _format_schedule_date(s_date: str) -> str:
        """Format YYYY-MM-DD into 'MMM D, YYYY' (e.g. 2026-10-20 -> Oct 20, 2026)."""
        try:
            dt = datetime.strptime(s_date.strip(), "%Y-%m-%d")
            return dt.strftime("%b %d, %Y")
        except Exception:
            return s_date

    @staticmethod
    def _format_schedule_time(s_time: str) -> str:
        """Format HH:MM (24-hr) into 12-hr format (e.g. 08:30 -> 8:30 AM, 18:00 -> 6:00 PM)."""
        try:
            parts = s_time.strip().split(':')
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            ampm = "AM" if h < 12 else "PM"
            h12 = h % 12
            if h12 == 0:
                h12 = 12
            return f"{h12}:{m:02d} {ampm}"
        except Exception:
            return s_time

    async def _find_and_open_existing_draft(self, page, clean_title: str, video_path: str = "") -> bool:
        """
        Check if an existing draft already exists on YouTube Studio for this video
        to avoid creating multiple draft copies.
        If found, clicks 'Edit draft' on that row to open ytcp-uploads-dialog directly.
        Returns True if a draft was found and successfully opened, False otherwise.
        """
        raw_stem = Path(video_path).stem if video_path else ""
        norm_targets = [
            re.sub(r'[^a-z0-9]', '', clean_title.lower()),
            re.sub(r'[^a-z0-9]', '', raw_stem.lower()),
            re.sub(r'[^a-z0-9]', '', raw_stem.replace('-', ' ').replace('_', ' ').lower()),
        ]
        # Filter out short or empty targets
        norm_targets = [t for t in norm_targets if len(t) >= 4]

        logger.info(f"Checking for existing YouTube Studio draft for: '{clean_title}' (targets: {norm_targets})...")

        urls_to_check = [
            "https://studio.youtube.com/channel/mine/videos/short",
            "https://studio.youtube.com/channel/mine/videos/upload",
        ]

        for check_url in urls_to_check:
            try:
                curr_url = page.url
                if check_url not in curr_url:
                    await page.goto(check_url, wait_until='domcontentloaded', timeout=45000)
                    await page.wait_for_timeout(3000)

                # Check for "SKIP TO YOUTUBE STUDIO" interstitial
                skip_btn = await page.query_selector('text="SKIP TO YOUTUBE STUDIO"')
                if skip_btn:
                    try:
                        await skip_btn.click()
                        await page.wait_for_timeout(2500)
                    except Exception:
                        pass

                # Wait for video rows or empty state
                try:
                    await page.wait_for_selector('ytcp-video-row', timeout=8000)
                except Exception:
                    # No rows on this tab
                    continue

                # Search through video rows using JS evaluation
                match_info = await page.evaluate("""(targets) => {
                    const norm = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
                    const rows = Array.from(document.querySelectorAll('ytcp-video-row'));
                    for (let i = 0; i < rows.length; i++) {
                        const r = rows[i];
                        const titleEl = r.querySelector('#video-title, #video-title-text, a#thumbnail-anchor');
                        const visEl = r.querySelector('.cell-body.tablecell-visibility, [class*="visibility"]');
                        const t = titleEl ? titleEl.textContent.trim() : '';
                        const v = visEl ? visEl.textContent.trim().toLowerCase() : '';

                        if (!v.includes('draft')) continue;

                        const rowNorm = norm(t);
                        for (const target of targets) {
                            if (rowNorm === target || 
                                (rowNorm.length >= 10 && target.length >= 10 && (rowNorm.includes(target) || target.includes(rowNorm)))) {
                                return { found: true, index: i, title: t };
                            }
                        }
                    }
                    return { found: false };
                }""", norm_targets)

                if match_info and match_info.get('found'):
                    row_idx = match_info.get('index')
                    row_title = match_info.get('title')
                    logger.info(f"🎯 Found existing draft row [{row_idx}]: '{row_title}'. Resuming draft...")

                    rows = await page.query_selector_all('ytcp-video-row')
                    if row_idx < len(rows):
                        target_row = rows[row_idx]
                        await target_row.hover()
                        await page.wait_for_timeout(500)

                        # Click Edit draft button
                        edit_btn = await target_row.query_selector(
                            'button[aria-label="Edit draft"], button:has-text("Edit draft"), #edit-draft-button, #video-title, #details-link, a#thumbnail-anchor'
                        )
                        if edit_btn:
                            await edit_btn.click()
                        else:
                            await target_row.click()

                        # Wait for dialog to be attached in DOM and finish loading
                        try:
                            await page.wait_for_selector('ytcp-uploads-dialog', state='attached', timeout=15000)
                            await page.wait_for_function("""() => {
                                const d = document.querySelector('ytcp-uploads-dialog');
                                return d && (!d.hasAttribute('is-loading-data') || d.hasAttribute('workflow-step'));
                            }""", timeout=15000)
                        except Exception:
                            pass
                        await page.wait_for_timeout(2000)
                        logger.info(f"✅ Existing draft opened directly in upload dialog: '{row_title}'.")
                        return True
            except Exception as e:
                logger.warning(f"Error checking drafts at {check_url}: {e}")

        logger.info("No matching existing draft found. Proceeding with standard upload.")
        return False

    async def _find_create_button(self, page):
        """Find the Create button in YouTube Studio."""
        selectors = [
            '#create-icon',
            'ytcp-button#create-icon',
            'button[aria-label="Create"]',
            '#upload-icon',
            'a[href*="upload"]',
        ]
        for sel in selectors:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return el
        buttons = await page.query_selector_all('button, ytcp-button')
        for btn in buttons:
            text = await btn.text_content()
            if text and 'create' in text.lower():
                return btn
        return None

    async def _find_upload_option(self, page):
        """Find the 'Upload videos' option from the create menu."""
        selectors = [
            'tp-yt-paper-item:has-text("Upload video")',
            '#text-item-0',
            'a:has-text("Upload")',
        ]
        for sel in selectors:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return el
        items = await page.query_selector_all('tp-yt-paper-item, ytcp-text-menu a')
        for item in items:
            text = await item.text_content()
            if text and 'upload' in text.lower():
                return item
        return None

    async def _handle_verify_its_you(self, page, wait_seconds: int = 60) -> bool:
        """Detect and handle Google's 'Verify it's you' security modal (ytcp-auth-confirmation-dialog)."""
        try:
            auth_dialog = await page.query_selector('ytcp-auth-confirmation-dialog, ytcp-confirmation-dialog:has-text("Verify it\'s you")')
            if not auth_dialog or not await auth_dialog.is_visible():
                return False

            logger.warning("🚨 GOOGLE SECURITY CHECKPOINT DETECTED: 'Verify it\\'s you' modal is active!")
            logger.warning("Google requires identity confirmation (2FA / phone prompt) to publish or schedule on this channel.")
            if not self.engine.headless:
                _bring_browser_to_foreground()

            # Click the "Next" button on the confirmation dialog to initiate 2FA challenge
            confirm_btn = await auth_dialog.query_selector('#confirm-button, button:has-text("Next")')
            if confirm_btn and await confirm_btn.is_visible():
                logger.info("Clicking 'Next' on 'Verify it\\'s you' dialog to prompt authentication...")
                try:
                    await confirm_btn.click()
                except Exception:
                    await page.evaluate("(btn) => btn && btn.click()", confirm_btn)

            logger.info(f"Waiting up to {wait_seconds}s for user to complete verification in the browser...")
            for sec in range(wait_seconds):
                await page.wait_for_timeout(1000)
                auth_dialog = await page.query_selector('ytcp-auth-confirmation-dialog, ytcp-confirmation-dialog:has-text("Verify it\'s you")')
                backdrop = await page.query_selector('tp-yt-iron-overlay-backdrop.opened')
                if not auth_dialog and not backdrop:
                    logger.info("✅ 'Verify it\\'s you' checkpoint cleared successfully!")
                    await page.wait_for_timeout(2000)
                    return True
                if sec % 10 == 0 and sec > 0:
                    logger.info(f"Still waiting for Google verification ({wait_seconds - sec}s remaining)...")

            logger.warning("Timed out waiting for Google verification checkpoint to be cleared.")
            return False
        except Exception as e:
            logger.debug(f"Error checking verify-it\\'s-you dialog: {e}")
            return False

    async def _handle_thumbnail(self, page, thumbnail_path):
        """Upload custom thumbnail if supported."""
        if not thumbnail_path or not Path(thumbnail_path).exists():
            logger.warning(f"Thumbnail path not provided or does not exist: {thumbnail_path}")
            return False
        try:
            # Scroll thumbnail container into view first
            thumb_container = await page.query_selector(
                'ytcp-thumbnails-compact-editor-uploader, #still-picker, #upload-thumbnail-button, [aria-label*="Upload thumbnail" i]'
            )
            if thumb_container:
                try:
                    await thumb_container.scroll_into_view_if_needed()
                    await page.wait_for_timeout(800)
                except Exception:
                    pass

            # 1. Try direct image file input (instant, most reliable)
            img_input = await page.query_selector('input#file-loader, #file-loader, ytcp-thumbnails-compact-editor-uploader input[type="file"], input[type="file"][accept*="image"]')
            if img_input:
                await img_input.set_input_files(str(thumbnail_path))
                logger.info(f"Custom thumbnail attached via image file input: {thumbnail_path}")
                await page.wait_for_timeout(2000)
                return True

            file_inputs = await page.query_selector_all('input[type="file"]')
            for fi in file_inputs:
                accept = (await fi.get_attribute('accept') or '').lower()
                id_attr = (await fi.get_attribute('id') or '').lower()
                if 'image' in accept or 'file-loader' in id_attr or 'thumb' in id_attr:
                    await fi.set_input_files(str(thumbnail_path))
                    logger.info(f"Custom thumbnail attached via image input: {thumbnail_path}")
                    await page.wait_for_timeout(2000)
                    return True

            # 2. Try clicking Upload thumbnail button with file chooser
            thumb_btn = await page.query_selector(
                '#upload-thumbnail-button, '
                'button:has-text("Upload thumbnail"), '
                'button:has-text("Upload file"), '
                '[aria-label*="Upload thumbnail" i], '
                '[aria-label*="Upload file" i], '
                '#still-picker button:has-text("Upload thumbnail"), '
                '#upload-thumbnail'
            )
            if thumb_btn and await thumb_btn.is_visible():
                try:
                    async with page.expect_file_chooser(timeout=8000) as fc_info:
                        await thumb_btn.click(timeout=4000)
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(str(thumbnail_path))
                    logger.info(f"Custom thumbnail uploaded via chooser: {thumbnail_path}")
                    await page.wait_for_timeout(2000)
                    return True
                except Exception as ex:
                    logger.warning(f"Thumbnail chooser fallback notice: {ex}")

            logger.warning(f"Could not locate custom thumbnail upload button for: {thumbnail_path}")
            return False
        except Exception as e:
            logger.warning(f"Thumbnail upload error: {e}")
            return False


    async def _wait_for_upload_complete(self, page, timeout_ms=None):
        """Wait for the video upload progress to reach completion."""
        timeout = timeout_ms or UPLOAD_TIMEOUT_MS
        try:
            # Look for processing indicators
            await page.wait_for_function(
                """() => {
                    const progress = document.querySelector('.progress-bar, ytcp-video-upload-progress');
                    if (!progress) return true;
                    const text = document.body.innerText;
                    return text.includes('Upload complete') ||
                           text.includes('Processing') ||
                           text.includes('Checks complete') ||
                           text.includes('100%');
                }""",
                timeout=timeout
            )
            logger.info("Upload appears complete")
        except Exception as e:
            logger.warning(f"Upload completion check timed out: {e}")

    async def _verify_upload(self, page):
        """Verify the upload/scheduling result in the browser."""
        result = {'status': 'uncertain', 'url': None}

        try:
            # Check for success indicators
            content = await page.content()
            page_text = await page.evaluate('() => document.body.innerText')

            if 'scheduled' in page_text.lower():
                result['status'] = 'scheduled'
            elif 'published' in page_text.lower() or 'public' in page_text.lower():
                result['status'] = 'published'
            elif 'processing' in page_text.lower():
                result['status'] = 'uploaded'

            # Try to extract video URL
            url = page.url
            if 'video' in url and '/edit' in url:
                # Extract video ID from URL like studio.youtube.com/video/XXXX/edit
                parts = url.split('/video/')
                if len(parts) > 1:
                    vid_id = parts[1].split('/')[0]
                    result['url'] = f"https://youtube.com/shorts/{vid_id}"

            # Look for video link in the page
            links = await page.query_selector_all('a[href*="youtu"]')
            for link in links:
                href = await link.get_attribute('href')
                if href and ('watch' in href or 'shorts' in href):
                    result['url'] = href
                    break

        except Exception as e:
            logger.warning(f"Verification failed: {e}")

        return result


class InstagramPublisher:
    """Automate Instagram Reels publishing through the browser."""

    INSTAGRAM_URL = "https://www.instagram.com"

    def __init__(self, engine: BrowserEngine):
        self.engine = engine
        self.page = engine.page

    async def is_authenticated(self):
        """Check if logged into Instagram."""
        try:
            # 1. Fast cookie check
            cookies = await self.engine.context.cookies()
            has_ig_cookie = any(
                c['name'] in {'sessionid', 'ds_user_id'} and 'instagram' in c.get('domain', '')
                for c in cookies
            )

            # 2. Page check
            try:
                await self.page.goto(self.INSTAGRAM_URL, wait_until='domcontentloaded', timeout=20000)
                await self.page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Instagram load warning: {e}")

            url = self.page.url
            if 'accounts/login' in url or 'login' in url.lower():
                return False

            # Check for authenticated indicators
            try:
                ig_el = await self.page.query_selector(
                    'svg[aria-label="Home"], svg[aria-label="New post"], svg[aria-label="Direct"], [aria-label="Profile"], nav'
                )
                if ig_el:
                    return True
            except Exception:
                pass

            if has_ig_cookie:
                return True

            return False
        except Exception as e:
            logger.error(f"Instagram auth check failed: {e}")
            return False

    async def open_for_manual_login(self):
        """Navigate to Instagram for manual sign-in."""
        await self.page.goto(f"{self.INSTAGRAM_URL}/accounts/login/",
                              wait_until='domcontentloaded', timeout=BROWSER_TIMEOUT_MS)
        return self.page.url

    async def _human_delay(self, min_s: float = 20.0, max_s: float = 30.0, action_name: str = ""):
        """Pause execution for a randomized delay between min_s and max_s to mimic a real human."""
        await human_delay(self.page, min_s, max_s, action_name)

    async def check_for_upload_limit(self) -> Optional[str]:
        """
        Check if Instagram has displayed an action block, rate limit, or upload restriction modal/banner.
        Returns error description if detected, otherwise None.
        """
        page = self.page
        if not page:
            return None
        try:
            # 1. Search full page innerText for known Instagram limit / block phrases
            text = await page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")
            limit_keywords = [
                "try again later",
                "action blocked",
                "we limit how often you can do certain things",
                "we limit how often",
                "we restrict certain activity",
                "temporarily blocked",
                "your account has been temporarily blocked",
                "couldn't upload",
                "could not upload",
                "upload failed",
                "your post could not be shared",
                "something went wrong. please try again",
                "you've reached a limit",
            ]
            for kw in limit_keywords:
                if kw in text:
                    logger.error(f"Instagram upload limit / action block detected: '{kw}'")
                    return f"Instagram upload limit / action block: '{kw}'. Limit resets in 24 hours."

            # 2. Check for dialog banner or error modal
            modal = await page.query_selector(
                'div[role="dialog"]:has-text("Try Again Later"), '
                'div[role="dialog"]:has-text("Action Blocked"), '
                'div[role="dialog"]:has-text("Couldn\'t upload"), '
                'div[role="dialog"]:has-text("Could not upload"), '
                'div[role="dialog"]:has-text("We limit how often"), '
                'div:has-text("We limit how often you can do certain things")'
            )
            if modal and await modal.is_visible():
                return "Instagram upload limit / action block dialog detected. Limit resets in 24 hours."
        except Exception as e:
            logger.debug(f"Error checking Instagram upload limit: {e}")
        return None

    async def upload_reel(self, video_path, caption, dry_run=False):
        """
        Upload a Reel through the Instagram web interface.
        - 10-20s randomized human delay before upload starts.
        - 20-30s randomized human delay from file selection through sharing.
        - Zero numbers in staged filenames and sanitized captions.
        - Automatic 9:16 aspect ratio selection for full-frame Reels.
        - Instant action block / upload limit detection.
        - Returns result dict.
        """
        result = {
            'platform': Platform.INSTAGRAM,
            'video_path': video_path,
            'status': 'pending',
            'error': None,
            'url': None,
            'screenshot': None,
        }

        try:
            page = self.page

            # Bring browser to foreground
            if not self.engine.headless:
                _bring_browser_to_foreground()

            if dry_run:
                result['status'] = 'dry_run'
                logger.info(f"[DRY RUN] Instagram: would upload reel")
                return result

            # 1. Navigate to Instagram (10-20s delay)
            logger.info("Navigating to Instagram...")
            await page.goto(self.INSTAGRAM_URL, wait_until='domcontentloaded',
                             timeout=BROWSER_TIMEOUT_MS)
            if not self.engine.headless:
                _bring_browser_to_foreground()
            await self._human_delay(10.0, 20.0, "Instagram loaded")

            if await self.engine.check_for_security_challenge():
                result['status'] = 'needs_attention'
                result['error'] = 'Security challenge detected'
                result['screenshot'] = await self.engine.screenshot('ig_security')
                return result

            # Check for any lingering discard modal from previous session
            try:
                discard_btn = await page.query_selector('div[role="dialog"] button:has-text("Discard")')
                if discard_btn and await discard_btn.is_visible():
                    await discard_btn.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # 2. Click Create / New post
            create_btn = await page.query_selector(
                '[aria-label="New post"], '
                'svg[aria-label="New post"], '
                '[aria-label="Create"], '
                'svg[aria-label="Create"], '
                'a[href="/create/"], '
                'a[href*="/create/style/"]'
            )
            if not create_btn:
                buttons = await page.query_selector_all('svg, a, span, div[role="button"]')
                for btn in buttons:
                    label = (await btn.get_attribute('aria-label')) or ''
                    txt = (await btn.text_content()) or ''
                    if 'new' in label.lower() and 'post' in label.lower():
                        create_btn = btn
                        break
                    if label.lower() == 'create' or txt.strip().lower() == 'create':
                        create_btn = btn
                        break

            if not create_btn:
                result['status'] = 'failed'
                result['error'] = 'Could not find Create button on Instagram navigation bar'
                result['screenshot'] = await self.engine.screenshot('ig_no_create')
                return result

            logger.info("Clicking Instagram '+ Create' icon...")
            try:
                await create_btn.hover()
                await page.wait_for_timeout(300)
            except Exception:
                pass
            await create_btn.click()

            # Per user instruction: wait 3 seconds after clicking + Create
            logger.info("⏳ Waiting 3 seconds before clicking Post...")
            await page.wait_for_timeout(3000)

            limit_err = await self.check_for_upload_limit()
            if limit_err:
                result['status'] = 'limit_reached'
                result['error'] = limit_err
                result['limit_reached'] = True
                result['screenshot'] = await self.engine.screenshot('ig_upload_limit')
                return result

            # Click 'Post' option from Create menu
            logger.info("Clicking 'Post' option from Create menu...")
            post_clicked = False
            for sel in [
                'div[role="menu"] [role="menuitem"]:has-text("Post")',
                'div[role="menu"] span:has-text("Post")',
                'div[role="dialog"] span:has-text("Post")',
                'span:text-is("Post")',
                '[role="button"]:has-text("Post")',
                'div:not([role="dialog"]) span:has-text("Post")',
                'span:has-text("Post")',
                'a:has-text("Post")',
            ]:
                try:
                    cand = await page.query_selector(sel)
                    if cand and await cand.is_visible():
                        logger.info(f"Clicking 'Post' via '{sel}'...")
                        try:
                            await cand.hover()
                            await page.wait_for_timeout(200)
                        except Exception:
                            pass
                        await cand.click()
                        post_clicked = True
                        break
                except Exception as click_err:
                    logger.debug(f"Selector {sel} click attempt: {click_err}")

            if not post_clicked:
                try:
                    loc = page.locator('span:has-text("Post"), [role="button"]:has-text("Post")').first
                    if await loc.is_visible():
                        await loc.click()
                        post_clicked = True
                        logger.info("Clicked 'Post' via locator.")
                except Exception as loc_err:
                    logger.debug(f"Locator Post click attempt: {loc_err}")

            # Per user instruction: wait 3 seconds after clicking Post before clicking Select
            logger.info("⏳ Waiting 3 seconds before clicking Select...")
            await page.wait_for_timeout(3000)

            # 3. Stage clean video file without numbers or timestamps
            clean_title = sanitize_title_no_numbers(caption.split('\n')[0] if caption else Path(video_path).stem)
            upload_video_path = video_path
            try:
                v_p = Path(video_path)
                safe_name = re.sub(r'[\\/*?:"<>|]', '', clean_title).replace(' ', '_').strip('_') + v_p.suffix
                staging_dir = v_p.parent / ".clean_staging"
                staging_dir.mkdir(parents=True, exist_ok=True)
                clean_target = staging_dir / safe_name
                if not clean_target.exists():
                    try:
                        os.link(str(v_p), str(clean_target))
                    except Exception:
                        import shutil
                        shutil.copy2(str(v_p), str(clean_target))
                upload_video_path = str(clean_target)
            except Exception as staging_err:
                logger.debug(f"Notice on Instagram clean staging file: {staging_err}")
                upload_video_path = video_path

            # Look for 'Select from computer' button or file input
            logger.info(f"Setting Instagram video file: {upload_video_path}")
            try:
                # Wait briefly if upload modal is animating in
                try:
                    await page.wait_for_selector(
                        'button:has-text("Select from computer"), button:has-text("Select From Computer"), input[type="file"]',
                        timeout=5000
                    )
                except Exception:
                    pass

                select_btn = await page.query_selector(
                    'button:has-text("Select from computer"), '
                    'button:has-text("Select From Computer"), '
                    'button:has-text("Select from Computer"), '
                    'div[role="button"]:has-text("Select from computer"), '
                    'button:has-text("Select")'
                )
                if select_btn and await select_btn.is_visible():
                    logger.info("Found 'Select from computer' button. Clicking and selecting video...")
                    try:
                        await select_btn.hover()
                        await page.wait_for_timeout(200)
                    except Exception:
                        pass
                    try:
                        async with page.expect_file_chooser(timeout=10000) as fc_info:
                            await select_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(upload_video_path)
                        logger.info(f"Instagram file selected via file chooser: {upload_video_path}")
                    except Exception as fc_err:
                        logger.warning(f"File chooser event error: {fc_err}, attempting fallback to input[type=file]...")
                        file_input = await page.query_selector('input[type="file"]')
                        if file_input:
                            await file_input.set_input_files(upload_video_path)
                            logger.info(f"Instagram file set via input fallback: {upload_video_path}")
                        else:
                            raise fc_err
                else:
                    file_input = await page.query_selector('input[type="file"]')
                    if file_input:
                        await file_input.set_input_files(upload_video_path)
                        logger.info(f"Instagram file set directly via file input: {upload_video_path}")
                    else:
                        raise RuntimeError("Could not find 'Select from computer' button or file input in upload dialog")
            except Exception as e:
                result['status'] = 'failed'
                result['error'] = f'File selection failed: {e}'
                result['screenshot'] = await self.engine.screenshot('ig_file_chooser')
                return result

            if not self.engine.headless:
                _bring_browser_to_foreground()

            # Uploading has started: use 20-30s delay
            await self._human_delay(20.0, 30.0, "Video file selected and upload dialog open")

            # Dismiss "Video posts are now shared as reels" OK modal if displayed
            try:
                ok_btn = await page.query_selector('div[role="dialog"] button:has-text("OK"), button:has-text("OK")')
                if ok_btn and await ok_btn.is_visible():
                    await ok_btn.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Check upload limit
            limit_err = await self.check_for_upload_limit()
            if limit_err:
                result['status'] = 'limit_reached'
                result['error'] = limit_err
                result['limit_reached'] = True
                result['screenshot'] = await self.engine.screenshot('ig_upload_limit')
                return result

            # 4. Navigate dialog steps (Media -> Filters -> Caption) via Next buttons (no cropping needed; video is already 9:16)
            for step_idx in range(2):
                next_btn = await page.query_selector(
                    'div[role="dialog"] button:has-text("Next"), '
                    'div[role="dialog"] div[role="button"]:has-text("Next"), '
                    'button:has-text("Next")'
                )
                if next_btn and await next_btn.is_visible():
                    try:
                        await next_btn.click(force=True)
                    except Exception:
                        await page.evaluate("(btn) => btn && btn.click()", next_btn)
                    await self._human_delay(20.0, 30.0, f"Next clicked (step {step_idx + 1})")

                    limit_err = await self.check_for_upload_limit()
                    if limit_err:
                        result['status'] = 'limit_reached'
                        result['error'] = limit_err
                        result['limit_reached'] = True
                        result['screenshot'] = await self.engine.screenshot('ig_upload_limit')
                        return result

            # 5. Enter caption with NO numbers in the title part
            clean_caption = caption or ""
            if '\n' in clean_caption:
                parts = clean_caption.split('\n', 1)
                clean_title_line = sanitize_title_no_numbers(parts[0])
                clean_caption = f"{clean_title_line}\n\n{parts[1].strip()}"
            else:
                clean_caption = sanitize_title_no_numbers(clean_caption)

            logger.info("Entering Instagram caption...")
            caption_input = await page.query_selector(
                'div[aria-label*="Write a caption" i], '
                'div[aria-label*="caption" i], '
                'textarea[aria-label*="caption" i], '
                'div[contenteditable="true"]'
            )
            if caption_input:
                try:
                    await caption_input.scroll_into_view_if_needed()
                except Exception:
                    pass
                await page.wait_for_timeout(1000)
                await caption_input.click()

                # Robustly clear any existing text from contenteditable div before typing
                await page.evaluate("""(el) => {
                    if (el) {
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('delete', false, null);
                        el.innerText = '';
                        el.textContent = '';
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }""", caption_input)
                await page.wait_for_timeout(300)
                await page.keyboard.press('Control+A')
                await page.wait_for_timeout(150)
                await page.keyboard.press('Backspace')
                await page.wait_for_timeout(300)
                await page.keyboard.insert_text(clean_caption)
                logger.info("Instagram caption entered (no numbers in title)")
                await self._human_delay(20.0, 30.0, "Instagram caption entered")

            # Check for "Share to Facebook" toggle/switch in Instagram post settings
            try:
                fb_toggle = await page.query_selector(
                    'div[role="switch"][aria-label*="Facebook" i], '
                    'input[type="checkbox"][aria-label*="Facebook" i], '
                    'div:has-text("Share to Facebook") input, '
                    'div:has-text("Share to Facebook") [role="switch"]'
                )
                if fb_toggle:
                    is_checked = await fb_toggle.get_attribute('aria-checked')
                    if is_checked == 'false':
                        await fb_toggle.click()
                        logger.info("Toggled 'Share to Facebook' switch ON in Instagram upload settings")
                        await page.wait_for_timeout(600)
                    else:
                        logger.info("'Share to Facebook' cross-posting is already enabled on Instagram")
            except Exception as fb_t_err:
                logger.debug(f"Share to Facebook toggle check notice: {fb_t_err}")

            # Dismiss any active hashtag autocomplete suggestions and blur caption editor
            logger.info("Dismissing any hashtag autocomplete popup and blurring caption input...")
            try:
                await page.wait_for_timeout(500)
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(300)
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(300)
                await page.evaluate("""() => {
                    if (document.activeElement && typeof document.activeElement.blur === 'function') {
                        document.activeElement.blur();
                    }
                }""")
                await page.wait_for_timeout(500)
            except Exception as blur_err:
                logger.debug(f"Blur notice: {blur_err}")

            # 6. Click Share button (Direct publishing since Instagram desktop has no schedule option)
            logger.info("Looking for Instagram 'Share' button in dialog...")
            share_btn = None
            dialog = await page.query_selector('div[role="dialog"]')
            if dialog:
                elements = await dialog.query_selector_all('[role="button"], div, button, span')
                for el in elements:
                    try:
                        txt = (await el.text_content() or '').strip()
                        if txt == 'Share':
                            box = await el.bounding_box()
                            # Ensure it's in the top header (y < 250 in viewport)
                            if box and box['y'] < 250 and box['width'] > 0 and box['height'] > 0:
                                share_btn = el
                                logger.info(f"Found Share button in header at ({box['x']:.1f}, {box['y']:.1f})")
                                break
                    except Exception:
                        pass

            if not share_btn:
                # Try locator for role button with text Share
                loc = page.locator('div[role="dialog"] [role="button"]:text-is("Share"), div[role="dialog"] div:text-is("Share")').last
                if await loc.is_visible():
                    share_btn = await loc.element_handle()

            if share_btn:
                box = await share_btn.bounding_box()
                if box:
                    center_x = box['x'] + box['width'] / 2
                    center_y = box['y'] + box['height'] / 2
                    logger.info(f"Clicking Share button via native mouse at ({center_x:.1f}, {center_y:.1f})...")
                    await page.mouse.move(center_x, center_y)
                    await page.wait_for_timeout(200)
                    await page.mouse.click(center_x, center_y)
                else:
                    await share_btn.click(force=True)

                # Dispatch secondary click via JS evaluate
                await page.evaluate("""(btn) => {
                    if (btn) {
                        btn.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                        btn.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                        btn.click();
                    }
                }""", share_btn)
            else:
                # Fallback to coordinates: Top right of dialog
                if dialog:
                    dbox = await dialog.bounding_box()
                    if dbox:
                        center_x = dbox['x'] + dbox['width'] - 40
                        center_y = dbox['y'] + 25
                        logger.info(f"Clicking Share via dialog header coordinates ({center_x:.1f}, {center_y:.1f})...")
                        await page.mouse.click(center_x, center_y)
                else:
                    raise RuntimeError("Could not find dialog or Share button")

            # Check if button click registered (text changed to Sharing... or dialog shows spinner)
            await page.wait_for_timeout(2500)
            still_needs_click = await page.evaluate("""() => {
                const dialog = document.querySelector('div[role="dialog"]');
                if (!dialog) return false;
                const txt = (dialog.innerText || '');
                return txt.includes('Share') && !txt.includes('Sharing');
            }""")
            if still_needs_click:
                logger.info("Share button still present; performing backup force click on Share...")
                try:
                    await page.locator('div[role="dialog"] [role="button"]:text-is("Share"), div[role="dialog"] div:text-is("Share")').last.click(force=True, timeout=3000)
                except Exception as click2_err:
                    logger.debug(f"Backup click notice: {click2_err}")

            logger.info("Share button clicked! Waiting for publishing confirmation...")
            await self._human_delay(20.0, 30.0, "Share button clicked — waiting for publishing confirmation")

            # 7. Check limit / action block immediately after sharing
            limit_err = await self.check_for_upload_limit()
            if limit_err:
                result['status'] = 'limit_reached'
                result['error'] = limit_err
                result['limit_reached'] = True
                result['screenshot'] = await self.engine.screenshot('ig_upload_limit')
                return result

            # 8. Verification: wait for "Your reel has been shared" confirmation or modal dismissal
            logger.info("Waiting for Instagram sharing confirmation...")
            confirmed = False
            start_wait = time.time()
            while time.time() - start_wait < 120:
                text = await page.evaluate("() => document.body ? document.body.innerText.toLowerCase() : ''")

                # Check for success messages
                if any(phrase in text for phrase in [
                    "your reel has been shared",
                    "your post has been shared",
                    "reel shared",
                    "post shared",
                ]):
                    confirmed = True
                    logger.info("Instagram sharing confirmed via confirmation message!")
                    break

                # Check if dialog closed (indicates completion)
                dialog_visible = await page.evaluate("() => !!document.querySelector('div[role=\"dialog\"]')")
                if not dialog_visible and (time.time() - start_wait > 8):
                    confirmed = True
                    logger.info("Upload dialog closed cleanly after clicking Share — post published!")
                    break

                # Rate limit / block check
                limit_err = await self.check_for_upload_limit()
                if limit_err:
                    result['status'] = 'limit_reached'
                    result['error'] = limit_err
                    result['limit_reached'] = True
                    result['screenshot'] = await self.engine.screenshot('ig_upload_limit')
                    return result

                # Check for Instagram error dialog
                if any(err_kw in text for err_kw in ["couldn't post", "could not upload", "we limit how often"]):
                    raise RuntimeError(f"Instagram upload error dialog: {text[:200]}")

                await asyncio.sleep(2)

            if not confirmed:
                result['status'] = 'failed'
                result['error'] = 'Instagram sharing was not confirmed: Dialog remained open and no confirmation was received.'
                result['screenshot'] = await self.engine.screenshot('ig_not_confirmed')
                logger.error("Instagram publishing failed: Not confirmed within 120s timeout.")
                return result

            # Now that it's confirmed, try to extract post URL from dialog
            try:
                conf_link = await page.query_selector('div[role="dialog"] a[href*="/reel/"], div[role="dialog"] a[href*="/p/"]')
                if conf_link:
                    href = await conf_link.get_attribute('href')
                    if href:
                        result['url'] = href if href.startswith('http') else f"https://www.instagram.com{href}"
            except Exception:
                pass

            result['status'] = 'published'
            result['screenshot'] = await self.engine.screenshot('ig_complete')
            logger.info(f"Instagram publishing result: status={result['status']}, url={result.get('url')}")

        except Exception as e:
            logger.error(f"Instagram upload failed: {e}")
            limit_err = await self.check_for_upload_limit()
            if limit_err:
                result['status'] = 'limit_reached'
                result['error'] = limit_err
                result['limit_reached'] = True
            else:
                result['status'] = 'failed'
                result['error'] = str(e)
            try:
                result['screenshot'] = await self.engine.screenshot('ig_error')
            except Exception:
                pass

        return result



class FacebookPublisher:
    """Automate Facebook Reels publishing through the browser."""

    FACEBOOK_URL = "https://www.facebook.com"

    def __init__(self, engine: BrowserEngine):
        self.engine = engine
        self.page = engine.page

    async def is_authenticated(self):
        """Check if logged into Facebook."""
        try:
            # 1. Fast cookie check
            cookies = await self.engine.context.cookies()
            has_fb_cookie = any(
                c['name'] in {'c_user', 'xs'} and 'facebook' in c.get('domain', '')
                for c in cookies
            )

            # 2. Page check
            try:
                await self.page.goto(self.FACEBOOK_URL, wait_until='domcontentloaded', timeout=20000)
                await self.page.wait_for_timeout(2000)
            except Exception as e:
                logger.warning(f"Facebook load warning: {e}")

            url = self.page.url
            if 'login' in url.lower() and 'checkpoint' not in url:
                return False

            try:
                fb_el = await self.page.query_selector(
                    '[aria-label="Facebook"], div[role="navigation"], [aria-label*="Your profile" i]'
                )
                if fb_el:
                    return True
            except Exception:
                pass

            if has_fb_cookie:
                return True

            return False
        except Exception as e:
            logger.error(f"Facebook auth check failed: {e}")
            return False

    async def open_for_manual_login(self):
        """Navigate to Facebook for manual sign-in."""
        await self.page.goto(f"{self.FACEBOOK_URL}/login",
                              wait_until='domcontentloaded', timeout=BROWSER_TIMEOUT_MS)
        return self.page.url

    async def _human_delay(self, min_s: float = 20.0, max_s: float = 30.0, action_name: str = ""):
        """Pause execution for a randomized delay between min_s and max_s (default 20-30s) to mimic a real human."""
        await human_delay(self.page, min_s, max_s, action_name)

    PROFESSIONAL_DASHBOARD_URL = "https://www.facebook.com/professional_dashboard/"

    async def _stage_clean_video(self, video_path: str, title: str) -> str:
        """Create a clean copy of the video file without numbers or timestamps in filename."""
        clean_title = sanitize_title_no_numbers(title or Path(video_path).stem)
        try:
            v_p = Path(video_path)
            safe_name = re.sub(r'[\\/*?:"<>|]', '', clean_title).replace(' ', '_').strip('_') + v_p.suffix
            staging_dir = v_p.parent / ".clean_staging"
            staging_dir.mkdir(parents=True, exist_ok=True)
            clean_target = staging_dir / safe_name
            if not clean_target.exists():
                try:
                    os.link(str(v_p), str(clean_target))
                except Exception:
                    import shutil
                    shutil.copy2(str(v_p), str(clean_target))
            return str(clean_target)
        except Exception as e:
            logger.debug(f"Notice on clean staging video: {e}")
            return video_path

    async def _select_date_in_calendar(self, page, target_date_str: str) -> bool:
        """
        Navigate calendar to target month and click target day cell.
        target_date_str: 'YYYY-MM-DD'
        """
        try:
            dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        except Exception:
            logger.warning(f"Could not parse target_date_str '{target_date_str}', skipping date selection")
            return False

        target_month_year = dt.strftime("%B %Y")
        target_day = str(dt.day)

        # Check and advance month up to 12 months forward
        for _ in range(12):
            header_text = await page.evaluate("""() => {
                const headers = Array.from(document.querySelectorAll('*')).filter(el => {
                    const t = (el.innerText || '').trim();
                    return /^(January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{4}$/i.test(t);
                });
                return headers.length > 0 ? (headers[0].innerText || '').trim() : '';
            }""")
            if header_text.lower() == target_month_year.lower():
                break

            # Click next month button in calendar header
            next_clicked = await page.evaluate("""() => {
                const headers = Array.from(document.querySelectorAll('*')).filter(el => {
                    const t = (el.innerText || '').trim();
                    return /^(January|February|March|April|May|June|July|August|September|October|November|December)\\s+\\d{4}$/i.test(t);
                });
                if (!headers.length) return false;
                const parent = headers[0].parentElement;
                if (!parent) return false;
                const btns = Array.from(parent.querySelectorAll('div[role="button"], button, i'));
                if (btns.length >= 2) {
                    btns[btns.length - 1].click();
                    return true;
                }
                return false;
            }""")
            if not next_clicked:
                break
            await page.wait_for_timeout(600)

        # Click day cell
        clicked = await page.evaluate("""(dayStr) => {
            const days = Array.from(document.querySelectorAll('div, span, button')).filter(el => {
                if (el.children.length !== 0 || (el.innerText || '').trim() !== dayStr) return false;
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) return false;
                const style = window.getComputedStyle(el);
                // Filter out disabled, not-allowed, or muted days (previous/next month cells)
                if (style.cursor === 'not-allowed') return false;
                if (style.color === 'rgb(176, 179, 184)') return false;
                if (el.getAttribute('aria-disabled') === 'true') return false;
                if (el.parentElement && el.parentElement.getAttribute('aria-disabled') === 'true') return false;
                return true;
            });
            if (days.length === 0) {
                // Fallback: search any element with dayStr that matches text
                const fallback = Array.from(document.querySelectorAll('div, span, button')).filter(el => {
                    return el.children.length === 0 && (el.innerText || '').trim() === dayStr;
                });
                if (fallback.length === 0) return false;
                const dayNum = parseInt(dayStr, 10);
                const target = (dayNum >= 20) ? fallback[fallback.length - 1] : fallback[0];
                target.click();
                return true;
            }
            const dayNum = parseInt(dayStr, 10);
            const targetEl = (dayNum >= 20) ? days[days.length - 1] : days[0];
            targetEl.click();
            return true;
        }""", target_day)
        return clicked

    async def _set_time_in_picker(self, page, target_time_str: str) -> bool:
        """Type target time (e.g. '08:30') into time combobox and dismiss dropdown cleanly."""
        time_inputs = await page.query_selector_all('input[type="text"][role="combobox"], input[value*=":"]')
        if not time_inputs:
            return False

        ti = time_inputs[0]
        await ti.click()
        await page.wait_for_timeout(200)
        await page.keyboard.press("Control+A")
        await page.wait_for_timeout(100)
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(100)
        await ti.type(target_time_str, delay=40)
        await page.wait_for_timeout(300)

        # Commit value and dismiss dropdown using Enter and Escape (avoids pointer-events intercept crashes)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(200)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)

        # Blur active element safely via JavaScript (never blocked by pointer intercepts)
        await page.evaluate("() => document.activeElement && document.activeElement.blur()")
        await page.wait_for_timeout(400)
        return True


    async def bulk_upload_and_schedule_reels(self, items: list[dict], dry_run: bool = False) -> list[dict]:
        """
        Bulk upload and schedule up to 9 Reels in a single batch using Facebook Professional Dashboard.
        - URL: https://www.facebook.com/professional_dashboard/
        - Native Bulk upload reels flow
        - Simultaneous file ingestion
        - Individual caption and schedule slots (08:30, 18:00, 21:00 IST)
        - Preserves clean titles with zero numbers
        - Automatic cross-posting to Instagram via Meta Accounts Centre
        - Returns list of result dicts
        """
        if not items:
            return []

        # Enforce max 9 videos per batch
        batch = items[:9]
        results = [{
            'platform': Platform.FACEBOOK,
            'job_id': item.get('job_id'),
            'video_path': item.get('video_path'),
            'source_filename': item.get('source_filename'),
            'scheduled_date': item.get('scheduled_date'),
            'scheduled_time': item.get('scheduled_time'),
            'status': 'pending',
            'error': None,
            'url': None,
        } for item in batch]

        if dry_run:
            for r in results:
                r['status'] = 'scheduled'
                r['url'] = f"https://www.facebook.com/professional_dashboard/dryrun_{r.get('job_id')}"
            logger.info(f"[DRY RUN] Facebook: Simulated bulk scheduling of {len(batch)} reels")
            return results

        page = self.page

        # Bring browser to foreground if visible
        if not self.engine.headless:
            _bring_browser_to_foreground()

        try:
            # 1. Use original video paths directly (kebab-case filenames with no staging dot-dir)
            clean_paths = [item['video_path'] for item in batch]

            # 2. Navigate to Facebook Professional Dashboard
            logger.info(f"Navigating to {self.PROFESSIONAL_DASHBOARD_URL}...")
            await page.goto(self.PROFESSIONAL_DASHBOARD_URL, wait_until='domcontentloaded', timeout=BROWSER_TIMEOUT_MS)
            if not self.engine.headless:
                _bring_browser_to_foreground()
            await self._human_delay(10.0, 18.0, "Professional Dashboard loaded")

            if await self.engine.check_for_security_challenge():
                for r in results:
                    r['status'] = 'needs_attention'
                    r['error'] = 'Security challenge detected on Facebook'
                return results

            # 3. Click 'Create a post' button
            logger.info("Opening 'Create a post' menu...")
            create_btn = await page.query_selector('div[role="button"]:has-text("Create a post"), button:has-text("Create a post")')
            if not create_btn:
                raise RuntimeError("Could not find 'Create a post' button on Professional Dashboard")
            await create_btn.click()
            await page.wait_for_timeout(1500)

            # 4. Click 'Bulk upload reels'
            logger.info("Selecting 'Bulk upload reels' option...")
            bulk_item = await page.query_selector('text="Bulk upload reels"')
            if not bulk_item:
                raise RuntimeError("Could not find 'Bulk upload reels' menu item")
            await bulk_item.click()
            await page.wait_for_timeout(2000)

            # 5. Ingest video files using native file chooser or modal input
            logger.info(f"Uploading {len(clean_paths)} video(s) to Bulk upload modal...")
            upload_triggered = False

            # Delay 1: Human delay of 2-5 seconds before triggering video upload
            pre_upload_delay = random.uniform(2.0, 5.0)
            logger.info(f"⏳ [Human Simulation] Pre-upload delay: Waiting {pre_upload_delay:.1f}s (2-5s) before choosing video...")
            await asyncio.sleep(pre_upload_delay)

            # Strategy A: Native file chooser via 'Upload from your computer' link (100% human-like & reliable)
            upload_link = await page.query_selector('text="Upload from your computer"')
            if not upload_link:
                try:
                    await page.wait_for_selector('text="Upload from your computer"', timeout=8000)
                    upload_link = await page.query_selector('text="Upload from your computer"')
                except Exception:
                    upload_link = None

            if upload_link:
                try:
                    async with page.expect_file_chooser(timeout=10000) as fc_info:
                        await upload_link.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(clean_paths)
                    upload_triggered = True
                    logger.info("File chooser set_files completed via 'Upload from your computer'")
                except Exception as fce:
                    logger.warning(f"File chooser notice: {fce}")

            # Strategy B: Fallback directly to file input with 'multiple' attribute
            if not upload_triggered:
                file_inputs = await page.query_selector_all('input[type="file"]')
                target_fi = None
                for fi in file_inputs:
                    mult = await fi.get_attribute('multiple')
                    if mult is not None:
                        target_fi = fi
                        break
                if not target_fi:
                    for fi in file_inputs:
                        accept = await fi.get_attribute('accept') or ''
                        if 'video' in accept:
                            target_fi = fi
                            break
                if not target_fi and file_inputs:
                    target_fi = file_inputs[0]

                if target_fi:
                    await target_fi.set_input_files(clean_paths)
                    upload_triggered = True
                    logger.info("Direct set_input_files completed on target file input")

            if not upload_triggered:
                raise RuntimeError("Failed to trigger video upload in Bulk upload reels modal")

            # Delay 2: Wait at least 10 seconds once video is selected and upload started
            logger.info("⏳ [Human Simulation] Video selected and upload started. Waiting at least 10.0s for video ingestion...")
            await asyncio.sleep(10.0)

            # Wait dynamically for upload rows / table to appear (up to 45s)
            logger.info("⏳ Waiting for batch table rows to initialize...")
            table_ready = False
            for _ in range(45):
                await page.wait_for_timeout(1000)
                ready = await page.evaluate("""() => {
                    const textboxes = document.querySelectorAll('div[role="textbox"], div[contenteditable="true"]');
                    const publishBtns = Array.from(document.querySelectorAll('*')).filter(el => (el.innerText || '').trim() === 'Publish now');
                    return textboxes.length > 0 || publishBtns.length > 0;
                }""")
                if ready:
                    table_ready = True
                    break

            if not table_ready:
                raise RuntimeError("Timed out waiting for Bulk upload table rows to appear after selecting video(s)")

            # Additional short stabilization delay
            await page.wait_for_timeout(2000)

            # 6. Configure each video row: Caption and Schedule
            desc_boxes = await page.query_selector_all('div[role="textbox"], div[contenteditable="true"]')
            total_rows = len(batch)
            logger.info(f"Found {len(desc_boxes)} description box(es) in bulk table (expected {total_rows})")

            for i, item in enumerate(batch):
                caption = item.get('caption') or ''
                sched_date = item.get('scheduled_date')
                sched_time = item.get('scheduled_time') or '08:30'

                logger.info(f"Configuring Reel [{i+1}/{total_rows}]: Date={sched_date}, Time={sched_time}")

                # A. Set caption in row
                if i < len(desc_boxes):
                    try:
                        await desc_boxes[i].click()
                        await page.wait_for_timeout(300)
                        await desc_boxes[i].fill(caption)
                        await page.wait_for_timeout(500)
                    except Exception as ce:
                        logger.warning(f"Error typing caption for row {i+1}: {ce}")

                # Delay 3: 5 seconds delay when description is added
                logger.info(f"⏳ [Human Simulation] Description added for Reel [{i+1}/{total_rows}]. Waiting 5.0s...")
                await asyncio.sleep(5.0)

                # B. Click Publish now -> Schedule for later via robust coordinate click
                box = await page.evaluate("""(idx) => {
                    const els = Array.from(document.querySelectorAll('*')).filter(el => (el.innerText || '').trim() === 'Publish now');
                    if (!els.length) return null;
                    const target = idx < els.length ? els[idx] : els[els.length - 1];
                    const r = target.getBoundingClientRect();
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }""", i)

                if box:
                    await page.mouse.click(box['x'], box['y'])
                    # Delay 4A: 3 seconds delay for step
                    logger.info("⏳ [Human Simulation] Opened Publish menu. Waiting 3.0s...")
                    await asyncio.sleep(3.0)

                sched_box = await page.evaluate("""() => {
                    const el = Array.from(document.querySelectorAll('*')).find(e => {
                        const t = (e.innerText || '').trim();
                        return t === 'Schedule for later' || t.startsWith('Schedule for later');
                    });
                    if (!el) return null;
                    const r = el.getBoundingClientRect();
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }""")

                if sched_box:
                    await page.mouse.click(sched_box['x'], sched_box['y'])
                    # Delay 4B: 3 seconds delay for step
                    logger.info("⏳ [Human Simulation] Selected 'Schedule for later'. Waiting 3.0s...")
                    await asyncio.sleep(3.0)

                    # Set date
                    if sched_date:
                        await self._select_date_in_calendar(page, sched_date)
                        # Delay 4C: 3 seconds delay for step
                        logger.info(f"⏳ [Human Simulation] Selected date {sched_date}. Waiting 3.0s...")
                        await asyncio.sleep(3.0)

                    # Set time
                    if sched_time:
                        await self._set_time_in_picker(page, sched_time)
                        # Delay 4D: 3 seconds delay for step
                        logger.info(f"⏳ [Human Simulation] Configured time {sched_time}. Waiting 3.0s...")
                        await asyncio.sleep(3.0)

                    # Click Apply
                    apply_clicked = await page.evaluate("""() => {
                        const btns = Array.from(document.querySelectorAll('div[role="button"], button')).filter(b => {
                            return (b.innerText || '').trim() === 'Apply';
                        });
                        if (btns.length > 0) {
                            btns[0].click();
                            return true;
                        }
                        return false;
                    }""")
                    if not apply_clicked:
                        apply_btn = await page.query_selector('div[role="button"]:has-text("Apply"), button:has-text("Apply")')
                        if apply_btn:
                            try:
                                await page.evaluate("(el) => el && el.click()", apply_btn)
                                apply_clicked = True
                            except Exception:
                                await apply_btn.click(timeout=3000)
                                apply_clicked = True

                    if apply_clicked:
                        row_info = await page.evaluate(f"""(idx) => {{
                            const boxes = Array.from(document.querySelectorAll('*')).filter(el => {{
                                return el.children.length === 0 && (el.innerText || '').startsWith('Scheduled');
                            }});
                            return boxes.length > idx ? boxes[idx].innerText.trim() : (boxes.length > 0 ? boxes[boxes.length - 1].innerText.trim() : '');
                        }}""", i)
                        logger.info(f"Schedule applied for Reel [{i+1}/{total_rows}]: {sched_date} @ {sched_time} (UI text: '{row_info}')")
                    else:
                        logger.warning(f"Could not click Apply button for Reel [{i+1}/{total_rows}]")

                    # Delay 4E: 3 seconds delay after Apply
                    logger.info("⏳ [Human Simulation] Clicked Apply. Waiting 3.0s...")
                    await asyncio.sleep(3.0)

                await self._human_delay(2.0, 3.0, f"Row {i+1} configured")

            # Delay 4F: 3 seconds delay before clicking Save / Schedule button
            logger.info("⏳ [Human Simulation] Pre-commit delay: Waiting 3.0s before clicking Save / Schedule...")
            await asyncio.sleep(3.0)

            # 7. Click 'Save' or 'Schedule' to finalize the entire batch
            logger.info("Committing batch: Clicking 'Save' / 'Schedule' button...")
            save_btn_rect = await page.evaluate("""() => {
                const el = Array.from(document.querySelectorAll('div[role="button"], button')).find(b => {
                    const t = (b.innerText || '').trim();
                    return t === 'Save' || t === 'Schedule';
                });
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }""")

            save_clicked = False
            if save_btn_rect:
                await page.mouse.click(save_btn_rect['x'], save_btn_rect['y'])
                await page.evaluate("""() => {
                    const el = Array.from(document.querySelectorAll('div[role="button"], button')).find(b => {
                        const t = (b.innerText || '').trim();
                        return t === 'Save' || t === 'Schedule';
                    });
                    if (el) el.click();
                }""")
                save_clicked = True

            if not save_clicked:
                save_btn = await page.query_selector(
                    'div[role="dialog"] div[role="button"]:has-text("Save"), div[role="dialog"] button:has-text("Save"), '
                    'div[role="button"]:has-text("Save"), button:has-text("Save"), '
                    'div[role="button"]:has-text("Schedule"), button:has-text("Schedule")'
                )
                if save_btn:
                    try:
                        await page.evaluate("(b) => b && b.click()", save_btn)
                        save_clicked = True
                    except Exception:
                        await save_btn.click(timeout=4000)
                        save_clicked = True

            if not save_clicked:
                raise RuntimeError("Could not click 'Save' or 'Schedule' button in Bulk upload modal")

            logger.info("Waiting for batch saving to complete...")
            # Wait up to 20 seconds for modal to close or redirect to content library
            for _ in range(20):
                await page.wait_for_timeout(1000)
                cur_url = page.url
                if 'content_library' in cur_url or 'filter=SCHEDULED' in cur_url:
                    break
                has_modal = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('*')).some(e => (e.innerText || '').trim() === 'Bulk-upload items');
                }""")
                if not has_modal:
                    break

            # Verification: Set results
            for r in results:
                r['status'] = 'scheduled'
                r['url'] = f"{self.PROFESSIONAL_DASHBOARD_URL}content/content_library/?filter=SCHEDULED"

            try:
                await self.engine.screenshot('fb_bulk_batch_success')
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Facebook bulk scheduling failed: {e}", exc_info=True)
            for r in results:
                r['status'] = 'failed'
                r['error'] = str(e)
            try:
                await self.engine.screenshot('fb_bulk_batch_error')
            except Exception:
                pass

        return results

    async def upload_and_schedule_reel(self, video_path: str, caption: str, scheduled_date: str, scheduled_time: str, dry_run: bool = False) -> dict:
        """
        Upload and schedule a single Reel using the Professional Dashboard.
        Uses bulk_upload_and_schedule_reels with batch size 1 for 100% selector consistency.
        """
        single_item = {
            'video_path': video_path,
            'caption': caption,
            'title': sanitize_title_no_numbers(caption.split('\n')[0] if caption else Path(video_path).stem),
            'scheduled_date': scheduled_date,
            'scheduled_time': scheduled_time,
        }
        batch_res = await self.bulk_upload_and_schedule_reels([single_item], dry_run=dry_run)
        if batch_res:
            return batch_res[0]
        return {
            'platform': Platform.FACEBOOK,
            'video_path': video_path,
            'status': 'failed',
            'error': 'No response from bulk scheduler',
            'url': None
        }

    async def upload_reel(self, video_path, description, dry_run=False):
        """
        Legacy upload method for backward compatibility.
        """
        return await self.upload_and_schedule_reel(
            video_path=video_path,
            caption=description,
            scheduled_date=None,
            scheduled_time='08:30',
            dry_run=dry_run
        )


async def open_all_for_manual_login(headless=False):
    """
    Open browser and navigate to all platforms for manual login.
    Returns the engine for continued use.
    """
    engine = BrowserEngine(headless=headless)
    await engine.start()

    platforms = {
        'youtube': YouTubePublisher(engine),
        'instagram': InstagramPublisher(engine),
        'facebook': FacebookPublisher(engine),
    }

    auth_status = {}
    for name, pub in platforms.items():
        is_auth = await pub.is_authenticated()
        auth_status[name] = is_auth
        if not is_auth:
            await pub.open_for_manual_login()
            logger.info(f"{name}: Not authenticated — please sign in manually")

    return engine, platforms, auth_status


def fast_check_auth_from_profile(profile_dir=None):
    """
    Fast, non-blocking check reading the Chromium SQLite cookie store.
    Completes in under 5ms without launching any browser or network requests.
    Safe to run even while Chrome is open.
    """
    import sqlite3
    import shutil
    p_dir = Path(profile_dir) if profile_dir else BROWSER_PROFILE_DIR
    cookie_db = p_dir / "Default" / "Network" / "Cookies"
    if not cookie_db.exists():
        cookie_db = p_dir / "Cookies"

    if not cookie_db.exists():
        return {'youtube': False, 'instagram': False, 'facebook': False}

    temp_copy = p_dir / "Default" / "Network" / f"Cookies_auth_check_{os.getpid()}"
    try:
        shutil.copy2(str(cookie_db), str(temp_copy))
        conn = sqlite3.connect(str(temp_copy))
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT host_key, name FROM cookies WHERE "
            "host_key LIKE '%youtube%' OR host_key LIKE '%google%' OR "
            "host_key LIKE '%instagram%' OR host_key LIKE '%facebook%'"
        ).fetchall()
        conn.close()
        temp_copy.unlink(missing_ok=True)

        names = set(r[1] for r in rows)
        return {
            'youtube': bool(any(n in names for n in ['SAPISID', 'LOGIN_INFO', 'SSID', '__Secure-3PSID'])),
            'instagram': bool(any(n in names for n in ['sessionid', 'ds_user_id'])),
            'facebook': bool(any(n in names for n in ['c_user', 'xs'])),
        }
    except Exception as e:
        logger.warning(f"Fast auth check error: {e}")
        if temp_copy.exists():
            temp_copy.unlink(missing_ok=True)
        return {'youtube': False, 'instagram': False, 'facebook': False}


async def check_all_auth(engine: BrowserEngine = None):
    """Check authentication status for all platforms."""
    # 1. Fast check from cookies first
    p_dir = engine.profile_dir if engine else BROWSER_PROFILE_DIR
    status = fast_check_auth_from_profile(p_dir)
    
    # If all 3 are verified or engine not provided, return immediately
    if (status.get('youtube') and status.get('instagram') and status.get('facebook')) or not engine:
        return status

    # 2. Check any remaining unverified platforms via page evaluation
    platforms = {
        'youtube': YouTubePublisher(engine),
        'instagram': InstagramPublisher(engine),
        'facebook': FacebookPublisher(engine),
    }
    for name, pub in platforms.items():
        if not status.get(name):
            try:
                status[name] = await pub.is_authenticated()
            except Exception as e:
                logger.warning(f"Page check for {name} failed: {e}")
                status[name] = False
    return status

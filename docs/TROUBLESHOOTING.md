# 🔧 Troubleshooting Guide

Solutions and recovery procedures for common issues encountered when using **Video Scheduling — Creator Studio**.

---

## 🌐 Browser Automation & Authentication

### 1. "Browser profile is locked or Chrome is already running"
**Cause**: A previous Chrome automation instance didn't exit cleanly, or Google Chrome is running in the background holding the lock on `browser_profile/SingletonLock`.

**Solution**:
1. Close all open Google Chrome windows.
2. In Windows Task Manager (or terminal), terminate any orphaned Chrome processes:
   ```powershell
   Stop-Process -Name "chrome" -Force
   ```
3. If the error persists, delete the lock file inside your browser profile:
   ```powershell
   Remove-Item "browser_profile\SingletonLock" -Force -ErrorAction SilentlyContinue
   ```
4. Click **"Check Auth Status"** in the Connections page to verify.

---

### 2. "Account is Logged Out / Session Expired"
**Cause**: Social platforms periodically expire session cookies or request verification.

**Solution**:
1. Navigate to the **Connections** tab in the dashboard.
2. Click **"Open Browser for Login"**.
3. Sign into YouTube Studio, Instagram, or Facebook in the opened browser window.
4. Complete any 2FA security codes or email verification.
5. Once logged in, click **"Check Auth Status"**.

---

### 3. "CAPTCHA or Human Verification Appears"
**Cause**: Social platforms occasionally present a security verification challenge when logging in or uploading in rapid succession.

**Solution**:
- When running publishing jobs, keep the **"👁️ Open Browser Window"** option checked.
- If a CAPTCHA appears, simply solve it manually in the visible browser window. The automation script will detect that the challenge was cleared and automatically continue the workflow.

---

## 🎥 Video Processing & FFmpeg

### 1. "'ffmpeg' is not recognized as an internal or external command"
**Cause**: FFmpeg is either not installed or not present in your system `PATH` environment variable.

**Solution**:
1. Download a pre-built FFmpeg static build from [gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/).
2. Extract to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your system `PATH` environment variable.
4. Restart your terminal / batch launcher and verify with:
   ```powershell
   ffmpeg -version
   ```

---

### 2. "Video Concatenation Audio Mismatch"
**Cause**: Your raw video and the outro clip have differing audio channel layouts (e.g. stereo vs. mono) or sample rates (44.1kHz vs. 48kHz).

**Solution**:
- The video processing engine automatically re-encodes both audio streams using `-c:a aac -b:a 192k` with standardized channel mapping. Ensure both videos have an audio track (even silent audio).

---

## 📊 Excel Metadata & Synchronization

### 1. "PermissionError: [Errno 13] Permission denied: '...video_metadata.xlsx'"
**Cause**: The Excel spreadsheet is currently open in Microsoft Excel, LibreOffice, or another program that has placed an exclusive file lock on it.

**Solution**:
1. Save and **close** the file in Microsoft Excel.
2. Return to the dashboard and retry **"Sync Workbook"**.

---

### 2. "Accidental Overwrite or Bad Edit in Excel"
**Cause**: Manual spreadsheet edits resulted in accidental deletion of rows or corrupted formatting.

**Solution**:
- Before every synchronization write, the engine creates an automatic timestamped backup in:
  `backups/` or `output/excel_backups/`
- Simply copy the most recent timestamped backup file and replace `video_metadata.xlsx`.

---

## 🚦 Queue & Publishing Recovery

### 1. "Resetting Failed Publishing Jobs"
If an upload was interrupted due to internet disconnection or platform maintenance:
1. Go to the **Publishing Queue** page.
2. Click **"🔄 Reset Failed"** in the top action bar.
3. All failed jobs will be safely reset back to `Pending` status without duplicating existing published records.

### 2. "HTTP 409 Conflict: Queue Publishing is Already Running"
**Cause**: You clicked "Start Uploading" while another publishing batch or full pipeline task was actively running.

**Solution**:
- The application prevents two Chrome instances from using the same profile concurrently to avoid profile corruption. Wait for the active batch to finish, or click **"⏹️ Stop Uploading"** to gracefully halt the current job.

# Security Policy

## 🔒 Supported Versions

We actively support and release patches for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| < 2.0   | :x:                |

---

## 🛡️ Privacy & Local Data Architecture

**Video Scheduling — Creator Studio** is engineered from the ground up as a **100% local, self-hosted, desktop/local web application**:

1. **No External Telemetry or Cloud Transmission**:
   - The application does not send telemetry, analytics, user metadata, or video files to any third-party server or cloud API.
   - All processing (FFmpeg rendering, thumbnail extraction, SQLite storage, Excel synchronization) occurs strictly on your local machine.

2. **Localhost Binding**:
   - By default, the FastAPI web dashboard binds strictly to `127.0.0.1:8000`. It is not accessible across your local area network unless you explicitly modify `DASHBOARD_HOST`.

3. **Persistent Browser Session Security**:
   - Authentication sessions with YouTube Studio, Instagram, and Facebook Professional are saved directly into the local `browser_profile/` directory via Playwright's persistent Chrome profile mechanism.
   - Credentials, passwords, and 2FA tokens are handled interactively by you inside the native Chrome browser window. The application never intercepts, stores, logs, or transmits plain-text passwords.
   - The `browser_profile/` directory is strictly excluded from version control via `.gitignore`.

4. **Spreadsheet & Video Privacy**:
   - Video files (`start video/`, `End Video/`, `output/processed_videos/`) and metadata workbooks (`*.xlsx`) are excluded from Git commits.

---

## 🚨 Reporting a Vulnerability

If you discover a security vulnerability or sensitive information leakage:

1. **Do not create a public GitHub issue.**
2. Send an email to the project maintainer: **parthwagh9999@gmail.com** (or open a private security advisory on GitHub).
3. Include:
   - A description of the vulnerability.
   - Steps to reproduce or proof-of-concept.
   - Potential impact.
4. We will acknowledge receipt within 48 hours and work with you to patch and release a fix promptly.

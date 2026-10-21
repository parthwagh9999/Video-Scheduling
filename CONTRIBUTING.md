# Contributing to Video Scheduling

Thank you for your interest in contributing to **Video Scheduling — Creator Studio**!

This project is an open-source, automated video scheduling and publishing application designed for content creators publishing vertical short-form video (YouTube Shorts, Instagram Reels, and Facebook Reels) using browser automation and local metadata synchronization.

---

## 🛠️ Development Setup

### 1. Prerequisites
- **Python 3.10 to 3.13** installed
- **FFmpeg and FFprobe** available in your system `PATH`
- **Google Chrome** installed (used by Playwright automation)
- **Git**

### 2. Clone and Setup Environment
```bash
git clone https://github.com/parthwagh9999/Video-Scheduling.git
cd Video-Scheduling

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser drivers
playwright install chromium
```

### 3. Verify Local Test Suite
```bash
pytest tests/ -v
```

---

## 🧪 Testing Guidelines

1. **Automated Unit & Integration Tests**:
   - Run `pytest` before submitting any PR.
   - All tests in `tests/` must pass without warnings or errors.
2. **Never Run Tests on Live Social Accounts**:
   - Tests must use mock data, temporary SQLite databases (`:memory:` or temporary paths), and simulated streams (`dry_run=True`).
   - Automated tests must never interact with live creator accounts.
3. **Adding New Features**:
   - When introducing new API endpoints, scheduler algorithms, or database models, add corresponding tests in `tests/test_api.py`, `tests/test_scheduler.py`, or `tests/test_database.py`.

---

## 🛡️ Security & Privacy Rules (Strict)

- **NEVER commit**:
  - Personal video files (`*.mp4`, `*.mov`, etc.)
  - Real metadata workbooks (`*.xlsx`) containing private creator content
  - Browser profile directories (`browser_profile/`)
  - Cookies, sessions, tokens, or credentials
  - SQLite database files (`*.db`)
- Always verify your staging status with `git status -s` before committing.

---

## 📐 Coding Standards

- **Python**: Follow PEP 8 guidelines. Use descriptive variable names and type annotations where practical.
- **Frontend**: Vanilla CSS and Vanilla JavaScript (SPA architecture). Maintain clean DOM separation and avoid bulky heavy frameworks unless strictly required.
- **Error Handling**: Gracefully catch and log errors. Never allow background operations or browser disconnections to crash the dashboard server.

---

## 🚀 Pull Request Process

1. Fork the repository and create your branch from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your improvements, ensuring code formatting and regression tests pass.
3. Commit with a clear, concise message:
   ```bash
   git commit -m "feat(scheduler): improve conflict detection for custom time slots"
   ```
4. Push to your fork and submit a Pull Request to `parthwagh9999/Video-Scheduling`.

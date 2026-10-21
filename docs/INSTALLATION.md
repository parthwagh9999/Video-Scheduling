# 📦 Complete Installation & Setup Guide

This guide provides end-to-end instructions for installing and running **Video Scheduling — Creator Studio** on Windows, macOS, and Linux.

---

## 📋 System Requirements

| Component | Minimum | Recommended |
| --------- | ------- | ----------- |
| **Operating System** | Windows 10/11, macOS 12+, Ubuntu 20.04+ | Windows 11 (64-bit) |
| **Python** | Python 3.10 | Python 3.11 or 3.12 |
| **RAM** | 4 GB | 8 GB or more (for FFmpeg video rendering) |
| **Disk Space** | 2 GB free (plus storage for your videos) | SSD with 10+ GB free |
| **Browser** | Google Chrome installed locally | Latest Google Chrome |
| **Media Engine** | FFmpeg 5.0+ with FFprobe | FFmpeg 6.0+ |

---

## 🪟 Windows Setup (Quickstart)

### Step 1: Install Python
1. Download Python 3.11 or 3.12 from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer and **ensure you check the box**:  
   ☑ **"Add Python to PATH"** (Very important!)
3. Click **"Install Now"**.

### Step 2: Install FFmpeg
1. Download a pre-built static build of FFmpeg from [gyan.dev/ffmpeg/builds/](https://www.gyan.dev/ffmpeg/builds/) (choose `ffmpeg-release-essentials.zip`).
2. Extract the folder to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your Windows System `PATH` Environment Variable:
   - Press <kbd>Win</kbd> + <kbd>R</kbd>, type `sysdm.cpl` and hit Enter.
   - Go to **Advanced** tab → Click **Environment Variables**.
   - Under *System variables*, select **Path** and click **Edit**.
   - Click **New** and paste `C:\ffmpeg\bin`.
   - Click **OK** to save.
4. Verify by opening PowerShell and typing:
   ```powershell
   ffmpeg -version
   ```

*(Alternatively, if you use Chocolatey or Scoop: `choco install ffmpeg-full` or `scoop install ffmpeg`)*

### Step 3: Clone & Install Video Scheduling
1. Clone this repository or download it as a ZIP:
   ```powershell
   git clone https://github.com/parthwagh9999/Video-Scheduling.git
   cd Video-Scheduling
   ```
2. Create and activate a Python virtual environment:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install required Python packages:
   ```powershell
   pip install -r requirements.txt
   ```
4. Install Playwright browser drivers:
   ```powershell
   playwright install chromium
   ```

### Step 4: Launch the Application
- **Option A (One-Click Launcher)**: Double-click `start_dashboard.bat` in the root folder.
- **Option B (Terminal)**:
  ```powershell
  python run.py dashboard
  ```
The dashboard will open automatically in your browser at `http://localhost:8000`.

---

## 🍏 macOS Setup

### Step 1: Install Homebrew & Tools
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python and FFmpeg
brew install python@3.11 ffmpeg
```

### Step 2: Clone & Install
```bash
git clone https://github.com/parthwagh9999/Video-Scheduling.git
cd Video-Scheduling

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Step 3: Launch
```bash
python run.py dashboard
```
Open `http://localhost:8000` in Safari or Chrome.

---

## 🐧 Linux (Ubuntu / Debian) Setup

### Step 1: Install System Packages
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv ffmpeg git
```

### Step 2: Clone & Install
```bash
git clone https://github.com/parthwagh9999/Video-Scheduling.git
cd Video-Scheduling

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
playwright install-deps
```

### Step 3: Launch
```bash
python run.py dashboard
```

---

## 🔐 First-Run Account Authentication

Before the application can schedule videos on your social media accounts:
1. Open the dashboard at `http://localhost:8000`.
2. Click **"Connections"** in the sidebar.
3. Click **"Open Browser for Login"**. A Google Chrome window will appear with tabs for YouTube Studio, Instagram, and Facebook.
4. Log into your accounts and complete any 2-step verification prompts.
5. Close the browser window or click **"Check Auth Status"**.
6. Your sessions are now saved safely in your local `browser_profile/` folder and will be automatically reused for all future publishing operations!

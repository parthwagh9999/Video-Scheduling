"""
Excel workbook synchronization module.
- Reads existing metadata from the workbook
- Matches filenames to actual video files
- Registers missing videos with generated SEO metadata
- Creates timestamped backups before modifications
- Updates status, URLs, and timestamps as publishing progresses
- Preserves existing user-approved data
- Idempotent: safe to run multiple times
"""
import shutil
import re
from pathlib import Path
from datetime import datetime
from copy import copy
import logging
import sys

import openpyxl
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import (
    EXCEL_PATH, EXCEL_COLUMNS, EXCEL_SHEET_NAME, BACKUP_DIR, Status,
    START_VIDEO_DIR,
)

logger = logging.getLogger(__name__)

# Column indices (1-based, matching the workbook)
COL_FILENAME = 1
COL_TITLE = 2
COL_DESCRIPTION = 3
COL_WORD_COUNT = 4
COL_STATUS = 5
COL_SCHED_DATE = 6
COL_SCHED_TIME = 7
COL_YOUTUBE_URL = 8
COL_UPLOADED_AT = 9
COL_INSTAGRAM_CAPTION = 10
COL_INSTAGRAM_WORD_COUNT = 11


def create_backup(workbook_path=None):
    """Create a timestamped backup of the workbook. Returns backup path."""
    wb_path = Path(workbook_path) if workbook_path else EXCEL_PATH
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{wb_path.stem}_backup_{timestamp}{wb_path.suffix}"
    backup_path = BACKUP_DIR / backup_name
    shutil.copy2(str(wb_path), str(backup_path))
    logger.info(f"Backup created: {backup_path}")
    return backup_path


def load_workbook_safe(workbook_path=None):
    """Load workbook with error handling for locked files."""
    wb_path = Path(workbook_path) if workbook_path else EXCEL_PATH
    try:
        wb = openpyxl.load_workbook(str(wb_path))
        return wb
    except PermissionError:
        raise PermissionError(
            f"Cannot open {wb_path}. The file may be open in another application. "
            "Please close it and try again."
        )
    except Exception as e:
        raise RuntimeError(f"Failed to open workbook: {e}")


def validate_workbook_structure(wb, sheet_name=None):
    """Validate that the workbook has the expected structure."""
    sheet = sheet_name or EXCEL_SHEET_NAME
    if sheet not in wb.sheetnames:
        return {
            'valid': False,
            'error': f"Sheet '{sheet}' not found. Available: {wb.sheetnames}"
        }

    ws = wb[sheet]
    actual_headers = [ws.cell(row=1, column=c).value for c in range(1, 10)]

    missing = []
    for i, expected in enumerate(EXCEL_COLUMNS):
        actual = actual_headers[i] if i < len(actual_headers) else None
        if actual != expected:
            missing.append(f"Column {i+1}: expected '{expected}', got '{actual}'")

    return {
        'valid': len(missing) == 0,
        'headers': actual_headers,
        'issues': missing,
        'sheet': sheet,
        'max_row': ws.max_row,
        'max_col': ws.max_column,
    }


def read_all_records(workbook_path=None, sheet_name=None):
    """Read all records from the workbook. Returns list of dicts."""
    wb = load_workbook_safe(workbook_path)
    ws = wb[sheet_name or EXCEL_SHEET_NAME]
    records = []

    for row in range(2, ws.max_row + 1):
        filename = ws.cell(row=row, column=COL_FILENAME).value
        if not filename:
            continue
        records.append({
            'row': row,
            'filename': filename,
            'seo_title': ws.cell(row=row, column=COL_TITLE).value,
            'seo_description': ws.cell(row=row, column=COL_DESCRIPTION).value,
            'word_count': ws.cell(row=row, column=COL_WORD_COUNT).value,
            'status': ws.cell(row=row, column=COL_STATUS).value,
            'scheduled_date': ws.cell(row=row, column=COL_SCHED_DATE).value,
            'scheduled_time': ws.cell(row=row, column=COL_SCHED_TIME).value,
            'youtube_url': ws.cell(row=row, column=COL_YOUTUBE_URL).value,
            'uploaded_at': ws.cell(row=row, column=COL_UPLOADED_AT).value,
            'instagram_caption': ws.cell(row=row, column=COL_INSTAGRAM_CAPTION).value,
            'instagram_word_count': ws.cell(row=row, column=COL_INSTAGRAM_WORD_COUNT).value,
        })

    wb.close()
    return records


def find_missing_videos(workbook_path=None, start_dir=None):
    """
    Compare workbook filenames with actual start-video files.
    Returns:
    - matched: files in both
    - missing_from_excel: files on disk but not in workbook
    - missing_from_disk: files in workbook but not on disk
    - duplicates: duplicate filenames in workbook
    """
    records = read_all_records(workbook_path)
    start_d = Path(start_dir) if start_dir else START_VIDEO_DIR

    # Get actual files
    actual_files = set()
    for f in start_d.iterdir():
        if f.is_file() and f.suffix.lower() in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}:
            actual_files.add(f.name)

    excel_filenames = [r['filename'] for r in records]
    excel_set = set(excel_filenames)

    # Check for duplicates
    from collections import Counter
    counts = Counter(excel_filenames)
    duplicates = {k: v for k, v in counts.items() if v > 1}

    matched = actual_files & excel_set
    missing_from_excel = actual_files - excel_set
    missing_from_disk = excel_set - actual_files

    return {
        'matched': sorted(matched),
        'missing_from_excel': sorted(missing_from_excel),
        'missing_from_disk': sorted(missing_from_disk),
        'duplicates': duplicates,
        'total_actual': len(actual_files),
        'total_excel': len(excel_filenames),
    }


def generate_seo_title(filename):
    """Generate a clean SEO title from a video filename with NO NUMBERS."""
    # Remove extension
    stem = Path(filename).stem
    # Remove timestamp suffix (e.g., _20261013192544)
    stem = re.sub(r'_\d{14}$', '', stem)
    # Remove resolution tags (e.g. 1080p, 720p, 4k, 2k, 60fps)
    stem = re.sub(r'\b\d+(?:p|k|fps)\b', '', stem, flags=re.IGNORECASE)
    # Remove any remaining digits
    stem = re.sub(r'\d+', '', stem)
    # Replace underscores and hyphens with spaces
    title = re.sub(r'[\-_]+', ' ', stem)
    # Remove extra spaces and clean edges
    title = re.sub(r'\s+', ' ', title).strip(' -_.,:;')
    # Clean trailing hanging prepositions left behind
    title = re.sub(r'\b(in|for|of|to|at|by|on)\s*$', '', title, flags=re.IGNORECASE).strip(' -_.,:;')
    # Title case
    title = title.title()
    return title or 'Short Video'


def generate_seo_description(title, filename):
    """
    Generate an SEO description with hashtags.
    Uses a template approach relevant to motivational/life-lessons content.
    Each description targets ~500 words.
    """
    topic = title.strip()

    description = f"""In this short but powerful video, we explore the idea behind "{topic}" — a concept that resonates deeply with anyone striving for personal growth and self-improvement. Life often presents us with challenges that test our resolve, and understanding this principle can transform how we approach everyday decisions.

The journey of self-improvement begins with awareness. When we truly understand the forces that shape our behavior, we gain the power to redirect our energy toward meaningful goals. This video breaks down a key insight that many successful people have embraced throughout history.

Consider how this idea applies to your daily life. Whether you are building a career, nurturing relationships, or simply trying to become a better version of yourself, the message in this video offers practical wisdom you can apply immediately. It is not about grand gestures or dramatic changes — it is about the small, consistent choices that compound over time.

One of the most profound aspects of this lesson is its universality. Regardless of your background, age, or current circumstances, the principle discussed here remains relevant. It speaks to the fundamental human desire to grow, to learn, and to leave a positive impact on the world around us.

We often hear advice that sounds good in theory but fails in practice. What makes this particular insight different is its grounding in real-world observation. It comes from watching how people navigate complex situations and emerge stronger. The key takeaway is not just intellectual understanding but practical application.

Think about the last time you faced a difficult decision. Did you act from a place of clarity, or were you driven by impulse? This video encourages you to pause, reflect, and choose your response intentionally. That single shift in approach can dramatically improve your outcomes across every area of life.

Personal development is not a destination — it is a continuous journey. Each day offers new opportunities to practice the principles that lead to lasting success. By watching videos like this one and reflecting on their messages, you are already taking an important step forward.

Remember, growth happens outside your comfort zone. The ideas shared in this video might challenge some of your existing beliefs, and that is perfectly fine. True wisdom comes from being open to new perspectives while staying grounded in your core values.

We encourage you to share this video with someone who might benefit from hearing this message. Sometimes, a single insight delivered at the right moment can change the trajectory of someone's entire life. Let us build a community of thoughtful, motivated individuals who support each other's growth.

Thank you for watching. If this video resonated with you, consider exploring more content on this channel. Every video is designed to offer genuine value and practical wisdom that you can use to improve your life starting today.

#motivation #selfimprovement #lifelessons #mindset #personalgrowth"""

    return description


def count_description_words(description_text):
    """
    Count words in the description, excluding hashtags.
    Consistent documented method: split on whitespace, exclude tokens starting with #.
    """
    if not description_text:
        return 0
    words = description_text.split()
    # Exclude hashtag tokens
    non_hashtag_words = [w for w in words if not w.startswith('#')]
    return len(non_hashtag_words)


def preview_new_records(workbook_path=None, start_dir=None):
    """
    Generate preview of records that would be added to Excel.
    Does NOT modify the workbook.
    Returns list of new record dicts.
    """
    comparison = find_missing_videos(workbook_path, start_dir)
    new_records = []

    for fname in comparison['missing_from_excel']:
        title = generate_seo_title(fname)
        desc = generate_seo_description(title, fname)
        wc = count_description_words(desc)
        new_records.append({
            'filename': fname,
            'seo_title': title,
            'seo_description': desc,
            'word_count': wc,
            'status': Status.PENDING,
            'scheduled_date': None,
            'scheduled_time': None,
            'youtube_url': None,
            'uploaded_at': None,
            'auto_generated': True,
        })

    return new_records, comparison


def sync_workbook(workbook_path=None, start_dir=None, dry_run=False):
    """
    Synchronize the workbook with actual start-video files.
    - Creates a backup first
    - Adds missing records
    - Does NOT overwrite existing approved metadata
    - Returns sync report

    Set dry_run=True to preview changes without modifying the workbook.
    """
    wb_path = Path(workbook_path) if workbook_path else EXCEL_PATH
    new_records, comparison = preview_new_records(workbook_path, start_dir)

    report = {
        'workbook_path': str(wb_path),
        'sheet_name': EXCEL_SHEET_NAME,
        'rows_before': comparison['total_excel'],
        'files_on_disk': comparison['total_actual'],
        'matched': len(comparison['matched']),
        'missing_from_excel': len(comparison['missing_from_excel']),
        'missing_from_disk': len(comparison['missing_from_disk']),
        'duplicates': comparison['duplicates'],
        'new_records_preview': new_records,
        'rows_added': 0,
        'rows_updated': 0,
        'rows_unchanged': len(comparison['matched']),
        'backup_path': None,
        'dry_run': dry_run,
    }

    if dry_run or not new_records:
        return report

    # Create backup before modification
    backup_path = create_backup(wb_path)
    report['backup_path'] = str(backup_path)

    wb = load_workbook_safe(wb_path)
    ws = wb[EXCEL_SHEET_NAME]

    # Find the next available row
    next_row = ws.max_row + 1

    for rec in new_records:
        ws.cell(row=next_row, column=COL_FILENAME, value=rec['filename'])
        ws.cell(row=next_row, column=COL_TITLE, value=rec['seo_title'])
        ws.cell(row=next_row, column=COL_DESCRIPTION, value=rec['seo_description'])
        ws.cell(row=next_row, column=COL_WORD_COUNT, value=rec['word_count'])
        ws.cell(row=next_row, column=COL_STATUS, value=rec['status'])
        next_row += 1
        report['rows_added'] += 1

    wb.save(str(wb_path))
    wb.close()

    # Verify saved workbook can be reopened
    try:
        verify_wb = openpyxl.load_workbook(str(wb_path))
        verify_ws = verify_wb[EXCEL_SHEET_NAME]
        report['rows_after'] = verify_ws.max_row - 1  # minus header
        verify_wb.close()
    except Exception as e:
        report['verification_error'] = str(e)

    return report


def update_record_status(workbook_path=None, filename=None, row_number=None,
                          status=None, scheduled_date=None, scheduled_time=None,
                          youtube_url=None, uploaded_at=None):
    """
    Update specific fields for a single record.
    Only updates non-None parameters.
    """
    wb_path = Path(workbook_path) if workbook_path else EXCEL_PATH
    wb = load_workbook_safe(wb_path)
    ws = wb[EXCEL_SHEET_NAME]

    target_row = row_number
    if not target_row and filename:
        # Find row by filename
        for r in range(2, ws.max_row + 1):
            if ws.cell(row=r, column=COL_FILENAME).value == filename:
                target_row = r
                break

    if not target_row:
        wb.close()
        raise ValueError(f"Record not found: {filename}")

    if status is not None:
        ws.cell(row=target_row, column=COL_STATUS, value=status)
    if scheduled_date is not None:
        ws.cell(row=target_row, column=COL_SCHED_DATE, value=scheduled_date)
    if scheduled_time is not None:
        ws.cell(row=target_row, column=COL_SCHED_TIME, value=scheduled_time)
    if youtube_url is not None:
        ws.cell(row=target_row, column=COL_YOUTUBE_URL, value=youtube_url)
    if uploaded_at is not None:
        ws.cell(row=target_row, column=COL_UPLOADED_AT, value=uploaded_at)

    wb.save(str(wb_path))
    wb.close()
    logger.info(f"Updated row {target_row} ({filename}): status={status}")


def get_sync_summary(workbook_path=None, start_dir=None):
    """Get a summary of the current sync state without modifying anything."""
    comparison = find_missing_videos(workbook_path, start_dir)
    records = read_all_records(workbook_path)

    status_counts = {}
    for r in records:
        s = r['status'] or 'None'
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        'workbook_path': str(workbook_path or EXCEL_PATH),
        'sheet_name': EXCEL_SHEET_NAME,
        'total_excel_rows': len(records),
        'total_files': comparison['total_actual'],
        'matched': len(comparison['matched']),
        'missing_from_excel': comparison['missing_from_excel'],
        'missing_from_disk': comparison['missing_from_disk'],
        'duplicates': comparison['duplicates'],
        'status_distribution': status_counts,
    }

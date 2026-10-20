"""
Video discovery, processing (concatenation with outro), and thumbnail extraction.
Uses FFmpeg/FFprobe for all media operations.
Never modifies original files.
"""
import subprocess
import json
import os
import re
import shutil
from pathlib import Path
from datetime import datetime
import sys
import logging

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from config.settings import (
    START_VIDEO_DIR, END_VIDEO_DIR, PROCESSED_DIR, THUMBNAIL_DIR,
    FFMPEG_PATH, FFPROBE_PATH, THUMBNAIL_EXTRACT_TIME, THUMBNAIL_QUALITY,
    OUTRO_RULE, OUTRO_START_INDEX,
)

logger = logging.getLogger(__name__)


def natural_sort_key(s):
    """Case-insensitive natural sort key for stable ordering."""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r'(\d+)', str(s))
    ]


def discover_start_videos(start_dir=None):
    """Discover all video files in the start-video folder, naturally sorted."""
    d = Path(start_dir) if start_dir else START_VIDEO_DIR
    if not d.exists():
        raise FileNotFoundError(f"Start video directory not found: {d}")
    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    files = [
        f for f in d.iterdir()
        if f.is_file() and f.suffix.lower() in video_exts
    ]
    files.sort(key=lambda f: natural_sort_key(f.name))
    return files


def discover_end_video(end_dir=None):
    """Find the single end video in the end-video folder."""
    d = Path(end_dir) if end_dir else END_VIDEO_DIR
    if not d.exists():
        raise FileNotFoundError(f"End video directory not found: {d}")
    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}
    videos = [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in video_exts]
    if len(videos) == 0:
        raise FileNotFoundError("No video found in end-video folder")
    if len(videos) > 1:
        logger.warning(f"Multiple files in end-video folder, using first: {videos[0].name}")
    return videos[0]


def probe_video(filepath):
    """Get video/audio stream properties using ffprobe. Returns a dict."""
    filepath = str(filepath)
    cmd = [
        FFPROBE_PATH, '-v', 'error',
        '-show_entries', 'stream=codec_type,codec_name,width,height,r_frame_rate,pix_fmt,sample_rate,channels,duration',
        '-show_entries', 'format=duration,size,filename',
        '-of', 'json', filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {filepath}: {result.stderr}")
    data = json.loads(result.stdout)

    info = {
        'filepath': filepath,
        'filename': Path(filepath).name,
        'file_size_bytes': int(data.get('format', {}).get('size', 0)),
        'duration_seconds': float(data.get('format', {}).get('duration', 0)),
    }

    for stream in data.get('streams', []):
        if stream.get('codec_type') == 'video':
            info['width'] = stream.get('width')
            info['height'] = stream.get('height')
            info['codec'] = stream.get('codec_name')
            info['fps'] = stream.get('r_frame_rate')
            info['pixel_format'] = stream.get('pix_fmt')
            if 'duration' in stream:
                info['video_duration'] = float(stream['duration'])
        elif stream.get('codec_type') == 'audio':
            info['audio_codec'] = stream.get('codec_name')
            info['audio_sample_rate'] = int(stream.get('sample_rate', 0))
            info['audio_channels'] = stream.get('channels')

    return info


def check_compatibility(start_info, end_info):
    """Check if start and end videos are compatible for stream-copy concat."""
    issues = []
    checks = [
        ('width', 'Width mismatch'),
        ('height', 'Height mismatch'),
        ('codec', 'Video codec mismatch'),
        ('fps', 'Frame rate mismatch'),
        ('pixel_format', 'Pixel format mismatch'),
        ('audio_codec', 'Audio codec mismatch'),
        ('audio_sample_rate', 'Audio sample rate mismatch'),
        ('audio_channels', 'Audio channel count mismatch'),
    ]
    for key, msg in checks:
        v1 = start_info.get(key)
        v2 = end_info.get(key)
        if v1 is not None and v2 is not None and v1 != v2:
            issues.append(f"{msg}: start={v1}, end={v2}")
    return issues


def compute_outro_assignments(filenames, rule="every_second", start_index=0, manual_selection=None):
    """
    Determine which videos get the outro appended.
    Returns list of (filename, gets_outro, position).
    """
    result = []
    for i, fname in enumerate(filenames):
        if rule == "every":
            gets_outro = True
        elif rule == "none":
            gets_outro = False
        elif rule == "manual":
            gets_outro = fname in (manual_selection or set())
        elif rule == "every_second":
            # Start with start_index, then every other
            gets_outro = (i % 2 == start_index % 2)
        else:
            gets_outro = False
        result.append((fname, gets_outro, i))
    return result


def concatenate_videos(start_path, end_path, output_path):
    """
    Concatenate start + end video using ffmpeg concat demuxer (stream copy).
    Always builds from original source files, never from a previous output.
    Returns True on success.
    """
    start_path = Path(start_path)
    end_path = Path(end_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Create concat file list
    concat_file = output_path.parent / f"_concat_{output_path.stem}.txt"
    try:
        with open(concat_file, 'w', encoding='utf-8') as f:
            f.write(f"file '{str(start_path).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")
            f.write(f"file '{str(end_path).replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}'\n")

        cmd = [
            FFMPEG_PATH, '-y', '-f', 'concat', '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',
            '-movflags', '+faststart',
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr}")
        return True
    finally:
        if concat_file.exists():
            concat_file.unlink()


def validate_output(output_path, expected_start_duration, expected_end_duration, tolerance=0.5):
    """Validate concatenated output: duration, streams, no corruption."""
    info = probe_video(output_path)
    issues = []

    expected_total = expected_start_duration + expected_end_duration
    actual = info['duration_seconds']
    if abs(actual - expected_total) > tolerance:
        issues.append(f"Duration mismatch: expected ~{expected_total:.1f}s, got {actual:.1f}s")

    if not info.get('codec'):
        issues.append("No video stream found in output")
    if not info.get('audio_codec'):
        issues.append("No audio stream found in output")
    if info.get('width', 0) == 0 or info.get('height', 0) == 0:
        issues.append("Invalid resolution in output")

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'output_info': info,
    }


def generate_output_filename(source_filename, suffix="_processed"):
    """Generate output filename preserving relationship to source."""
    stem = Path(source_filename).stem
    ext = Path(source_filename).suffix
    return f"{stem}{suffix}{ext}"


def extract_thumbnail(video_path, output_path, extract_time=None):
    """
    Extract a high-quality JPEG thumbnail from the original start video.
    Uses the exact opening first frame (default 0.0s).
    """
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    t = extract_time if extract_time is not None else THUMBNAIL_EXTRACT_TIME

    cmd = [
        FFMPEG_PATH, '-y',
        '-ss', str(t),
        '-i', str(video_path),
        '-frames:v', '1',
        '-q:v', str(THUMBNAIL_QUALITY),
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        raise RuntimeError(f"Thumbnail extraction failed: {result.stderr}")
    return output_path.exists()


def validate_thumbnail(thumbnail_path):
    """Check thumbnail is not blank/black and has expected properties."""
    thumb = Path(thumbnail_path)
    if not thumb.exists():
        return {'valid': False, 'issue': 'File does not exist'}

    size = thumb.stat().st_size
    if size < 1000:  # Less than 1KB likely blank
        return {'valid': False, 'issue': f'File too small ({size} bytes), likely blank'}

    # Probe the image
    cmd = [
        FFPROBE_PATH, '-v', 'error',
        '-show_entries', 'stream=width,height,codec_name',
        '-of', 'json', str(thumb)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if result.returncode != 0:
        return {'valid': False, 'issue': f'Cannot probe thumbnail: {result.stderr}'}

    data = json.loads(result.stdout)
    streams = data.get('streams', [])
    if not streams:
        return {'valid': False, 'issue': 'No image stream found'}

    s = streams[0]
    w = s.get('width', 0)
    h = s.get('height', 0)

    # Check for black frames using ffmpeg
    cmd_black = [
        FFMPEG_PATH, '-i', str(thumb),
        '-vf', 'blackdetect=d=0:pix_th=0.10',
        '-an', '-f', 'null', '-'
    ]
    result_black = subprocess.run(cmd_black, capture_output=True, text=True, encoding='utf-8')
    is_black = 'black_start' in result_black.stderr

    return {
        'valid': not is_black and w > 0 and h > 0,
        'width': w,
        'height': h,
        'file_size_bytes': size,
        'is_blank': is_black,
        'issue': 'Frame is entirely black' if is_black else None,
    }


def scan_and_sync_thumbnails(start_dir=None, thumb_dir=None, auto_extract_missing=True, force_reextract=False):
    """
    Scan thumbnail directory and start videos, validate all frames,
    extract any missing (or force re-extract) thumbnails from original start video opening first frame (0.0s),
    and synchronize thumbnail metadata with the SQLite database.
    """
    from app.database.models import get_connection, upsert_thumbnail
    start_d = Path(start_dir) if start_dir else START_VIDEO_DIR
    th_d = Path(thumb_dir) if thumb_dir else THUMBNAIL_DIR
    th_d.mkdir(parents=True, exist_ok=True)

    start_files = discover_start_videos(start_d)
    conn = get_connection()

    results = {
        'total_videos': len(start_files),
        'existing_valid': 0,
        'extracted': 0,
        'failed': 0,
        'thumbnails': [],
        'errors': []
    }

    for sf in start_files:
        sv = conn.execute("SELECT id FROM source_videos WHERE filename=?", (sf.name,)).fetchone()
        sv_id = sv['id'] if sv else None

        thumb_fname = f"{sf.stem}_thumb.jpg"
        thumb_path = th_d / thumb_fname
        valid = False
        width, height, file_size = 0, 0, 0
        is_blank = False

        if not force_reextract and thumb_path.exists() and thumb_path.stat().st_size > 1000:
            tv = validate_thumbnail(thumb_path)
            if tv['valid']:
                valid = True
                width = tv.get('width', 0)
                height = tv.get('height', 0)
                file_size = tv.get('file_size_bytes', 0)
                results['existing_valid'] += 1

        if (not valid or force_reextract) and auto_extract_missing:
            try:
                extract_thumbnail(sf, thumb_path)
                tv = validate_thumbnail(thumb_path)
                valid = tv['valid']
                width = tv.get('width', 0)
                height = tv.get('height', 0)
                file_size = tv.get('file_size_bytes', 0)
                is_blank = tv.get('is_blank', False)
                if valid:
                    results['extracted'] += 1
                else:
                    results['failed'] += 1
                    results['errors'].append(f"{sf.name}: extracted thumbnail invalid ({tv.get('issue')})")
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(f"{sf.name}: extraction failed ({e})")

        if sv_id and thumb_path.exists():
            upsert_thumbnail(conn, {
                'source_video_id': sv_id,
                'source_filename': sf.name,
                'thumbnail_path': str(thumb_path),
                'extract_time_seconds': THUMBNAIL_EXTRACT_TIME,
                'width': width,
                'height': height,
                'file_size_bytes': file_size,
                'is_valid': 1 if valid else 0,
                'is_blank': 1 if is_blank else 0,
                'upload_status': 'pending',
                'fallback_used': None,
                'manual_intervention': 0,
                'notes': None,
            })

        results['thumbnails'].append({
            'filename': sf.name,
            'thumbnail': thumb_fname,
            'valid': valid,
            'width': width,
            'height': height,
            'size': file_size
        })

    conn.commit()
    conn.close()
    return results


def process_all_videos(start_dir=None, end_dir=None, output_dir=None, thumb_dir=None,
                        outro_rule=None, start_index=None, manual_selection=None,
                        dry_run=False, progress_callback=None):
    """
    Main video processing pipeline:
    1. Discover start videos (sorted)
    2. Discover end video
    3. Compute outro assignments
    4. Concatenate where needed
    5. Extract thumbnails from ORIGINAL start videos
    6. Validate outputs

    Returns a manifest list.
    """
    start_d = Path(start_dir) if start_dir else START_VIDEO_DIR
    end_d = Path(end_dir) if end_dir else END_VIDEO_DIR
    out_d = Path(output_dir) if output_dir else PROCESSED_DIR
    th_d = Path(thumb_dir) if thumb_dir else THUMBNAIL_DIR
    rule = outro_rule or OUTRO_RULE
    si = start_index if start_index is not None else OUTRO_START_INDEX

    out_d.mkdir(parents=True, exist_ok=True)
    th_d.mkdir(parents=True, exist_ok=True)

    start_files = discover_start_videos(start_d)
    end_file = discover_end_video(end_d)
    end_info = probe_video(end_file)

    filenames = [f.name for f in start_files]
    assignments = compute_outro_assignments(filenames, rule, si, manual_selection)

    manifest = []
    total = len(assignments)

    for idx, (fname, gets_outro, position) in enumerate(assignments):
        start_path = start_d / fname
        start_info = probe_video(start_path)

        entry = {
            'source_filename': fname,
            'source_filepath': str(start_path),
            'end_video_filename': end_file.name if gets_outro else None,
            'outro_appended': gets_outro,
            'sequence_position': position,
            'processing_errors': None,
        }

        # Determine output
        if gets_outro:
            out_fname = generate_output_filename(fname, "_with_outro")
            out_path = out_d / out_fname

            if dry_run:
                entry['output_filename'] = out_fname
                entry['output_filepath'] = str(out_path)
                entry['output_duration'] = start_info['duration_seconds'] + end_info['duration_seconds']
                entry['output_resolution'] = f"{start_info['width']}x{start_info['height']}"
                entry['validation_result'] = 'dry_run'
                entry['processing_params'] = 'stream_copy_concat'
            else:
                try:
                    already_processed = False
                    if out_path.exists() and out_path.stat().st_size > 1000:
                        try:
                            val = validate_output(out_path, start_info['duration_seconds'],
                                                 end_info['duration_seconds'])
                            if val['valid']:
                                already_processed = True
                                logger.info(f"Reusing existing processed video: {out_fname}")
                                entry['output_filename'] = out_fname
                                entry['output_filepath'] = str(out_path)
                                entry['output_duration'] = val['output_info']['duration_seconds']
                                entry['output_resolution'] = f"{val['output_info']['width']}x{val['output_info']['height']}"
                                entry['validation_result'] = 'passed'
                                entry['processing_params'] = 'reused_existing'
                        except Exception:
                            already_processed = False

                    if not already_processed:
                        # Check compatibility first
                        compat_issues = check_compatibility(start_info, end_info)
                        if compat_issues:
                            logger.warning(f"Compatibility issues for {fname}: {compat_issues}")
                            entry['processing_params'] = f'issues: {compat_issues}'

                        concatenate_videos(start_path, end_file, out_path)
                        val = validate_output(out_path, start_info['duration_seconds'],
                                             end_info['duration_seconds'])
                        entry['output_filename'] = out_fname
                        entry['output_filepath'] = str(out_path)
                        entry['output_duration'] = val['output_info']['duration_seconds']
                        entry['output_resolution'] = f"{val['output_info']['width']}x{val['output_info']['height']}"
                        entry['validation_result'] = 'passed' if val['valid'] else f"failed: {val['issues']}"
                        entry['processing_params'] = 'stream_copy_concat'
                except Exception as e:
                    logger.error(f"Processing failed for {fname}: {e}")
                    entry['processing_errors'] = str(e)
                    entry['validation_result'] = 'error'
                    entry['output_filename'] = out_fname
                    entry['output_filepath'] = str(out_path)
        else:
            # No outro — use original start video as publishing source
            entry['output_filename'] = fname
            entry['output_filepath'] = str(start_path)
            entry['output_duration'] = start_info['duration_seconds']
            entry['output_resolution'] = f"{start_info['width']}x{start_info['height']}"
            entry['validation_result'] = 'original_source'
            entry['processing_params'] = 'no_outro'

        # Extract thumbnail from ORIGINAL start video (never from processed/end)
        thumb_fname = Path(fname).stem + "_thumb.jpg"
        thumb_path = th_d / thumb_fname
        if dry_run:
            entry['thumbnail_path'] = str(thumb_path)
            entry['thumbnail_valid'] = 'dry_run'
        else:
            try:
                already_has_thumb = False
                if thumb_path.exists() and thumb_path.stat().st_size > 1000:
                    tv = validate_thumbnail(thumb_path)
                    if tv['valid']:
                        already_has_thumb = True
                        logger.info(f"Reusing existing thumbnail: {thumb_fname}")
                        entry['thumbnail_path'] = str(thumb_path)
                        entry['thumbnail_valid'] = True
                        entry['thumbnail_width'] = tv.get('width')
                        entry['thumbnail_height'] = tv.get('height')
                        entry['thumbnail_size'] = tv.get('file_size_bytes')
                        entry['thumbnail_is_blank'] = False

                if not already_has_thumb:
                    extract_thumbnail(start_path, thumb_path)
                    tv = validate_thumbnail(thumb_path)
                    entry['thumbnail_path'] = str(thumb_path)
                    entry['thumbnail_valid'] = tv['valid']
                    entry['thumbnail_width'] = tv.get('width')
                    entry['thumbnail_height'] = tv.get('height')
                    entry['thumbnail_size'] = tv.get('file_size_bytes')
                    entry['thumbnail_is_blank'] = tv.get('is_blank', False)
            except Exception as e:
                logger.error(f"Thumbnail extraction failed for {fname}: {e}")
                entry['thumbnail_path'] = str(thumb_path)
                entry['thumbnail_valid'] = False
                entry['processing_errors'] = (entry.get('processing_errors') or '') + f"; thumbnail: {e}"

        entry['processing_timestamp'] = datetime.now().isoformat()
        manifest.append(entry)

        if progress_callback:
            progress_callback(idx + 1, total, fname)

    return manifest

"""
Frame extraction for AI Video Analysis (Phase 4).

Deliberately simple: probe the clip's duration with ffprobe, then pull N
evenly-spaced still frames with ffmpeg. This is genuinely what's feasible
with an LLM's vision input (a handful of stills) — it is NOT the same as
real computer-vision tracking (player/ball tracking, pose estimation,
homography-mapped heat maps, expected goals). Those need a dedicated CV
pipeline and are out of scope here; see README for why that's a separate
project rather than something bolted onto a Telegram bot.

Requires the `ffmpeg` and `ffprobe` binaries on PATH (apt install ffmpeg /
brew install ffmpeg) — not a pip package, so it won't show up in
requirements.txt.
"""
import os
import subprocess
import uuid

import config


class VideoProcessingError(Exception):
    pass


def get_duration_seconds(video_path: str) -> float:
    try:
        result = subprocess.run(
            [config.FFPROBE_PATH, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise VideoProcessingError(f"ffprobe failed: {result.stderr.strip()[:300]}")
        return float(result.stdout.strip())
    except FileNotFoundError:
        raise VideoProcessingError(
            "ffprobe isn't installed or isn't on PATH. Install ffmpeg (which includes ffprobe)."
        )
    except subprocess.TimeoutExpired:
        raise VideoProcessingError("Timed out reading the video file.")


def extract_frames(video_path: str, frame_count: int = None) -> list[str]:
    """Extract evenly-spaced JPEG frames from a video. Returns a list of
    absolute file paths to the extracted frames (caller is responsible for
    cleanup — see cleanup_dir below)."""
    frame_count = frame_count or config.VIDEO_FRAME_COUNT
    duration = get_duration_seconds(video_path)
    if duration <= 0:
        raise VideoProcessingError("Couldn't determine the video's duration.")

    out_dir = os.path.join(config.VIDEO_TEMP_DIR, uuid.uuid4().hex)
    os.makedirs(out_dir, exist_ok=True)

    frame_paths = []
    try:
        for i in range(frame_count):
            # Spread timestamps across the middle of the clip, avoiding the
            # very first/last instants which are often black frames or blur.
            timestamp = duration * (i + 0.5) / frame_count
            out_path = os.path.join(out_dir, f"frame_{i:02d}.jpg")
            result = subprocess.run(
                [config.FFMPEG_PATH, "-y", "-ss", f"{timestamp:.2f}", "-i", video_path,
                 "-frames:v", "1", "-q:v", "3", out_path],
                capture_output=True, timeout=30,
            )
            if result.returncode != 0 or not os.path.exists(out_path):
                continue  # skip a failed frame rather than aborting the whole analysis
            frame_paths.append(out_path)
    except FileNotFoundError:
        raise VideoProcessingError(
            "ffmpeg isn't installed or isn't on PATH. Install it with e.g. `apt install ffmpeg`."
        )
    except subprocess.TimeoutExpired:
        raise VideoProcessingError("Timed out extracting frames from the video.")

    if not frame_paths:
        raise VideoProcessingError("Couldn't extract any frames from that video.")

    return frame_paths


def cleanup_dir(any_frame_path: str) -> None:
    """Remove the temp directory a frame was extracted into."""
    out_dir = os.path.dirname(any_frame_path)
    try:
        for f in os.listdir(out_dir):
            os.remove(os.path.join(out_dir, f))
        os.rmdir(out_dir)
    except OSError:
        pass  # best-effort cleanup; a stray temp dir isn't worth crashing over

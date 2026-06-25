"""Audio extraction / normalization via ffmpeg."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import config


def find_ffmpeg() -> str:
    """Locate an ffmpeg binary: system PATH first, then imageio-ffmpeg as a fallback."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # optional fallback

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "ffmpeg not found. Install it (e.g. `sudo apt install ffmpeg`) "
            "or `pip install imageio-ffmpeg`."
        ) from e


def find_ffprobe() -> str | None:
    """Locate ffprobe (system PATH, or alongside ffmpeg). None if unavailable."""
    exe = shutil.which("ffprobe")
    if exe:
        return exe
    ff = shutil.which("ffmpeg")
    if ff:
        cand = Path(ff).with_name("ffprobe")
        if cand.exists():
            return str(cand)
    return None


def probe_duration(path: Path) -> float | None:
    """Media duration in seconds via ffprobe, or None if it can't be determined."""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except (ValueError, AttributeError):
        return None


def split_audio(path: Path, chunk_seconds: int, out_dir: Path) -> list[Path]:
    """Split an audio file into <= chunk_seconds segments; return them in order.

    Long lessons are chunked before transcription: a single 40-min upload both risks the
    output-token ceiling and pushes the model into repetition loops. Segments are cut on
    frame boundaries (`-c copy`), so a word may straddle a seam — negligible for the
    compression that Stage 2 does next.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "chunk_%03d.mp3")
    cmd = [find_ffmpeg(), "-y", "-i", str(path), "-f", "segment",
           "-segment_time", str(chunk_seconds), "-c", "copy", pattern]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg segment failed for {path.name}:\n{proc.stderr[-2000:]}")
    return sorted(out_dir.glob("chunk_*.mp3"))


def normalize_to_audio(input_path: Path, out_path: Path) -> Path:
    """Extract/normalize any media file to a small mono MP3 suitable for upload.

    Handles both video (drops the video stream) and audio inputs uniformly.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        find_ffmpeg(),
        "-y",
        "-i", str(input_path),
        "-vn",                                # drop any video stream
        "-ac", "1",                           # mono
        "-ar", str(config.AUDIO_SAMPLE_RATE),  # 16 kHz (Gemini downsamples anyway)
        "-c:a", "libmp3lame",
        "-b:a", config.AUDIO_BITRATE,
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed for {input_path.name}:\n{proc.stderr[-2000:]}")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg produced no audio for {input_path.name}")
    return out_path

import os
import re
import contextlib
import shutil
from typing import List, Tuple, Optional

MAGICK_EXE = r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"
if os.path.isfile(MAGICK_EXE):
    os.environ["IMAGEMAGICK_BINARY"] = MAGICK_EXE
elif shutil.which("magick"):
    os.environ["IMAGEMAGICK_BINARY"] = "magick"
else:
    raise RuntimeError(
        "ImageMagick not found. Install it or set IMAGEMAGICK_BINARY to magick.exe full path."
    )

from moviepy.config import change_settings
change_settings({"IMAGEMAGICK_BINARY": os.environ["IMAGEMAGICK_BINARY"]})

from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip


def _parse_timestamp(ts: str) -> float:
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

def parse_srt(path: str) -> List[Tuple[float, float, str]]:
    """Parse a minimal SRT file into a list of (start_sec, end_sec, text)."""
    entries: List[Tuple[float, float, str]] = []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r"\n\s*\n", content.strip())
    for b in blocks:
        lines = [ln.strip("\ufeff") for ln in b.splitlines() if ln.strip()]
        if len(lines) < 2:
            continue
        # lines[0] may be index, ignore
        times = lines[1]
        m = re.match(r"(\d\d:\d\d:\d\d,\d\d\d)\s*--?>\s*(\d\d:\d\d:\d\d,\d\d\d)", times)
        if not m:
            continue
        start = _parse_timestamp(m.group(1))
        end = _parse_timestamp(m.group(2))
        text = "\n".join(lines[2:])
        entries.append((start, end, text))
    return entries

def _clamp_items_to_duration(items: List[Tuple[float, float, str]], max_duration: float) -> List[Tuple[float, float, str]]:
    """Ensure subtitle intervals fit within [0, max_duration]."""
    clamped: List[Tuple[float, float, str]] = []
    eps = 1e-3
    for start, end, text in items:
        s = max(0.0, min(start, max_duration - eps))
        e = max(0.0, min(end, max_duration - eps))
        if e <= s:
            e = min(s + 0.1, max_duration - eps)  # minimal visible duration
        clamped.append((s, e, text))
    return clamped

def burn_subtitles_from_items(
    video_path: str,
    items: List[Tuple[float, float, str]],
    output_path: str,
    font: Optional[str] = None,
    fontsize: Optional[int] = None,
    color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 2,
    margin_bottom: int = 40,
) -> str:
    """Burn subtitles described by items=(start,end,text) onto video using ImageMagick-backed TextClip."""
    v = VideoFileClip(video_path)
    subs = []
    try:
        W, H = v.w, v.h
        box_w = int(W * 0.9)
        if fontsize is None:
            fontsize = max(int(H * 0.06), 20)

        # Clamp to prevent trying to render beyond video duration
        items = _clamp_items_to_duration(items, float(v.duration))

        for start, end, text in items:
            dur = max(end - start, 0.1)
            txt = TextClip(
                text,
                fontsize=fontsize,
                color=color,
                font=font or "Segoe UI",  # good default on Windows
                method="caption",
                align="center",
                size=(box_w, None),
                stroke_color=stroke_color,
                stroke_width=stroke_width,
            )
            # Center horizontally; place near bottom with margin
            txt = txt.set_start(start).set_duration(dur).set_position(("center", H - margin_bottom - txt.h))
            subs.append(txt)

        out = CompositeVideoClip([v, *subs])
        out.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=v.fps or 24)
        return output_path
    finally:
        for s in subs:
            with contextlib.suppress(Exception):
                s.close()
        with contextlib.suppress(Exception):
            v.close()

def burn_subtitles_from_srt(
    video_path: str,
    srt_path: str,
    output_path: str,
    font: Optional[str] = None,
    fontsize: Optional[int] = None,
    color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 2,
    margin_bottom: int = 40,
) -> str:
    items = parse_srt(srt_path)
    return burn_subtitles_from_items(
        video_path,
        items,
        output_path,
        font=font,
        fontsize=fontsize,
        color=color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        margin_bottom=margin_bottom,
    )

def transcribe_to_items_whisper(
    video_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
) -> List[Tuple[float, float, str]]:
    """
    Transcribe a video to timed subtitle items using OpenAI Whisper (local 'openai-whisper' package).
    Returns a list of (start_sec, end_sec, text).
    """
    try:
        import whisper  # lazy import
    except Exception as e:
        raise RuntimeError("openai-whisper is not installed. Run: pip install openai-whisper") from e

    # Load model (auto-selects CUDA if available)
    model = whisper.load_model(model_size)

    # Transcribe directly from video file (ffmpeg required)
    result = model.transcribe(video_path, language=language, verbose=False)

    items: List[Tuple[float, float, str]] = []
    for seg in result.get("segments", []):
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 0.5))
        text = str(seg.get("text", "")).strip()
        if text:
            items.append((start, end, text))
    return items

def auto_subtitle_with_whisper(
    video_path: str,
    output_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
    font: Optional[str] = None,
    fontsize: Optional[int] = None,
    color: str = "white",
    stroke_color: str = "black",
    stroke_width: int = 2,
    margin_bottom: int = 40,
) -> str:
    """
    End-to-end: transcribe video with Whisper and burn subtitles onto it.
    """
    items = transcribe_to_items_whisper(video_path, model_size=model_size, language=language)
    return burn_subtitles_from_items(
        video_path=video_path,
        items=items,
        output_path=output_path,
        font=font,
        fontsize=fontsize,
        color=color,
        stroke_color=stroke_color,
        stroke_width=stroke_width,
        margin_bottom=margin_bottom,
    )

if __name__ == "__main__":
    # Example run
    auto_subtitle_with_whisper(
        "input.mp4",
        "input_subtitled.mp4",
        model_size="base",
        language="en",
        font="Segoe UI",
        fontsize=48,
    )
from typing import List
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from moviepy.video.fx.resize import resize as fx_resize


def build_segment_from_images(image_paths: List[str], audio_path: str, output_path: str, fps: int = 24) -> str:
    """Create a segment video using images only with a simple zoom-in (Ken Burns) effect, synced to audio.

    Rules:
    - Two images are expected; if durations don't split evenly, last image absorbs remainder.
    - Zoom from 1.0 to ~1.07 over its portion for subtle motion.
    - Output contains audio from audio_path clamped to video duration.
    """
    if not image_paths:
        raise ValueError("No images provided")

    # Determine total duration from audio
    with AudioFileClip(audio_path) as ac:
        total_dur = float(ac.duration or 0)

    n = len(image_paths)
    base = total_dur / n if n else 0

    def _zoom_clip(img_path: str, duration: float) -> ImageClip:
        c = ImageClip(img_path, duration=duration)
        # Use fx.resize with a time-dependent scale factor; increase from ~7% to ~17% total
        # Use a continuous linear function to avoid jitter/shake (no random components)
        return c.fx(fx_resize, lambda t: 1.0 + 0.17 * (t / max(duration, 1e-6)))

    clips = []
    try:
        for i, img in enumerate(image_paths):
            # Last clip absorbs any rounding remainder
            dur = base if i < n - 1 else total_dur - base * (n - 1)
            dur = max(dur, 0.1)
            clip = _zoom_clip(img, dur)
            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose")
        with AudioFileClip(audio_path) as ac2:
            aud = ac2.subclip(0, min(total_dur, float(video.duration or 0)))
            video = video.set_audio(aud)
            video.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=fps)
        return output_path
    finally:
        for c in clips:
            try:
                c.close()
            except (OSError, RuntimeError, AttributeError):
                pass

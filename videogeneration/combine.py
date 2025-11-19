import contextlib
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips


def combine_two_videos(video1_path, video2_path, audio_path, output_path, fps: int = 24):
    """Concatenate two videos then attach audio, clamping durations to avoid overread errors."""
    v1 = VideoFileClip(video1_path)
    v2 = VideoFileClip(video2_path)
    aud = AudioFileClip(audio_path)

    try:
        seg = concatenate_videoclips([v1, v2], method="compose")

        # Clamp to the shortest of video/audio with a small epsilon
        tol = 1e-3
        vid_dur = float(seg.duration or 0)
        aud_dur = float(aud.duration or 0)
        final_dur = max(min(vid_dur, aud_dur) - tol, 0)

        if vid_dur > final_dur:
            seg = seg.subclip(0, final_dur)
        clamped_audio = aud.subclip(0, final_dur)

        seg = seg.set_audio(clamped_audio)
        seg.write_videofile(output_path, codec="libx264", audio_codec="aac", fps=fps)
        return seg
    finally:
        with contextlib.suppress(Exception):
            v1.close()
        with contextlib.suppress(Exception):
            v2.close()
        with contextlib.suppress(Exception):
            aud.close()


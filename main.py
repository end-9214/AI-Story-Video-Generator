import os
import json as json_mod
from json import JSONDecodeError
import re
import uuid
import contextlib
from datetime import datetime
from typing import Dict, List

# Import pipeline pieces (import before any chdir so imports resolve)
from scripts.llm import get_llm_response, generate_prompts_for_script
from images.image_gen import generate_image_from_prompt
from images.image_to_video import generate_video_from_image
from videogeneration.combine import combine_two_videos
from videogeneration.images_slideshow import build_segment_from_images
from videogeneration.subtitles import auto_subtitle_with_whisper
from utils.common import (
    run_tts,
    generate_image_with_fallback,
    generate_video_with_retries,
)

from moviepy.editor import (
    AudioFileClip,
    VideoFileClip,
    concatenate_videoclips,
    ImageClip,
)


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\-_. ]+", "", text).strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    if not slug:
        slug = str(uuid.uuid4())[:8]
    return slug[:max_len]


def ensure_env_vars() -> None:
    missing = []
    if not os.getenv("GROQ_API_KEY"):
        missing.append("GROQ_API_KEY (LLM)")
    if not os.getenv("HF_TOKEN"):
        missing.append("HF_TOKEN (image generation)")
    if not os.getenv("HF_TOKEN_VIDEO"):
        missing.append("HF_TOKEN_VIDEO (image-to-video)")
    if missing:
        print("Warning: Missing environment variables -> " + ", ".join(missing))
        print(
            "Set them in a .env file or your environment before running for full functionality."
        )


def pick_script_key(scripts: Dict[str, dict]) -> str:
    # Filter out invalid scripts
    valid = {k: v for k, v in scripts.items() if isinstance(v, dict)}
    if not valid:
        raise RuntimeError("No valid scripts returned from LLM.")

    print("\nGenerated scripts:")
    ordered_keys = sorted(
        valid.keys(),
        key=lambda s: int(re.findall(r"\d+", s)[0]) if re.findall(r"\d+", s) else 0,
    )
    for idx, key in enumerate(ordered_keys, 1):
        segs = list(valid[key].keys())
        print(f"  {idx}) {key} - {len(segs)} segments")
        # Preview first segment
        if segs:
            first_seg = segs[0]
            preview = valid[key][first_seg]
            print(
                f"     {first_seg}: {preview[:120]}{'...' if len(preview) > 120 else ''}"
            )

    while True:
        try:
            choice = int(input(f"\nSelect a script [1-{len(ordered_keys)}]: ").strip())
            if 1 <= choice <= len(ordered_keys):
                return ordered_keys[choice - 1]
        except ValueError:
            pass
        print("Invalid choice. Please enter a number in range.")


def natural_segment_order(segments: List[str]) -> List[str]:
    def seg_key(s: str) -> int:
        m = re.findall(r"\d+", s)
        return int(m[0]) if m else 0

    return sorted(segments, key=seg_key)


def load_segment_prompts_from_disk(script_key: str, segment_key: str) -> dict | None:
    """Return prompts for a specific segment if present on disk, else None.

    Looks for session-local image_prompts/ALL_PROMPTS.json as created by scripts.llm.
    """
    try:
        ap = os.path.join("image_prompts", "ALL_PROMPTS.json")
        if not os.path.exists(ap):
            return None
        with open(ap, "r", encoding="utf-8") as f:
            data = json_mod.load(f)
        return data.get(script_key, {}).get(segment_key)
    except (OSError, JSONDecodeError):
        return None


def audio_duration_seconds(audio_path: str) -> float:
    with AudioFileClip(audio_path) as ac:
        return float(ac.duration)


def concatenate_segments(segment_video_paths: List[str], output_path: str) -> None:
    clips = []
    try:
        for p in segment_video_paths:
            clips.append(VideoFileClip(p))
        final = concatenate_videoclips(clips, method="compose")
        final.write_videofile(output_path, codec="libx264", audio_codec="aac")
    finally:
        for c in clips:
            with contextlib.suppress(OSError, RuntimeError, AttributeError):
                c.close()


def adjust_video_to_duration(
    video_path: str, target_duration: float, out_path: str | None = None, fps: int = 24
) -> str:
    """Trim or pad a video so its duration matches target_duration exactly.

    - If longer: trims to target_duration
    - If shorter: pads by freezing the last frame
    Returns the path to the adjusted video file.
    """
    clip = VideoFileClip(video_path)
    final_clip = None
    try:
        cur = float(clip.duration or 0)
        tol = 1e-3
        if cur > target_duration + tol:
            final_clip = clip.subclip(0, target_duration)
        elif cur < target_duration - tol:
            # Freeze last frame to pad
            safe_t = max(cur - 1.0 / fps, 0)
            last_frame = clip.get_frame(safe_t)
            pad_clip = ImageClip(last_frame).set_duration(target_duration - cur)
            final_clip = concatenate_videoclips([clip, pad_clip], method="compose")
        else:
            final_clip = clip

        if out_path is None:
            base, ext = os.path.splitext(video_path)
            out_path = f"{base}_adj{ext}"

        # Write without audio; audio is attached later
        final_clip.write_videofile(out_path, codec="libx264", audio=False, fps=fps)
        return out_path
    finally:
        with contextlib.suppress(Exception):
            if final_clip is not None and final_clip is not clip:
                final_clip.close()
        with contextlib.suppress(Exception):
            clip.close()


def main():
    ensure_env_vars()

    print(
        "Welcome! This workflow will generate a narrated video from your idea, segment by segment."
    )
    idea = input("Enter your idea: ").strip()
    if not idea:
        print("No idea provided. Exiting.")
        return

    # Create unique session directory for this idea
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_name = f"{ts}-{slugify(idea)}"
    base_sessions = os.path.join(os.getcwd(), "sessions")
    os.makedirs(base_sessions, exist_ok=True)
    session_dir = os.path.join(base_sessions, session_name)
    os.makedirs(session_dir, exist_ok=True)

    # Record original CWD and move into session dir so all relative outputs land here
    orig_cwd = os.getcwd()
    os.chdir(session_dir)
    try:
        with open("idea.txt", "w", encoding="utf-8") as f:
            f.write(idea)

        print("\nGenerating 4 candidate scripts from your idea...")
        scripts = get_llm_response(idea)
        if not scripts:
            print("Failed to generate scripts. Exiting.")
            return

        selected_key = pick_script_key(scripts)
        print(f"\nYou selected: {selected_key}")
        selected_script = scripts[selected_key]

        print(
            "\nImage prompts will be generated per segment with full-story context (resume-friendly)..."
        )

        # Optional voice selection
        default_voice = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")
        voice = (
            input(f"\nEnter voice name (blank for default '{default_voice}'): ").strip()
            or default_voice
        )

        # Choose rendering mode
        mode = (
            input(
                "\nRender mode? Type 'videos' for image-to-video or 'images' for images-only (default 'videos'): "
            )
            .strip()
            .lower()
        )
        if mode not in {"videos", "images"}:
            mode = "videos"

        segments_root = os.path.join(session_dir, "segments")
        os.makedirs(segments_root, exist_ok=True)
        segment_output_paths: List[str] = []

        segment_keys = natural_segment_order(list(selected_script.keys()))
        for seg_key in segment_keys:
            print(f"\n=== Processing {seg_key} ===")
            seg_dir = os.path.join(segments_root, seg_key)
            os.makedirs(seg_dir, exist_ok=True)

            seg_text = selected_script[seg_key]
            with open(os.path.join(seg_dir, "segment.txt"), "w", encoding="utf-8") as f:
                f.write(seg_text)

            # 1) Generate voice
            audio_path = os.path.join(seg_dir, "audio.mp3")
            print("Generating voice...")
            run_tts(seg_text, voice, audio_path)

            # 2) Generate or load two image prompts for this segment (context-aware)
            image_prompts = load_segment_prompts_from_disk(selected_key, seg_key)
            if image_prompts:
                print("Found existing prompts for this segment; reusing.")
            else:
                print(
                    "Generating prompts for this segment (with full-script context and continuity)..."
                )
                out = generate_prompts_for_script(selected_key, segment=seg_key)
                image_prompts = (
                    out.get(seg_key)
                    or load_segment_prompts_from_disk(selected_key, seg_key)
                    or {}
                )

            prompt1 = image_prompts.get("image1", {}).get("prompt", seg_text)
            prompt2 = image_prompts.get("image2", {}).get("prompt", seg_text)

            # 3) Generate two images
            print("Generating images...")
            img1_path = os.path.join(seg_dir, "image1.png")
            img2_path = os.path.join(seg_dir, "image2.png")

            if mode == "videos":
                generate_image_from_prompt(prompt=prompt1, save_path=img1_path)
                generate_image_from_prompt(prompt=prompt2, save_path=img2_path)
            else:
                # images-only mode: prefer HF inference, but fallback to local generator on quota/other errors
                generate_image_with_fallback(prompt1, img1_path)
                generate_image_with_fallback(prompt2, img2_path)

            if mode == "videos":
                # 4) Convert images to videos of half the audio duration each
                dur = audio_duration_seconds(audio_path)
                half = max(dur / 2.0, 0.1)
                print(f"Audio duration: {dur:.2f}s -> Each video ~{half:.2f}s")

                # Change CWD to seg_dir for video generation so files save inside the segment
                os.chdir(seg_dir)
                try:
                    print("Generating video 1 from image 1...")
                    vid1_name = generate_video_with_retries(
                        image_path=os.path.basename(img1_path),
                        prompt=prompt1,
                        duration_seconds=half,
                        label="video 1",
                    )
                    vid1_path = os.path.join(seg_dir, vid1_name)
                    vid1_path = adjust_video_to_duration(vid1_path, half)

                    print("Generating video 2 from image 2...")
                    vid2_name = generate_video_with_retries(
                        image_path=os.path.basename(img2_path),
                        prompt=prompt2,
                        duration_seconds=half,
                        label="video 2",
                    )
                    vid2_path = os.path.join(seg_dir, vid2_name)
                    vid2_path = adjust_video_to_duration(vid2_path, half)
                finally:
                    os.chdir(session_dir)

                # 5) Combine the two videos and attach the segment audio
                segment_video_path = os.path.join(seg_dir, f"{seg_key}.mp4")
                print("Combining videos and attaching audio for segment...")
                combine_two_videos(vid1_path, vid2_path, audio_path, segment_video_path)
                segment_output_paths.append(segment_video_path)
                print(f"Completed {seg_key}: {segment_video_path}")
            else:
                # Images-only: build a segment video from two images with zoom, synced to audio
                segment_video_path = os.path.join(seg_dir, f"{seg_key}.mp4")
                print(
                    "Composing images-only segment (zoom effect) and attaching audio..."
                )
                build_segment_from_images(
                    [img1_path, img2_path], audio_path, segment_video_path
                )
                segment_output_paths.append(segment_video_path)
                print(f"Completed {seg_key}: {segment_video_path}")

        # Final concatenation of all segments in order
        final_output = os.path.join(session_dir, "final_output.mp4")
        print("\nConcatenating all segments into the final video...")
        concatenate_segments(segment_output_paths, final_output)

        # Auto-generate and burn subtitles with Whisper
        print(
            "Transcribing and burning subtitles with Whisper (requires ffmpeg + ImageMagick)..."
        )
        subtitled_output = os.path.join(session_dir, "final_output_subtitled.mp4")
        auto_subtitle_with_whisper(
            video_path=final_output,
            output_path=subtitled_output,
            model_size=os.getenv("WHISPER_MODEL_SIZE", "base"),
            language=os.getenv("WHISPER_LANG", None) or None,
            font=os.getenv("SUBTITLES_FONT", "Segoe UI"),
            fontsize=None,
            color="white",
            stroke_color="black",
            stroke_width=2,
            margin_bottom=40,
        )
        print(
            f"\nAll done! Final videos:\n - No subtitles: {final_output}\n - Subtitled:   {subtitled_output}"
        )

    finally:
        # Always go back to original working directory
        os.chdir(orig_cwd)


if __name__ == "__main__":
    main()

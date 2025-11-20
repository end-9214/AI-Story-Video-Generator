"""Shared utility functions used across the AI Story Video Generator pipeline."""

import os
import time
import asyncio
from typing import Optional
from contextlib import contextmanager


@contextmanager
def pushd(new_dir: str):
    """Context manager for temporarily changing the current working directory.

    Args:
        new_dir: Directory to change to (will be created if it doesn't exist)

    Example:
        with pushd("/tmp/test"):
            # Do work in /tmp/test
            pass
        # Back to original directory
    """
    old = os.getcwd()
    os.makedirs(new_dir, exist_ok=True)
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(old)


def run_tts(text: str, voice: str, out_path: str) -> None:
    """Generate audio from text using Edge TTS (synchronous wrapper).

    Args:
        text: Text to convert to speech
        voice: Voice name (e.g., "en-US-AriaNeural")
        out_path: Path where the audio file will be saved
    """
    from voicegeneration.voice_gen import generate_audio as tts_generate_audio

    asyncio.run(tts_generate_audio(text=text, voice=voice, output_file=out_path))


def generate_image_with_fallback(prompt: str, save_path: str) -> None:
    """Generate an image from a prompt with fallback to local generator on HF inference failure.

    Tries HF inference first (quota-based), falls back to Gradio Space on error.

    Args:
        prompt: Text prompt for image generation
        save_path: Path where the image will be saved

    Raises:
        RuntimeError: If both HF inference and fallback generation fail
    """
    from images.hf_inference_image_gen import (
        generate_and_save_image as hf_generate_and_save_image,
    )
    from images.image_gen import generate_image_from_prompt

    try:
        hf_generate_and_save_image(prompt, save_path)
    except Exception as e:
        # Fallback to local generator
        try:
            generate_image_from_prompt(prompt=prompt, save_path=save_path)
        except Exception as e2:
            raise RuntimeError(
                f"Both HF inference and fallback image generation failed: hf_error={e}; fallback_error={e2}"
            ) from e2


def generate_video_with_retries(
    image_path: str, prompt: str, duration_seconds: float, label: str = "video"
) -> str:
    """Generate a video from an image with automatic retries and backoff.

    Uses environment variables for configuration:
        VIDEO_GEN_WAIT_SECONDS: Seconds to wait between attempts (default: 10)
        VIDEO_GEN_MAX_RETRIES: Maximum number of retry attempts (default: 5)

    Args:
        image_path: Path to the input image
        prompt: Text prompt for video generation
        duration_seconds: Target duration of the generated video
        label: Label for logging purposes (default: "video")

    Returns:
        The filename of the generated video

    Raises:
        RuntimeError: If all retry attempts fail
    """
    from images.image_to_video import generate_video_from_image

    wait_s = float(os.getenv("VIDEO_GEN_WAIT_SECONDS", "10"))
    max_retries = int(os.getenv("VIDEO_GEN_MAX_RETRIES", "5"))
    attempt = 0
    last_err: Optional[Exception] = None

    while attempt <= max_retries:
        if wait_s > 0:
            print(
                f"Waiting {wait_s:.1f}s before generating {label} (attempt {attempt+1}/{max_retries+1})..."
            )
            time.sleep(wait_s)
        try:
            name, _meta = generate_video_from_image(
                image_path=image_path, prompt=prompt, duration_seconds=duration_seconds
            )
            return name
        except Exception as e:
            last_err = e
            attempt += 1
            if attempt <= max_retries:
                print(
                    f"{label} generation failed (attempt {attempt}/{max_retries+1}): {e}. Retrying..."
                )

    raise RuntimeError(
        f"{label} generation failed after {attempt} attempts: {last_err}"
    )

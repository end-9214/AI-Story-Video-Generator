from gradio_client import Client, handle_file
import os
from dotenv import load_dotenv
import shutil

load_dotenv()


def generate_video_from_image(
    image_path: str,
    prompt: str,
    steps: int = 4,
    duration_seconds: float = None,
    negative_prompt: str = None,
    guidance_scale: float = 1.0,
    guidance_scale_2: float = 1.0,
    seed: int = 42,
    randomize_seed: bool = True,
    space_name: str = "end9214/wan2-2-fp8da-aoti-faster",
    api_name: str = "/generate_video",
) -> tuple[str, int]:
    """
    Calls the Wan 2.2 I2V Space's generate_video endpoint and downloads the resulting video.
    Returns the local video path and the seed used.
    """

    client = Client(space_name, hf_token=os.getenv("HF_TOKEN_VIDEO"))
    inputs = {
        "input_image": handle_file(image_path),
        "prompt": prompt,
        "steps": steps,
        "randomize_seed": randomize_seed,
        "seed": seed,
        "guidance_scale": guidance_scale,
        "guidance_scale_2": guidance_scale_2,
    }
    if duration_seconds is not None:
        inputs["duration_seconds"] = duration_seconds
    if negative_prompt is not None:
        inputs["negative_prompt"] = negative_prompt

    result, used_seed = client.predict(**inputs, api_name=api_name)

    if isinstance(result, dict) and "video" in result:
        remote_video_path = result["video"]
    else:
        raise ValueError(f"Unexpected return format: {result}")

    print(f"Received video from Space: {remote_video_path}, seed used: {used_seed}")

    output_filename = f"generated_{used_seed}.mp4"
    try:
        shutil.copy(remote_video_path, output_filename)
        print(f"Video saved as: {output_filename}")
    except Exception as e:
        print(f"Failed to copy video file: {e}")
        raise

    return output_filename, used_seed


if __name__ == "__main__":
    img_path = "generated_image.png"
    prompt_text = (
        "From a low-angle, the lion is seen lunging forward in pursuit, its body low to the ground, as the bear's legs blur while running through the dense underbrush with trees framing the scene, in a cinematic naturalistic illustration style with a cohesive color palette, soft rim lighting, and volumetric atmosphere."
    )
    video_path, video_seed = generate_video_from_image(
        image_path=img_path,
        prompt=prompt_text,
        steps=6,
        duration_seconds=3.5,
        guidance_scale=1.2,
        seed=100,
        randomize_seed=False,
    )
    print(f"Done! Video available at: {video_path}")

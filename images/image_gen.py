import os
from gradio_client import Client
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

def generate_image_from_prompt(
    prompt: str,
    seed: int = 0,
    randomize_seed: bool = True,
    aspect_ratio: str = "1:1",
    guidance_scale: float = 1.0,
    num_inference_steps: int = 5,
    prompt_enhance: bool = True,
    save_path: str = "generated_image.png",
    space_name: str = "multimodalart/Qwen-Image-Fast",
    api_name: str = "/infer"
) -> int:
    """
    Calls the remote Gradio image generation API and saves the resulting image.

    Args:
        prompt: Text prompt for image generation.
        seed: Base seed for reproducibility.
        randomize_seed: If True, overrides seed with a random value.
        aspect_ratio: Desired output aspect ratio (e.g., "1:1", "16:9").
        guidance_scale: Controls prompt adherence.
        num_inference_steps: Number of diffusion steps.
        prompt_enhance: Whether to enhance the prompt using LLM.
        save_path: Local filename to save the generated image.
        space_name: Hugging Face Space identifier (user/space).
        api_name: Named API endpoint to invoke (must match your app).

    Returns:
        The actual seed used for generation.

    Example:
        used_seed = generate_image_from_prompt("A serene mountain sunrise")
        print(f"Image saved with seed {used_seed}")
    """
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        raise EnvironmentError("HF_TOKEN is not set in your environment.")

    client = Client(space_name, hf_token=hf_token)
    print("Available API endpoints and usage spec:")
    print(client.view_api())

    # Call the remote inference function
    image_path, used_seed = client.predict(
        prompt=prompt,
        seed=seed,
        randomize_seed=randomize_seed,
        aspect_ratio=aspect_ratio,
        guidance_scale=guidance_scale,
        num_inference_steps=num_inference_steps,
        prompt_enhance=prompt_enhance,
        api_name=api_name
    )

    print(f"Generated image stored temporarily at: {image_path}")
    print(f"Seed used: {used_seed}")

    try:
        image = Image.open(image_path)
        image.save(save_path)
        print(f"Image successfully saved as: {save_path}")
    except Exception as e:
        raise RuntimeError(f"Failed to open or save the image: {e}") from e

    return used_seed



if __name__ == "__main__":
    generate_image_from_prompt("From a low-angle, the lion is seen lunging forward in pursuit, its body low to the ground, as the bear's legs blur while running through the dense underbrush with trees framing the scene, in a cinematic naturalistic illustration style with a cohesive color palette, soft rim lighting, and volumetric atmosphere.")
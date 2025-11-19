import os
from functools import lru_cache
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()

@lru_cache(maxsize=1)
def _get_client() -> InferenceClient:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise EnvironmentError("HF_TOKEN is not set or inference client failed to initialize.")
    return InferenceClient(provider="fal-ai", api_key=token)


def generate_and_save_image(prompt: str, save_path: str) -> str:
    """Generate an image from a text prompt using Qwen/Qwen-Image (fal-ai provider) and save it.

    Args:
        prompt: text prompt
        save_path: absolute or relative path to save PNG
    Returns:
        The save_path
    """
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    client = _get_client()
    image = client.text_to_image(prompt, model="Qwen/Qwen-Image")
    image.save(save_path)
    return save_path

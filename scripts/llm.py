from groq import Groq
from dotenv import load_dotenv
import os
import json
import re
from typing import Optional

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_llm_response(user_query):
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "system",
                "content": (
                    "You must think of a story script according to user idea and generate exactly four scripts, output in JSON format as follows:\n"
                    "{\n"
                    "  \"script1\": { \"segment1\": \"...\", \"segment2\": \"...\", ... },\n"
                    "  \"script2\": { ... },\n"
                    "  \"script3\": { ... },\n"
                    "  \"script4\": { ... }\n"
                    "}\n\n"
                    "Requirements for each script:\n"
                    "1. Exactly 150 words total.\n"
                    "2. Divide into segments labeled \"segment1\", \"segment2\", etc. there should be enough segments to cover the entire script.\n"
                    "3. Each segment must contain exactly 15 words (split by whitespace).\n"
                    "4. The scripts must have a start and a proper conclusion.\n"
                    "5. If a script fails any constraint, its value must be the string \"ERROR\".\n"
                    "6. If a user wants you to generate a script in Hindi language then that script in Hindi language and should contain a lot of funny words.\n"
                    "7. Maximum only 6 segments\n\n"
                    "Generate scripts based on the user's prompt."
                )
            },
            {
                "role": "user",
                "content": user_query
            }
        ],
        temperature=1,
        max_completion_tokens=1024,
        top_p=1,
        stream=False,
        response_format={"type": "json_object"},
        stop=None
    )
    raw_content = completion.choices[0].message.content
    try:
        scripts = json.loads(raw_content)
    except json.JSONDecodeError as e:
        print("Error parsing JSON from LLM:", e)
        scripts = None

    if scripts:
        with open("scripts.json", "w", encoding="utf-8") as f:
            json.dump(scripts, f, indent=4, ensure_ascii=False)

    return scripts

def generate_prompts_for_script(
    script_key: str,
    scripts_path: str = "scripts.json",
    segment: Optional[str] = None,
):
    """Generate image prompts for a script.

    Behavior:
    - Pass the full script as context to the LLM and specify the current segment to generate prompts for.
    - If `segment` is provided, only that segment is generated (useful for step-by-step, contextual generation).
    - Previously generated prompts (from image_prompts/ALL_PROMPTS.json) for earlier segments are provided as continuity context.
    - Results are merged into image_prompts/ALL_PROMPTS.json without overwriting other scripts/segments.
    """

    with open(scripts_path, "r", encoding="utf-8") as f:
        scripts = json.load(f)

    if script_key not in scripts:
        raise KeyError(f"Script key '{script_key}' not found in {scripts_path}")

    script_obj = scripts[script_key]
    if not isinstance(script_obj, dict):
        raise ValueError(f"Script '{script_key}' is not a valid segmented script: {type(script_obj)}")

    def seg_index(k: str) -> int:
        m = re.search(r"(\d+)", k)
        return int(m.group(1)) if m else 10**9

    ordered_segments = sorted(script_obj.items(), key=lambda kv: seg_index(kv[0]))

    # Choose which segments to process
    if segment is not None:
        if segment not in script_obj:
            raise KeyError(f"Segment '{segment}' not found in script '{script_key}'")
        segments_to_process = [(segment, script_obj[segment])]
    else:
        segments_to_process = ordered_segments

    # Load existing prompts to preserve and provide continuity
    existing_all = {}
    all_prompts_path = os.path.join("image_prompts", "ALL_PROMPTS.json")
    if os.path.exists(all_prompts_path):
        try:
            with open(all_prompts_path, "r", encoding="utf-8") as f:
                existing_all = json.load(f)
        except (OSError, json.JSONDecodeError):
            existing_all = {}

    existing_for_script = existing_all.get(script_key, {})

    # Build full-script context (both structured and concatenated text)
    full_script_segments = [
        {"id": sk, "text": st} for sk, st in ordered_segments
    ]
    full_script_text = " ".join(st for _, st in ordered_segments)

    result = {}

    style_instruction = (
        "Generate two highly detailed cinematic image prompts (image1, image2), 55-75 tokens each. "
        "Each prompt must be a single sentence (no line breaks). Include camera angle and clear subject motion. "
        "Avoid using character names; use descriptive objects (e.g., 'a human', 'a dog'). "
        "Ensure image1 and image2 differ in composition/angle/mood. Maintain story continuity with prior segments when provided."
    )

    for segment_key, segment_text in segments_to_process:
        # Provide continuity: previously generated prompts for segments before the current one
        prev_prompts = {}
        for sk, _ in ordered_segments:
            if seg_index(sk) < seg_index(segment_key):
                if sk in existing_for_script:
                    prev_prompts[sk] = existing_for_script[sk]

        payload = {
            "script_id": script_key,
            "current_segment_id": segment_key,
            "current_segment_text": segment_text,
            "full_script_segments": full_script_segments,
            "full_script_text": full_script_text,
            "previous_image_prompts": prev_prompts,
            "instruction": style_instruction,
        }

        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an expert cinematic image prompt engineer. "
                        "Use the full story context and the specified current segment to craft two distinct prompts. "
                        "Also keep in mind understand the scripts correctly and then generate images prompt according to the scripts demand, mention gender too; also use creative words too if needed like a human cat, muscular <anything which is in the script> for objects."
                        'Return ONLY strict JSON: {"image1":{"prompt":str}, "image2":{"prompt":str}}. '
                        "Each prompt must be exactly one sentence, no quotes, no lists, no line breaks. "
                        "Ensure the two prompts differ in angle/composition/mood, and maintain continuity with prior segments when provided."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.45,
            max_completion_tokens=900,
            top_p=1,
            stream=False,
            response_format={"type": "json_object"},
        )
        raw = completion.choices[0].message.content
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback to a trimmed segment text for both prompts
            data = {
                "image1": {"prompt": segment_text[:120]},
                "image2": {"prompt": segment_text[:120]},
            }

        result[segment_key] = data

        # Merge-save progressively for robustness
        os.makedirs("image_prompts", exist_ok=True)
        # Refresh in-memory state to avoid clobbering concurrent updates
        latest_all = {}
        if os.path.exists(all_prompts_path):
            try:
                with open(all_prompts_path, "r", encoding="utf-8") as f:
                    latest_all = json.load(f)
            except (OSError, json.JSONDecodeError):
                latest_all = {}
        latest_all.setdefault(script_key, {})
        latest_all[script_key][segment_key] = data
        with open(all_prompts_path, "w", encoding="utf-8") as f:
            json.dump(latest_all, f, indent=4, ensure_ascii=False)

        # Update local cache for continuity on subsequent segments in this run
        existing_for_script[segment_key] = data

    return result

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate detailed cinematic image prompts with full-script context")
    parser.add_argument("--script", required=True, help="Script key e.g. script1")
    parser.add_argument(
        "--segment",
        required=False,
        help="Optional segment id to generate only that segment (e.g., segment2). If omitted, all segments are generated.",
    )
    args = parser.parse_args()
    out = generate_prompts_for_script(args.script, segment=args.segment)
    print(json.dumps(out, indent=2, ensure_ascii=False))

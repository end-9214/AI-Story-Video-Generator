import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Reuse existing pipeline pieces
from scripts.llm import get_llm_response, generate_prompts_for_script
from images.image_gen import generate_image_from_prompt
from videogeneration.combine import combine_two_videos
from videogeneration.images_slideshow import build_segment_from_images
from videogeneration.subtitles import auto_subtitle_with_whisper
from utils.common import (
    run_tts,
    generate_image_with_fallback,
    generate_video_with_retries,
    pushd,
)

# Utility helpers imported from main.py to keep behavior identical
from main import (
    slugify,
    natural_segment_order,
    audio_duration_seconds,
    concatenate_segments,
    adjust_video_to_duration,
)


# ---------------- API scaffolding ----------------
app = FastAPI(title="Minor Project Video Generator API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SESSIONS_ROOT = os.path.join(os.getcwd(), "sessions")
VOICES_PATH = os.path.join(os.getcwd(), "voicegeneration", "voices.json")


# -------- Status helpers --------


def _status_path(session_dir: str) -> str:
    return os.path.join(session_dir, "status.json")


def _write_status(session_dir: str, payload: Dict) -> None:
    try:
        with open(_status_path(session_dir), "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def _read_status(session_dir: str) -> Dict:
    try:
        with open(_status_path(session_dir), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# -------- Core generation logic (non-interactive) --------


def create_session(idea: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    session_name = f"{ts}-{slugify(idea)}"
    session_dir = os.path.join(SESSIONS_ROOT, session_name)
    os.makedirs(session_dir, exist_ok=True)
    with open(os.path.join(session_dir, "idea.txt"), "w", encoding="utf-8") as f:
        f.write(idea)
    # Init status
    _write_status(
        session_dir,
        {
            "session_id": session_name,
            "idea": idea,
            "state": "created",
            "progress": {"total_segments": 0, "completed": 0},
            "artifacts": {},
            "error": None,
        },
    )
    return session_name


def generate_scripts_for_session(session_id: str) -> Dict[str, Dict]:
    session_dir = os.path.join(SESSIONS_ROOT, session_id)
    if not os.path.isdir(session_dir):
        raise FileNotFoundError("Session not found")
    idea = open(os.path.join(session_dir, "idea.txt"), "r", encoding="utf-8").read()

    # Ensure scripts.json goes into this session
    with pushd(session_dir):
        scripts = get_llm_response(idea)

    if not scripts or not isinstance(scripts, dict):
        raise RuntimeError("Failed to generate scripts")

    # Save separately too for debugging
    with open(os.path.join(session_dir, "scripts.json"), "w", encoding="utf-8") as f:
        json.dump(scripts, f, indent=2, ensure_ascii=False)

    st = _read_status(session_dir)
    st.update({"state": "scripts_ready", "script_keys": list(scripts.keys())})
    _write_status(session_dir, st)
    return scripts


def run_pipeline(
    session_id: str, script_key: str, voice: Optional[str], mode: str = "videos"
) -> None:
    session_dir = os.path.join(SESSIONS_ROOT, session_id)
    if not os.path.isdir(session_dir):
        raise FileNotFoundError("Session not found")

    # Defaults
    default_voice = os.getenv("EDGE_TTS_VOICE", "en-US-AriaNeural")
    voice = voice or default_voice
    mode = mode if mode in {"videos", "images"} else "videos"

    # Load scripts generated earlier (ensure exist)
    scripts_path = os.path.join(session_dir, "scripts.json")
    if not os.path.exists(scripts_path):
        raise HTTPException(
            status_code=400, detail="Scripts not generated for this session yet."
        )
    with open(scripts_path, "r", encoding="utf-8") as f:
        scripts: Dict[str, Dict] = json.load(f)
    if script_key not in scripts or not isinstance(scripts[script_key], dict):
        raise HTTPException(status_code=400, detail="Invalid script_key.")

    selected_script = scripts[script_key]

    # Status init
    seg_keys = natural_segment_order(list(selected_script.keys()))
    status = _read_status(session_dir)
    status.update(
        {
            "state": "running",
            "voice": voice,
            "mode": mode,
            "selected_script": script_key,
            "progress": {"total_segments": len(seg_keys), "completed": 0},
        }
    )
    _write_status(session_dir, status)

    segments_root = os.path.join(session_dir, "segments")
    os.makedirs(segments_root, exist_ok=True)
    segment_output_paths: List[str] = []

    try:
        for i, seg_key in enumerate(seg_keys, start=1):
            seg_dir = os.path.join(segments_root, seg_key)
            os.makedirs(seg_dir, exist_ok=True)

            seg_text = selected_script[seg_key]
            with open(os.path.join(seg_dir, "segment.txt"), "w", encoding="utf-8") as f:
                f.write(seg_text)

            # Update status
            status.update(
                {
                    "current_segment": seg_key,
                    "progress": {"total_segments": len(seg_keys), "completed": i - 1},
                }
            )
            _write_status(session_dir, status)

            # 1) TTS
            audio_path = os.path.join(seg_dir, "audio.mp3")
            run_tts(seg_text, voice, audio_path)

            # 2) Generate or load prompts for this segment
            # Ensure prompt generation happens with CWD=session_dir so files go to session
            with pushd(session_dir):
                try:
                    # Try to infer from ALL_PROMPTS.json if exists
                    image_prompts = {}
                    ap = os.path.join("image_prompts", "ALL_PROMPTS.json")
                    if os.path.exists(ap):
                        try:
                            with open(ap, "r", encoding="utf-8") as f:
                                allp = json.load(f)
                            image_prompts = allp.get(script_key, {}).get(seg_key, {})
                        except Exception:
                            image_prompts = {}
                    if not image_prompts:
                        out = generate_prompts_for_script(script_key, segment=seg_key)
                        image_prompts = out.get(seg_key, {})
                except Exception:
                    # Fallback: use segment text if LLM prompt generation fails
                    image_prompts = {}

            prompt1 = image_prompts.get("image1", {}).get("prompt", seg_text)
            prompt2 = image_prompts.get("image2", {}).get("prompt", seg_text)

            # 3) Images
            img1_path = os.path.join(seg_dir, "image1.png")
            img2_path = os.path.join(seg_dir, "image2.png")
            if mode == "videos":
                generate_image_from_prompt(prompt=prompt1, save_path=img1_path)
                generate_image_from_prompt(prompt=prompt2, save_path=img2_path)
            else:
                generate_image_with_fallback(prompt1, img1_path)
                generate_image_with_fallback(prompt2, img2_path)

            if mode == "videos":
                # 4) Convert to videos of half the audio duration each
                dur = audio_duration_seconds(audio_path)
                half = max(dur / 2.0, 0.1)

                with pushd(seg_dir):
                    vid1_name = generate_video_with_retries(
                        image_path=os.path.basename(img1_path),
                        prompt=prompt1,
                        duration_seconds=half,
                        label="video 1",
                    )
                    vid1_path = os.path.join(seg_dir, vid1_name)
                    vid1_path = adjust_video_to_duration(vid1_path, half)

                    vid2_name = generate_video_with_retries(
                        image_path=os.path.basename(img2_path),
                        prompt=prompt2,
                        duration_seconds=half,
                        label="video 2",
                    )
                    vid2_path = os.path.join(seg_dir, vid2_name)
                    vid2_path = adjust_video_to_duration(vid2_path, half)

                # 5) Combine and attach audio
                segment_video_path = os.path.join(seg_dir, f"{seg_key}.mp4")
                combine_two_videos(vid1_path, vid2_path, audio_path, segment_video_path)
                segment_output_paths.append(segment_video_path)
            else:
                # Images-only segment video with zoom
                segment_video_path = os.path.join(seg_dir, f"{seg_key}.mp4")
                build_segment_from_images(
                    [img1_path, img2_path], audio_path, segment_video_path
                )
                segment_output_paths.append(segment_video_path)

            status.update(
                {"progress": {"total_segments": len(seg_keys), "completed": i}}
            )
            _write_status(session_dir, status)

        # Final concatenation
        final_output = os.path.join(session_dir, "final_output.mp4")
        concatenate_segments(segment_output_paths, final_output)

        # Subtitles
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

        status.update(
            {
                "state": "completed",
                "artifacts": {
                    "final": final_output,
                    "subtitled": subtitled_output,
                    "segments": segment_output_paths,
                },
            }
        )
        _write_status(session_dir, status)
    except Exception as e:
        status.update({"state": "failed", "error": str(e)})
        _write_status(session_dir, status)
        raise


# ---------------- Endpoints ----------------


@app.post("/api/sessions", summary="Create a session from an idea")
def api_create_session(payload: Dict[str, str]):
    idea = (payload or {}).get("idea", "").strip()
    if not idea:
        raise HTTPException(status_code=400, detail="'idea' is required")
    session_id = create_session(idea)
    return {"session_id": session_id}


@app.post("/api/scripts", summary="Generate candidate scripts for a session")
def api_generate_scripts(payload: Dict[str, str]):
    session_id = (payload or {}).get("session_id", "").strip()
    if not session_id:
        # Allow single-call create+scripts if only idea passed
        idea = (payload or {}).get("idea", "").strip()
        if not idea:
            raise HTTPException(
                status_code=400, detail="Provide 'session_id' or 'idea'"
            )
        session_id = create_session(idea)
    scripts = generate_scripts_for_session(session_id)
    ordered_keys = sorted(
        [k for k, v in scripts.items() if isinstance(v, dict)],
        key=lambda s: (
            int(__import__("re").findall(r"\d+", s)[0])
            if __import__("re").findall(r"\d+", s)
            else 0
        ),
    )
    return {"session_id": session_id, "scripts": scripts, "ordered_keys": ordered_keys}


@app.post(
    "/api/sessions/{session_id}/run", summary="Start generation for a selected script"
)
def api_run_session(
    session_id: str, payload: Dict[str, str], background: BackgroundTasks
):
    script_key = (payload or {}).get("script_key", "").strip()
    if not script_key:
        raise HTTPException(status_code=400, detail="'script_key' is required")
    voice = (payload or {}).get("voice")
    mode = (payload or {}).get("mode", "videos")

    # Schedule background job
    background.add_task(
        run_pipeline,
        session_id=session_id,
        script_key=script_key,
        voice=voice,
        mode=mode,
    )

    st = _read_status(os.path.join(SESSIONS_ROOT, session_id))
    st.update(
        {"state": "queued", "selected_script": script_key, "voice": voice, "mode": mode}
    )
    _write_status(os.path.join(SESSIONS_ROOT, session_id), st)

    return {
        "session_id": session_id,
        "status_url": f"/api/sessions/{session_id}",
        "message": "Generation started",
    }


@app.get("/api/sessions", summary="List existing sessions")
def api_list_sessions():
    if not os.path.exists(SESSIONS_ROOT):
        return {"sessions": []}
    sessions = [
        d
        for d in os.listdir(SESSIONS_ROOT)
        if os.path.isdir(os.path.join(SESSIONS_ROOT, d))
    ]
    sessions.sort(reverse=True)
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}", summary="Get session status")
def api_get_status(session_id: str, request: Request):
    session_dir = os.path.join(SESSIONS_ROOT, session_id)
    if not os.path.isdir(session_dir):
        raise HTTPException(status_code=404, detail="Session not found")
    st = _read_status(session_dir)
    # Optionally enrich artifacts if missing
    if st.get("state") == "completed" and "artifacts" in st:
        for k in ["final", "subtitled"]:
            p = st["artifacts"].get(k)
            if p and not os.path.isabs(p):
                st["artifacts"][k] = os.path.join(session_dir, os.path.basename(p))
    # Autodetect final artifacts in session root even if status.json doesn't have them (older sessions)
    auto_final = os.path.join(session_dir, "final_output.mp4")
    auto_sub = os.path.join(session_dir, "final_output_subtitled.mp4")
    st.setdefault("artifacts", {})
    if os.path.exists(auto_final) and not st["artifacts"].get("final"):
        st["artifacts"]["final"] = auto_final
    if os.path.exists(auto_sub) and not st["artifacts"].get("subtitled"):
        st["artifacts"]["subtitled"] = auto_sub

    # Build a segments inventory (images, intermediate videos, audios, segment video)
    segments_root = os.path.join(session_dir, "segments")
    segments_info: Dict[str, Dict[str, List[str]]] = {}
    if os.path.isdir(segments_root):
        for seg in sorted(os.listdir(segments_root)):
            seg_dir = os.path.join(segments_root, seg)
            if not os.path.isdir(seg_dir):
                continue
            files = os.listdir(seg_dir)
            images = [f for f in files if f.lower().endswith((".png", ".jpg", ".jpeg"))]
            videos = [f for f in files if f.lower().endswith(".mp4")]
            audios = [f for f in files if f.lower().endswith((".mp3", ".wav", ".m4a"))]

            # Convert to artifact URLs
            def _url(p: str) -> str:
                # Return an absolute URL to download this artifact via the API
                base = str(request.base_url).rstrip("/")
                return f"{base}/api/sessions/{session_id}/artifact/{seg}/{p}"

            segments_info[seg] = {
                "images": [_url(f) for f in images],
                "videos": [_url(f) for f in videos],
                "audios": [_url(f) for f in audios],
            }

    st["segments_info"] = segments_info

    # Attach artifact URLs for final/subtitled if present
    artifacts = st.get("artifacts") or {}
    art_urls: Dict[str, str] = {}
    for name in ("subtitled", "final"):
        p = artifacts.get(name)
        if p and os.path.exists(p):
            base = str(request.base_url).rstrip("/")
            art_urls[name] = (
                f"{base}/api/sessions/{session_id}/artifact/{os.path.basename(p)}"
            )
    st["artifacts_urls"] = art_urls

    return st


@app.get(
    "/api/sessions/{session_id}/download/{kind}",
    summary="Download final or subtitled video",
)
def api_download(session_id: str, kind: str):
    session_dir = os.path.join(SESSIONS_ROOT, session_id)
    if not os.path.isdir(session_dir):
        raise HTTPException(status_code=404, detail="Session not found")
    file_map = {
        "final": os.path.join(session_dir, "final_output.mp4"),
        "subtitled": os.path.join(session_dir, "final_output_subtitled.mp4"),
    }
    if kind not in file_map:
        raise HTTPException(
            status_code=400, detail="kind must be 'final' or 'subtitled'"
        )
    path = file_map[kind]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"{kind} video not available yet")
    return FileResponse(path, media_type="video/mp4", filename=os.path.basename(path))


@app.get(
    "/api/sessions/{session_id}/artifact/{relpath:path}",
    summary="Download an arbitrary artifact from a session (images, segment videos, audio)",
)
def api_get_artifact(session_id: str, relpath: str):
    session_dir = os.path.join(SESSIONS_ROOT, session_id)
    if not os.path.isdir(session_dir):
        raise HTTPException(status_code=404, detail="Session not found")

    # Normalize and prevent path traversal: relpath is relative to session_dir
    requested = os.path.normpath(os.path.join(session_dir, relpath))
    if not requested.startswith(os.path.abspath(session_dir)):
        raise HTTPException(status_code=400, detail="Invalid path")
    if not os.path.exists(requested) or not os.path.isfile(requested):
        raise HTTPException(status_code=404, detail="File not found")

    # Guess media type
    _, ext = os.path.splitext(requested)
    ext = ext.lower()
    media_type = "application/octet-stream"
    if ext in (".png", ".jpg", ".jpeg"):
        media_type = "image/" + ("jpeg" if ext in (".jpg", ".jpeg") else "png")
    elif ext == ".mp4":
        media_type = "video/mp4"
    elif ext in (".mp3",):
        media_type = "audio/mpeg"

    return FileResponse(
        requested, media_type=media_type, filename=os.path.basename(requested)
    )


@app.get("/api/voices", summary="List available TTS voices")
def api_list_voices(flat: bool | None = False):
    """Return the voices.json mapping. If flat=true, return a flat array of voices.

    Flat item shape: { "name": str, "lang": str, "region": str, "gender": "Male"|"Female" }
    """
    if not os.path.exists(VOICES_PATH):
        raise HTTPException(status_code=404, detail="voices.json not found")
    try:
        with open(VOICES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read voices.json: {e}")

    if not flat:
        return data

    flat_list = []
    # Nested shape: lang -> country -> gender -> [names]
    for lang, countries in (data or {}).items():
        if not isinstance(countries, dict):
            continue
        for region, genders in countries.items():
            if not isinstance(genders, dict):
                continue
            for gender, names in genders.items():
                for name in names:
                    flat_list.append(
                        {
                            "name": name,
                            "lang": lang,
                            "region": region,
                            "gender": gender,
                        }
                    )
    # Sort: lang, region, gender, then name
    flat_list.sort(key=lambda x: (x["lang"], x["region"], x["gender"], x["name"]))
    return {"voices": flat_list}

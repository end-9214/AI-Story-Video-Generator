# Minor Project – Idea → Narrated Video (ZeroGPU)

End-to-end pipeline that turns an idea into a narrated, subtitled video using:

- Text-to-Image (T2I): Qwen-Image with Lightning LoRA and FlowMatch Euler (via Hugging Face Spaces)
- Image-to-Video (I2V): Wan 2.2 (14B) optimized with INT8/FP8 + AOTI (via Hugging Face Spaces)
- Orchestration: FastAPI (Windows host) with session management, retries, and artifact APIs
- Media: Edge TTS narration, FFmpeg composition, Whisper subtitles, ImageMagick-backed burn-in

The frontend (Next.js) provides a simple UI to create sessions, choose scripts, run the pipeline, and download outputs. Heavy inference runs in Spaces (ZeroGPU); the local machine does not require a GPU.

---

## Features

- Idea → scripts → images → animated clips → stitched video → auto-subtitled video
- ZeroGPU-ready: model inference via Hugging Face Spaces with on-demand GPUs
- Reliability: retries/backoff for I2V, deterministic duration alignment to narration
- Artifacts and status: per-segment images/videos/audio; progress and download URLs
- Works on Windows; no local GPU required

---

## Architecture

```
[Browser/Client]
    │
    ▼
[Next.js Frontend] ───── HTTP/JSON ─────► [FastAPI Backend (Windows)]
                                           │
                                           ├─ Edge TTS → audio.mp3
                                           ├─ T2I (HF Space) → image1.png, image2.png
                                           ├─ I2V (HF Space) → vid1.mp4, vid2.mp4
                                           ├─ FFmpeg compose/concat → seg_X.mp4, final_output.mp4
                                           └─ Whisper + ImageMagick → final_output_subtitled.mp4
```

Session artifacts are saved under `sessions/<SESSION_ID>/`.

---

## Requirements

Local (backend orchestration):

- Windows 10/11, Python 3.10+
- FFmpeg on PATH (video processing)
- ImageMagick on PATH (MoviePy TextClip for subtitles)
- PowerShell (commands below assume PowerShell)

Frontend:

- Node.js 18+ (Next.js 14)
- pnpm 9.x (preferred, see `package.json`), or npm as fallback

Environment variables (create a `.env` in project root):

- `GROQ_API_KEY` – LLM for script/prompt generation (scripts/llm)
- `HF_TOKEN` – T2I auth (Hugging Face Inference/Gradio Client)
- `HF_TOKEN_VIDEO` – I2V auth (Gradio Client)
- Optional runtime knobs:
  - `EDGE_TTS_VOICE` (default voice, e.g. `en-US-AriaNeural`)
  - `WHISPER_MODEL_SIZE` (e.g. `base`, `small`)
  - `WHISPER_LANG` (e.g. `en`)
  - `SUBTITLES_FONT` (default `Segoe UI` on Windows)
  - `VIDEO_GEN_WAIT_SECONDS` (default `10`)
  - `VIDEO_GEN_MAX_RETRIES` (default `5`)

Spaces (defaults in code):

- T2I Space: `end9214/Qwen-Image-Fast` (`images/image_gen.py`)
- I2V Space: `end9214/wan2-2-fp8da-aoti-faster` (`images/image_to_video.py`)

---

## Setup (Backend)

```powershell
# From project root
py -3.11 -m venv .venv
. .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Ensure FFmpeg and ImageMagick are installed and on PATH
# (ImageMagick is required for subtitle burn-in; set IMAGEMAGICK_BINARY if needed)

# Run FastAPI
uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

### API quickstart

1) Create session

```powershell
$body = @{ idea = "A short story about a kid learning to ride a bicycle" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/sessions -ContentType 'application/json' -Body $body
```

2) Generate scripts

```powershell
$body = @{ session_id = "<SESSION_ID>" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/scripts -ContentType 'application/json' -Body $body
```

3) Run pipeline (videos or images mode)

```powershell
$body = @{ script_key = "script1"; voice = "en-US-AriaNeural"; mode = "videos" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/sessions/<SESSION_ID>/run -ContentType 'application/json' -Body $body
```

4) Poll status and download results

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8000/api/sessions/<SESSION_ID>
Invoke-WebRequest -Uri http://localhost:8000/api/sessions/<SESSION_ID>/download/final -OutFile final.mp4
Invoke-WebRequest -Uri http://localhost:8000/api/sessions/<SESSION_ID>/download/subtitled -OutFile final_subtitled.mp4
```

---

## Setup (Frontend)

```powershell
cd frontend
# Preferred
pnpm install
pnpm dev

# Or with npm
npm install
npm run dev
```

The frontend expects the backend at `http://localhost:8000`. Adjust fetch URLs in `frontend/lib/api.ts` if needed.

---

## API Reference (from `api/server.py`)

- `POST /api/sessions` → { session_id }
- `POST /api/scripts` → { session_id, scripts, ordered_keys }
- `POST /api/sessions/{session_id}/run` (body: { script_key, voice?, mode? })
- `GET /api/sessions` → { sessions: [] }
- `GET /api/sessions/{session_id}` → status, progress, `segments_info`, `artifacts_urls`
- `GET /api/sessions/{session_id}/download/{final|subtitled}` → MP4
- `GET /api/sessions/{session_id}/artifact/{relpath}` → any artifact under the session
- `GET /api/voices[?flat=true]` → voices mapping or flat list

Artifacts (per session):

```
sessions/<id>/
  idea.txt
  scripts.json
  status.json
  segments/seg_XX/
    segment.txt
    audio.mp3
    image1.png
    image2.png
    vid1.mp4
    vid2.mp4
    seg_XX.mp4
  final_output.mp4
  final_output_subtitled.mp4
```

---

## Configuration Notes

- T2I (Qwen-Image Fast): 1024×1024, ≤8 steps typical; optional prompt enhancement (Space controlled)
- I2V (Wan 2.2, quantized + AOTI): 6–8 steps typical; clip duration passed from backend
- Mode `videos` uses I2V per image; mode `images` builds a slideshow with zoom/pan
- If HF inference fails for T2I, the backend falls back to the local generator

---

## Troubleshooting

- ImageMagick not found
  - Install ImageMagick and ensure `magick` is on PATH, or set `IMAGEMAGICK_BINARY` to the full path.
- FFmpeg not found
  - Install FFmpeg (e.g., via Chocolatey) and ensure it’s on PATH.
- Space timeouts / queue delays
  - Increase `VIDEO_GEN_MAX_RETRIES`, adjust `VIDEO_GEN_WAIT_SECONDS`, or switch to `mode="images"` as a fallback.
- Voices listing fails
  - Ensure `voicegeneration/voices.json` exists and is valid; use `/api/voices?flat=true` for a flat list.
- Missing tokens
  - Set `HF_TOKEN`, `HF_TOKEN_VIDEO`, and (if used) `GROQ_API_KEY` in `.env`.

---


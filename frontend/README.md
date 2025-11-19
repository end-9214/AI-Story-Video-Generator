# AI Story Video Generator – Frontend

This is a Next.js (App Router, TypeScript) frontend for the FastAPI backend in `api/server.py`.

## Prerequisites

- Node 18+
- pnpm 9+
- Backend running (see project root README). Default API base: `http://localhost:8000`.

## Setup

```powershell
cd frontend
copy .env.example .env.local
# optional: edit NEXT_PUBLIC_API_BASE_URL if backend is not localhost:8000
pnpm install
pnpm dev
```

Open http://localhost:3000.

## What you can do

1) Create a session from your idea.
2) Generate 4 candidate scripts and pick one.
3) Choose voice and mode (videos/images), start generation.
4) Watch progress and download results when completed.

## Notes

- CORS is open by default in the backend. If you deploy, restrict `allow_origins` as needed.
- For downloads, the app links directly to the backend file URLs.

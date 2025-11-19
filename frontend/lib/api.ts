export type ScriptsResponse = {
  session_id: string
  scripts: Record<string, Record<string, string> | string>
  ordered_keys: string[]
}

export type SessionStatus = {
  session_id?: string
  idea?: string
  state?: 'created' | 'queued' | 'running' | 'completed' | 'failed'
  current_segment?: string
  selected_script?: string
  voice?: string
  mode?: 'videos' | 'images'
  progress?: { total_segments: number; completed: number }
  artifacts?: {
    final?: string
    subtitled?: string
    segments?: string[]
  }
  artifacts_urls?: { final?: string; subtitled?: string }
  segments_info?: Record<string, { images: string[]; videos: string[]; audios: string[] }>
  error?: string | null
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

async function jsonFetch<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options?.headers || {}) },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `Request failed: ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function createSession(idea: string): Promise<{ session_id: string }> {
  return jsonFetch(`${API_BASE}/api/sessions`, {
    method: 'POST',
    body: JSON.stringify({ idea }),
  })
}

export async function generateScripts(session_id: string): Promise<ScriptsResponse> {
  return jsonFetch(`${API_BASE}/api/scripts`, {
    method: 'POST',
    body: JSON.stringify({ session_id }),
  })
}

export async function runSession(
  session_id: string,
  script_key: string,
  voice?: string,
  mode: 'videos' | 'images' = 'videos',
): Promise<{ session_id: string; status_url: string; message: string }> {
  return jsonFetch(`${API_BASE}/api/sessions/${session_id}/run`, {
    method: 'POST',
    body: JSON.stringify({ script_key, voice, mode }),
  })
}

export async function getSession(session_id: string): Promise<SessionStatus> {
  return jsonFetch(`${API_BASE}/api/sessions/${session_id}`)
}

export function downloadUrl(session_id: string, kind: 'final' | 'subtitled') {
  return `${API_BASE}/api/sessions/${session_id}/download/${kind}`
}

export function absoluteUrl(u?: string): string | undefined {
  if (!u) return u
  if (/^https?:\/\//i.test(u)) return u
  return `${API_BASE}${u.startsWith('/') ? '' : '/'}${u}`
}

// Voices
export type VoiceFlat = { name: string; lang: string; region: string; gender: 'Male' | 'Female' }
export type VoicesFlatResponse = { voices: VoiceFlat[] }

export async function getVoicesFlat(): Promise<VoicesFlatResponse> {
  return jsonFetch(`${API_BASE}/api/voices?flat=true`)
}

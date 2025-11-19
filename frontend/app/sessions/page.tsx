'use client'

import useSWR from 'swr'
import { useState } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

async function fetcher(url: string) {
  const res = await fetch(url)
  if (!res.ok) throw new Error('Failed')
  return res.json()
}

export default function SessionsPage() {
  const [q, setQ] = useState('')
  const { data, error, isLoading } = useSWR(`${API_BASE}/api/sessions`, fetcher, { refreshInterval: 5000 })
  const sessions: string[] = data?.sessions || []
  const filtered = q ? sessions.filter(s => s.toLowerCase().includes(q.toLowerCase())) : sessions
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input placeholder="Search sessions..." value={q} onChange={e => setQ(e.target.value)} />
        <span className="text-white/50 text-sm">{isLoading ? 'Loading…' : `${filtered.length} sessions`}</span>
      </div>
      <div className="grid gap-3">
        {filtered.map(id => (
          <a key={id} href={`/sessions/${encodeURIComponent(id)}`} className="card p-4 hover:bg-white/10 transition-colors">
            <div className="font-medium">{id}</div>
            <div className="text-white/60 text-sm">sessions/{id}</div>
          </a>
        ))}
        {filtered.length === 0 && <div className="text-white/60 text-sm">No sessions found.</div>}
      </div>
      {error && <div className="text-red-400 text-sm">Error loading sessions.</div>}
    </div>
  )
}

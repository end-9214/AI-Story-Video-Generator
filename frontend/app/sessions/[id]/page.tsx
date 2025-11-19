'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { getSession, type SessionStatus, absoluteUrl } from '@/lib/api'

export default function SessionDetail({ params }: { params: { id: string } }) {
  const { id } = params
  const [status, setStatus] = useState<SessionStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    async function load() {
      setLoading(true)
      try {
        const s = await getSession(id)
        if (mounted) setStatus(s)
      } catch (e: any) {
        setError(e.message || 'Failed to load session')
      } finally {
        if (mounted) setLoading(false)
      }
    }
    load()
    const iv = setInterval(load, 3000)
    return () => { mounted = false; clearInterval(iv) }
  }, [id])

  if (loading && !status) return <div>Loading session...</div>
  if (error) return <div className="text-red-400">{error}</div>
  if (!status) return <div>No data</div>

  const artifacts = status.artifacts_urls || {}

  return (
    <div className="space-y-6">
      <div className="card p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm text-white/60">Session</div>
            <div className="font-medium">{status.session_id || id}</div>
          </div>
          <div className="text-sm text-white/60">State: <span className="font-medium">{status.state}</span></div>
        </div>
        <div className="mt-3 text-sm text-white/70">Idea: {status.idea}</div>
      </div>

      <div className="card p-4">
        <h3 className="font-semibold mb-3">Final video (subtitled preferred)</h3>
        {artifacts.subtitled ? (
          <video controls src={absoluteUrl(artifacts.subtitled)} className="w-full max-h-[480px] bg-black" />
        ) : artifacts.final ? (
          status.state === 'completed' ? (
            <video controls src={absoluteUrl(artifacts.final)} className="w-full max-h-[480px] bg-black" />
          ) : (
            <div className="text-sm text-white/60">Final video present but subtitled version missing. Session incomplete.</div>
          )
        ) : (
          <div className="text-sm text-white/60">No final video yet. Session is incomplete.</div>
        )}
      </div>

      <div className="card p-4">
        <h3 className="font-semibold mb-3">Segments</h3>
        {Object.keys(status.segments_info || {}).length === 0 && (
          <div className="text-sm text-white/60">No segments available yet.</div>
        )}

        <div className="space-y-4">
          {Object.entries(status.segments_info || {}).map(([seg, info]) => (
            <div key={seg} className="border border-white/6 rounded-md p-3">
              <div className="flex items-center justify-between mb-2">
                <div className="font-medium">{seg}</div>
                <div className="text-sm text-white/60">{status.selected_script}</div>
              </div>

              <div className="grid md:grid-cols-3 gap-3">
                <div>
                  <div className="text-sm text-white/70 mb-1">Images</div>
                  <div className="grid gap-2">
                    {(info as any).images?.map((u: string) => (
                      <img key={u} src={absoluteUrl(u)} alt={u} className="rounded-md border border-white/6 max-h-48 object-contain" />
                    ))}
                    {(!(info as any).images || (info as any).images.length === 0) && <div className="text-sm text-white/60">No images yet</div>}
                  </div>
                </div>

                <div>
                  <div className="text-sm text-white/70 mb-1">Videos</div>
                  <div className="grid gap-2">
                    {(info as any).videos?.map((u: string) => (
                      <video key={u} src={absoluteUrl(u)} controls className="w-full max-h-40 bg-black rounded-md" />
                    ))}
                    {(!(info as any).videos || (info as any).videos.length === 0) && <div className="text-sm text-white/60">No segment videos yet</div>}
                  </div>
                </div>

                <div>
                  <div className="text-sm text-white/70 mb-1">Audio</div>
                  <div className="grid gap-2">
                    {(info as any).audios?.map((u: string) => (
                      <audio key={u} src={absoluteUrl(u)} controls className="w-full" />
                    ))}
                    {(!(info as any).audios || (info as any).audios.length === 0) && <div className="text-sm text-white/60">No audio yet</div>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}

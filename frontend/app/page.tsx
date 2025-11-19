'use client'

import { useEffect, useMemo, useState } from 'react'
import useSWR from 'swr'
import { createSession, generateScripts, runSession, getSession, downloadUrl, type ScriptsResponse, type SessionStatus, getVoicesFlat, type VoiceFlat, absoluteUrl } from '@/lib/api'

export default function HomePage() {
  const [idea, setIdea] = useState('A short story about a kid learning to ride a bicycle with help from dad')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [scriptsRes, setScriptsRes] = useState<ScriptsResponse | null>(null)
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [voice, setVoice] = useState('en-IN-NeerjaNeural')
  const [mode, setMode] = useState<'videos' | 'images'>('videos')
  const [error, setError] = useState<string>('')
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4>(1)

  const { data: status, mutate: refreshStatus } = useSWR<SessionStatus>(
    sessionId && currentStep >= 4 ? `/status/${sessionId}` : null,
    async () => (sessionId ? getSession(sessionId) : ({} as any)),
    { refreshInterval: sessionId && currentStep >= 4 ? 3000 : 0 }
  )

  const { data: voicesData } = useSWR<{ voices: VoiceFlat[] }>(
    currentStep >= 3 ? '/voices' : null,
    async () => getVoicesFlat(),
    { revalidateOnFocus: false }
  )

  useEffect(() => {
    if (!scriptsRes || !scriptsRes.ordered_keys?.length) return
    setSelectedKey(scriptsRes.ordered_keys[0])
  }, [scriptsRes])

  useEffect(() => {
    // Drive step based on known state when navigating or reloading
    if (!sessionId) setCurrentStep(1)
    else if (!scriptsRes) setCurrentStep(2)
  }, [sessionId, scriptsRes])

  async function onCreateSession() {
    setError('')
    try {
      const { session_id } = await createSession(idea)
      setSessionId(session_id)
      // Immediately generate scripts and move to step 2
      const res = await generateScripts(session_id)
      setScriptsRes(res)
      setCurrentStep(2)
    } catch (e: any) {
      setError(e.message || 'Failed creating session')
    }
  }

  async function onGenerateScripts() {
    if (!sessionId) return
    setError('')
    try {
      const res = await generateScripts(sessionId)
      setScriptsRes(res)
      setCurrentStep(2)
    } catch (e: any) {
      setError(e.message || 'Failed generating scripts')
    }
  }

  async function onRun() {
    if (!sessionId || !selectedKey) return
    setError('')
    try {
      await runSession(sessionId, selectedKey, voice, mode)
      setCurrentStep(4)
      refreshStatus()
    } catch (e: any) {
      setError(e.message || 'Failed starting generation')
    }
  }

  function segIndex(key: string) {
    const m = key.match(/(\d+)/)
    return m ? parseInt(m[1], 10) : 999999
  }

  const segmentKeys = useMemo(() => {
    if (scriptsRes && selectedKey && typeof scriptsRes.scripts[selectedKey] === 'object') {
      return Object.keys(scriptsRes.scripts[selectedKey] as Record<string,string>).sort((a,b) => segIndex(a)-segIndex(b))
    }
    if ((status as any)?.segments_info) {
      return Object.keys((status as any).segments_info).sort((a,b) => segIndex(a)-segIndex(b))
    }
    return [] as string[]
  }, [scriptsRes, selectedKey, status])

  return (
    <div className="space-y-8">
      {currentStep === 1 && (
        <section className="min-h-[60vh] flex items-center">
          <div className="w-full card p-8 md:p-12 text-center">
            <h1 className="text-2xl md:text-4xl font-bold mb-4">Describe your story idea</h1>
            <p className="text-white/70 mb-6 max-w-2xl mx-auto">Write a short description. We’ll propose four scripts, then generate images and a narrated video.</p>
            <div className="max-w-2xl mx-auto grid gap-3">
              <textarea
                value={idea}
                onChange={(e) => setIdea(e.target.value)}
                rows={5}
                placeholder="A curious kid learns to ride a bicycle with help from dad in the park…"
              />
              <div className="flex items-center justify-center gap-3">
                <button className="btn btn-primary" onClick={onCreateSession} disabled={!idea.trim()}>Create session</button>
                {sessionId && <span className="text-sm text-white/60">Session: {sessionId}</span>}
              </div>
            </div>
          </div>
        </section>
      )}

      {currentStep === 2 && (
        <section className="card p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold">2) Pick a script</h2>
            <button className="btn btn-ghost" onClick={onGenerateScripts} disabled={!sessionId}>Regenerate scripts</button>
          </div>
          {scriptsRes ? (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {scriptsRes.ordered_keys.map(k => (
                  <button key={k} className={`btn ${selectedKey === k ? 'btn-secondary' : 'btn-ghost'}`} onClick={() => setSelectedKey(k)}>
                    {k}
                  </button>
                ))}
              </div>
              <div className="grid gap-3">
                {selectedKey && typeof scriptsRes.scripts[selectedKey] === 'object' && (
                  <div className="grid gap-2">
                    {Object.entries(scriptsRes.scripts[selectedKey] as Record<string,string>).map(([seg, text]) => (
                      <div key={seg} className="text-sm text-white/80">
                        <span className="text-white/60 mr-2">{seg}:</span>
                        {text}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex justify-end">
                <button className="btn btn-primary" onClick={() => setCurrentStep(3)} disabled={!selectedKey}>Continue</button>
              </div>
            </div>
          ) : (
            <p className="text-sm text-white/60">Generating scripts…</p>
          )}
        </section>
      )}

      {currentStep === 3 && (
        <section className="card p-5">
          <h2 className="text-lg font-semibold mb-4">3) Generation settings</h2>
          <div className="grid md:grid-cols-3 gap-3">
            <div>
              <label className="text-sm text-white/70">Voice</label>
              {voicesData?.voices?.length ? (
                <select value={voice} onChange={(e) => setVoice(e.target.value)}>
                  {Array.from(
                    voicesData.voices.reduce((map, v) => {
                      const key = `${v.lang}-${v.region}-${v.gender}`
                      if (!map.has(key)) map.set(key, [])
                      map.get(key)!.push(v)
                      return map
                    }, new Map<string, VoiceFlat[]>()),
                  ).map(([group, items]) => (
                    <optgroup key={group} label={group}>
                      {items.map((v) => (
                        <option key={v.name} value={v.name}>{v.name}</option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              ) : (
                <input value={voice} onChange={e => setVoice(e.target.value)} placeholder="en-IN-NeerjaNeural" />
              )}
            </div>
            <div>
              <label className="text-sm text-white/70">Mode</label>
              <select value={mode} onChange={e => setMode(e.target.value as any)}>
                <option value="videos">Videos (image → video)</option>
                <option value="images">Images only (zoom slideshow)</option>
              </select>
            </div>
            <div className="flex items-end">
              <button className="btn btn-primary" onClick={onRun} disabled={!sessionId || !selectedKey}>Start generation</button>
            </div>
          </div>
        </section>
      )}

      {currentStep === 4 && (
        <section className="card p-5">
          <h2 className="text-lg font-semibold mb-4">4) Progress</h2>
          {status ? (
            <div className="space-y-2">
              <div className="text-sm">State: <span className="font-medium">{status.state}</span></div>
              {status.progress && (
                <div className="text-sm">Progress: {status.progress.completed} / {status.progress.total_segments}</div>
              )}
              {status.current_segment && <div className="text-sm text-white/70">Current: {status.current_segment}</div>}

              {(status.artifacts_urls?.subtitled || status.artifacts_urls?.final) && (
                <div className="mt-3">
                  <video
                    controls
                    className="w-full max-h-[520px] bg-black rounded-md shadow-xl"
                    src={absoluteUrl(status.artifacts_urls?.subtitled || status.artifacts_urls?.final)}
                  />
                  <div className="text-xs text-white/50 mt-1">{status.artifacts_urls?.subtitled ? 'Subtitled' : 'Final'} preview</div>
                </div>
              )}

              {segmentKeys.length > 0 && (
                <div className="mt-4">
                  <div className="text-sm text-white/70 mb-2">Segments</div>
                  <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
                    {segmentKeys.map((seg) => {
                      const doneCount = status?.progress?.completed ?? 0
                      const cur = status?.current_segment
                      const idx = segIndex(seg)
                      const isDone = idx <= doneCount
                      const isCurrent = cur === seg
                      return (
                        <div key={seg} className={`rounded-md px-3 py-2 border text-xs flex items-center gap-2 transition-colors
                          ${isDone ? 'border-green-500/40 bg-green-500/10 text-green-300' : isCurrent ? 'border-yellow-500/40 bg-yellow-500/10 text-yellow-200' : 'border-white/10 bg-white/5 text-white/70'}`}
                        >
                          {isDone ? (
                            <svg className="w-3.5 h-3.5 text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6L9 17l-5-5"/></svg>
                          ) : isCurrent ? (
                            <span className="inline-block w-3 h-3 rounded-full bg-yellow-400 animate-pulse" />
                          ) : (
                            <span className="inline-block w-3 h-3 rounded-full bg-white/30" />
                          )}
                          <span>{seg}</span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {status.state === 'completed' && sessionId && (
                <div className="flex gap-3 mt-2">
                  <a className="btn btn-secondary" href={downloadUrl(sessionId, 'final')} target="_blank">Download Final</a>
                  <a className="btn btn-secondary" href={downloadUrl(sessionId, 'subtitled')} target="_blank">Download Subtitled</a>
                </div>
              )}
              {status.state === 'failed' && status.error && (
                <div className="text-sm text-red-400">Error: {status.error}</div>
              )}

              {status.state !== 'completed' && status.state !== 'failed' && (
                <div className="mt-3 relative overflow-hidden rounded-md border border-white/10">
                  <div className="px-3 py-2 text-xs text-white/70">Generating your video…</div>
                  <div className="h-1 w-full bg-white/10">
                    <div className="h-1 bg-secondary animate-[shimmer_1.6s_infinite] w-1/3" />
                  </div>
                </div>
              )}

            </div>
          ) : (
            <div className="text-sm text-white/60">Waiting for status…</div>
          )}
        </section>
      )}

      {error && (
        <div className="card p-4 border border-red-500/40 text-red-300">{error}</div>
      )}

      <div className="text-xs text-white/50">
        API: {process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'}
      </div>
    </div>
  )
}

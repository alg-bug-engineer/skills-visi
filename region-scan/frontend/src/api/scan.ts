import type { ColorMode, PilotsResponse, RunDetail, RunSummary, ScanRecord } from '../types/scan'

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${url}`)
  return (await res.json()) as T
}

export function fetchRuns(): Promise<RunSummary[]> {
  return getJson('/api/scan/runs')
}

export function fetchRun(
  runId: string,
  opts: { period?: string; band?: string; metric?: ColorMode } = {},
): Promise<RunDetail> {
  const p = new URLSearchParams()
  if (opts.period) p.set('period', opts.period)
  if (opts.band) p.set('band', opts.band)
  if (opts.metric && opts.metric !== 'band') p.set('metric', opts.metric)
  const qs = p.toString()
  return getJson(`/api/scan/runs/${encodeURIComponent(runId)}${qs ? `?${qs}` : ''}`)
}

export function fetchPilots(runId: string, period?: string): Promise<PilotsResponse> {
  const qs = period ? `?period=${encodeURIComponent(period)}` : ''
  return getJson(`/api/scan/runs/${encodeURIComponent(runId)}/pilots${qs}`)
}

export function fetchIntersection(
  interId: string,
  runId: string,
  period: string,
): Promise<ScanRecord> {
  const p = new URLSearchParams({ run_id: runId, period })
  return getJson(`/api/scan/intersections/${encodeURIComponent(interId)}?${p.toString()}`)
}

export async function triggerScan(periods?: string[]): Promise<void> {
  const res = await fetch('/api/scan/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ periods }),
  })
  if (!res.ok) throw new Error(`scan trigger failed ${res.status}`)
}

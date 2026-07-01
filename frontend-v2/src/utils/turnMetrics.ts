import type { CognitionPayload, TurnMetric } from '../types/map'
import type { EvidenceTurnBreakdown } from '../types/evidence'
import { normalizeDir } from './mapMarkers'
import { turnCodeFromLabel } from './cognitionChannelAdapter'

const TURN_ORDER = ['左', '直', '右', '调']
const DIR_ORDER = ['东', '西', '南', '北', '东北', '东南', '西北', '西南']

export function dirFromTurnLabel(label: string): string {
  const m = label.match(/[东南西北]+/)
  return m ? m[0] : normalizeDir(label.slice(0, 1))
}

export function turnCharFromLabel(label: string): string {
  const m = label.match(/(左|直|右|调)/)
  return m ? m[1] : '直'
}

export function normalizeTurnMetrics(
  rows: Array<EvidenceTurnBreakdown | TurnMetric> | null | undefined,
): TurnMetric[] {
  if (!rows?.length) return []
  return rows.map((row) => {
    const label = row.label || ''
    const dir4 = ('dir4_label' in row && row.dir4_label) || dirFromTurnLabel(label)
    const turn = ('turn' in row && row.turn) || turnCharFromLabel(label)
    return {
      label,
      dir4_label: dir4,
      turn,
      dir8_code: ('dir8_code' in row ? row.dir8_code : null) ?? null,
      turn_dir_no: ('turn_dir_no' in row ? row.turn_dir_no : null) ?? null,
      turn_saturation: row.turn_saturation ?? null,
      green_utilization: row.green_utilization ?? null,
      flow_vph: ('flow_vph' in row ? row.flow_vph : null) ?? null,
      level: 'level' in row ? row.level : undefined,
    }
  })
}

export function resolveTurnMetrics(
  cognition: CognitionPayload | null,
  byTurn?: EvidenceTurnBreakdown[] | null,
): TurnMetric[] {
  if (cognition?.metrics_by_turn?.length) return cognition.metrics_by_turn
  return normalizeTurnMetrics(byTurn)
}

export function turnsForDir(turns: TurnMetric[], dir: string): TurnMetric[] {
  const norm = normalizeDir(dir)
  return turns.filter(
    (t) => normalizeDir(t.dir4_label || dirFromTurnLabel(t.label)) === norm,
  )
}

export function maxTurnSatForDir(turns: TurnMetric[], dir: string): number | null {
  const sats = turnsForDir(turns, dir)
    .map((t) => t.turn_saturation)
    .filter((s): s is number => s != null && Number(s) > 0)
  return sats.length ? Math.max(...sats) : null
}

export function sortTurnMetrics(turns: TurnMetric[]): TurnMetric[] {
  return [...turns].sort((a, b) => {
    const satA = a.turn_saturation ?? -1
    const satB = b.turn_saturation ?? -1
    if (satB !== satA) return satB - satA
    const dirA = DIR_ORDER.indexOf(normalizeDir(a.dir4_label))
    const dirB = DIR_ORDER.indexOf(normalizeDir(b.dir4_label))
    if (dirA !== dirB) return (dirA < 0 ? 99 : dirA) - (dirB < 0 ? 99 : dirB)
    return TURN_ORDER.indexOf(a.turn || '直') - TURN_ORDER.indexOf(b.turn || '直')
  })
}

export function turnCodeForMetric(turn: TurnMetric): string {
  const ch = turn.turn || turnCharFromLabel(turn.label)
  return turnCodeFromLabel(ch)
}

export interface TurnSatLabelSpec {
  dir: string
  turnCode: string
  label: string
  saturation: number
}

export function shortTurnLabel(label: string): string {
  const dir = label.match(/^[东南西北]+/)?.[0] ?? ''
  const turn = label.match(/(左|直|右|调)/)?.[0] ?? ''
  if (dir && turn) return `${dir}·${turn}`
  return label.length > 6 ? `${label.slice(0, 6)}…` : label
}

export function turnSatLabelsFromMetrics(turns: TurnMetric[]): TurnSatLabelSpec[] {
  const specs: TurnSatLabelSpec[] = []
  for (const t of sortTurnMetrics(turns)) {
    if (t.turn_saturation == null) continue
    specs.push({
      dir: normalizeDir(t.dir4_label || dirFromTurnLabel(t.label)),
      turnCode: turnCodeForMetric(t),
      label: t.label,
      saturation: Number(t.turn_saturation),
    })
  }
  return specs
}

export interface TurnFlowLabelSpec {
  dir: string
  turnCode: string
  label: string
  flowVph: number
}

export function formatTurnFlowVph(flow: number): string {
  if (!Number.isFinite(flow) || flow <= 0) return '—'
  if (flow >= 1000) return `${(flow / 1000).toFixed(1)}k`
  return `${Math.round(flow)}`
}

export function turnFlowLabelsFromMetrics(turns: TurnMetric[]): TurnFlowLabelSpec[] {
  const specs: TurnFlowLabelSpec[] = []
  for (const t of sortTurnMetrics(turns)) {
    const flow = t.flow_vph
    if (flow == null || !Number.isFinite(flow) || flow <= 0) continue
    specs.push({
      dir: normalizeDir(t.dir4_label || dirFromTurnLabel(t.label)),
      turnCode: turnCodeForMetric(t),
      label: t.label,
      flowVph: Number(flow),
    })
  }
  return specs
}

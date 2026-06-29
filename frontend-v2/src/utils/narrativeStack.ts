/**
 * 右上角叙事卡 · 运行数据逐项构建（纯函数，便于单测）
 * 顺序：饱和度 → 四向指标 → 失衡 → 干线绿波 → 投诉/常发
 * 数据随 SSE 逐步到达，本函数只把"当前已有"的运行数据整理成可逐项展示的列表。
 */
import type { ProblemEvidence } from '../types/evidence'
import type { RuntimeMetrics } from '../types/presentation'
import type { DataInsight } from '../types/insight'
import { formatSaturation } from './evidencePresentation'
import { THRESHOLDS } from '../constants'

/** 已在运行数据其他条目展示的 HUD 指标，避免重复罗列 */
export const RUNTIME_METRIC_SKIP_LABELS = new Set([
  '饱和度',
  '失衡系数',
  '走廊', // 与「干线绿波」重复
  '延误', // 与「延误指数」重复
])

export type NarrativeRuntimeCategory =
  | 'saturation'
  | 'metrics'
  | 'imbalance'
  | 'corridor'
  | 'complaint'

export interface NarrativeRuntimeItem {
  id: string
  label: string
  value: string
  severity?: 'high' | 'medium' | 'low'
  category: NarrativeRuntimeCategory
}

const CATEGORY_ORDER: NarrativeRuntimeCategory[] = [
  'saturation',
  'metrics',
  'imbalance',
  'corridor',
  'complaint',
]

function saturationSeverity(v: number): 'high' | 'medium' | 'low' {
  if (v >= THRESHOLDS.saturationHigh) return 'high'
  if (v >= 0.65) return 'medium'
  return 'low'
}

function saturationTone(v: number): string {
  if (v >= 0.95) return '过饱和'
  if (v >= THRESHOLDS.saturationHigh) return '偏高'
  if (v >= 0.65) return '中等'
  return '畅通'
}

export function buildNarrativeRuntimeItems(input: {
  runtimeMetrics?: RuntimeMetrics | null
  dataInsight?: DataInsight | null
  evidence?: ProblemEvidence | null
}): NarrativeRuntimeItem[] {
  const items: NarrativeRuntimeItem[] = []
  const seen = new Set<string>()
  const push = (item: NarrativeRuntimeItem) => {
    if (seen.has(item.label)) return
    seen.add(item.label)
    items.push(item)
  }

  const rm = input.runtimeMetrics ?? null
  const insightMetrics = input.dataInsight?.metrics ?? []
  const ev = input.evidence ?? null

  // 1) 饱和度
  const sat =
    rm?.saturation_rate ??
    ev?.metrics?.saturation_rate ??
    (() => {
      const m = insightMetrics.find((x) => x.label === '饱和度')
      const n = m ? Number(m.value) : NaN
      return Number.isNaN(n) ? null : n
    })()
  if (sat != null) {
    push({
      id: 'saturation',
      label: '饱和度',
      value: `${formatSaturation(sat)} · ${saturationTone(sat)}`,
      severity: saturationSeverity(sat),
      category: 'saturation',
    })
  }

  // 2) 四向指标（来自累积的运行数据 DataInsight，排除已在其他条目展示的项）
  for (const m of insightMetrics) {
    if (RUNTIME_METRIC_SKIP_LABELS.has(m.label)) continue
    push({
      id: `metric-${m.label}`,
      label: m.label,
      value: m.value,
      severity: (m.severity as 'high' | 'medium' | 'low' | undefined) ?? undefined,
      category: 'metrics',
    })
  }

  // 3) 失衡
  const imb =
    rm?.imbalance_index ??
    (() => {
      const m = insightMetrics.find((x) => x.label === '失衡系数')
      const n = m ? Number(m.value) : NaN
      return Number.isNaN(n) ? null : n
    })()
  if (imb != null) {
    const high = imb >= THRESHOLDS.imbalanceHigh
    push({
      id: 'imbalance',
      label: '方向失衡',
      value: `${imb.toFixed(2)} · ${high ? '各进口差异大' : '较均衡'}`,
      severity: high ? 'medium' : 'low',
      category: 'imbalance',
    })
  }

  // 4) 干线绿波
  const corridor = ev?.corridor_context
  if (corridor && (corridor.in_corridor || (corridor.corridor_nodes?.length ?? 0) > 0)) {
    const speed = corridor.line_metrics?.[0]?.travel_speed_kmh
    const tone = corridor.green_wave_break_risk
      ? '绿波易断'
      : speed != null
        ? `行程车速 ${Math.round(speed)} km/h`
        : '在干线协调段内'
    push({
      id: 'corridor',
      label: '干线绿波',
      value: corridor.corridor_name ? `${corridor.corridor_name} · ${tone}` : tone,
      severity: corridor.green_wave_break_risk ? 'medium' : 'low',
      category: 'corridor',
    })
  }

  // 5) 投诉 / 常发
  const chronic = ev?.chronic
  if (chronic?.is_chronic && chronic.congested_days != null) {
    const window = chronic.window_days ?? 7
    push({
      id: 'chronic',
      label: '常发拥堵',
      value: `近 ${window} 天有 ${chronic.congested_days} 天偏堵`,
      severity: 'high',
      category: 'complaint',
    })
  }
  const complaintTotal = ev?.external_evidence?.complaint_total
  if (complaintTotal != null && complaintTotal > 0) {
    const top = ev?.external_evidence?.complaints?.[0]
    const detail = top ? ` · ${top.type}${top.count ? ` ${top.count}件` : ''}` : ''
    push({
      id: 'complaint',
      label: '群众投诉',
      value: `共 ${complaintTotal} 件${detail}`,
      severity: complaintTotal >= 5 ? 'high' : 'medium',
      category: 'complaint',
    })
  }

  return items.sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category),
  )
}

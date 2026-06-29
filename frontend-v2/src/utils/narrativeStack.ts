/**
 * 右上角叙事卡 · 运行数据逐项构建（纯函数，便于单测）
 * 顺序：四向指标 → 转向指标 → 失衡 → 常发
 * 左侧面板仅展示数据与证据，不含治理结论（如信号调整秒数）。
 */
import type {
  FlowTimingGovernance,
  ProblemEvidence,
  TurnBalanceSide,
} from '../types/evidence'
import type { RuntimeMetrics } from '../types/presentation'
import type { DataInsight } from '../types/insight'
import { THRESHOLDS } from '../constants'

/** 已在运行数据其他条目展示的 HUD 指标，避免重复罗列 */
export const RUNTIME_METRIC_SKIP_LABELS = new Set([
  '饱和度',
  '失衡系数',
  '走廊',
  '延误',
  '转向极差',
  '节点位置',
  '日计划时段',
  '规则',
  '规则结论',
  '证据链',
  '绿灯利用率',
  '绿信比',
  '信号调整',
])

const RUNTIME_METRIC_SKIP_LABEL_RE = /信号|治理建议|结论|证据链|规则/

/** 左侧面板运行数据：排除结论类 HUD 字段 */
export function shouldSkipRuntimeMetric(label: string, value?: string): boolean {
  const trimmedLabel = label.trim()
  if (RUNTIME_METRIC_SKIP_LABELS.has(trimmedLabel)) return true
  if (RUNTIME_METRIC_SKIP_LABEL_RE.test(trimmedLabel)) return true
  const v = (value ?? '').trim()
  if (/^[增减].*\d+\s*秒/.test(v) || /^[+-]\d+\s*秒/.test(v)) return true
  return false
}

export type NarrativeRuntimeCategory = 'metrics' | 'imbalance' | 'chronic'

export interface NarrativeRuntimeItem {
  id: string
  label: string
  value: string
  severity?: 'high' | 'medium' | 'low'
  category: NarrativeRuntimeCategory
}

const CATEGORY_ORDER: NarrativeRuntimeCategory[] = ['metrics', 'imbalance', 'chronic']

function formatGreenUtil(v: number): string {
  return `${Math.round(v * 100)}%`
}

function formatTurnSatValue(sat: number): string {
  const tone = sat >= 0.95 ? '过饱和' : sat >= THRESHOLDS.saturationHigh ? '偏高' : '可控'
  return `${sat.toFixed(2)} · ${tone}`
}

function saturationSeverity(sat: number): 'high' | 'medium' | 'low' {
  if (sat >= THRESHOLDS.saturationHigh) return 'high'
  if (sat >= 0.65) return 'medium'
  return 'low'
}

function appendTurnSide(
  push: (item: NarrativeRuntimeItem) => void,
  side: TurnBalanceSide | undefined,
  role: 'over' | 'spare',
) {
  if (!side?.label) return
  const sat = side.turn_saturation
  if (sat != null) {
    push({
      id: `turn-${side.label}-sat`,
      label: `${side.label}饱和度`,
      value: formatTurnSatValue(sat),
      severity: saturationSeverity(sat),
      category: 'metrics',
    })
  }
  const gu = side.green_utilization
  if (gu != null) {
    push({
      id: `turn-${side.label}-gu`,
      label: `${side.label}绿灯利用`,
      value: formatGreenUtil(gu),
      severity:
        role === 'over'
          ? gu >= 0.9
            ? 'high'
            : 'medium'
          : gu <= 0.6
            ? 'low'
            : 'medium',
      category: 'metrics',
    })
  }
}

function appendTurnBalanceItems(
  push: (item: NarrativeRuntimeItem) => void,
  governance?: FlowTimingGovernance | null,
) {
  const tb = governance?.primary_diagnosis?.turn_balance
  if (!tb) return
  appendTurnSide(push, tb.over, 'over')
  appendTurnSide(push, tb.spare, 'spare')
}

export function buildNarrativeRuntimeItems(input: {
  runtimeMetrics?: RuntimeMetrics | null
  dataInsight?: DataInsight | null
  evidence?: ProblemEvidence | null
  flowTimingGovernance?: FlowTimingGovernance | null
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

  for (const m of insightMetrics) {
    if (shouldSkipRuntimeMetric(m.label, m.value)) continue
    push({
      id: `metric-${m.label}`,
      label: m.label,
      value: m.value,
      severity: (m.severity as 'high' | 'medium' | 'low' | undefined) ?? undefined,
      category: 'metrics',
    })
  }

  appendTurnBalanceItems(push, input.flowTimingGovernance)

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

  const chronic = ev?.chronic
  if (chronic?.is_chronic && chronic.congested_days != null) {
    const window = chronic.window_days ?? 7
    push({
      id: 'chronic',
      label: '常发拥堵',
      value: `近 ${window} 天有 ${chronic.congested_days} 天偏堵`,
      severity: 'high',
      category: 'chronic',
    })
  }

  return items.sort(
    (a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category),
  )
}

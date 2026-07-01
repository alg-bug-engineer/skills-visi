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
import { formatGreenUtilizationRaw } from './evidencePresentation'
import { normalizeTurnMetrics, sortTurnMetrics } from './turnMetrics'

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
const SHORT_APPROACH_LABEL_RE = /^[东南西北]进口$/
const APPROACH_SAT_LABEL_RE = /^[东南西北]进口饱和度$/

/** 左侧面板运行数据：排除结论类 HUD 字段 */
export function shouldSkipRuntimeMetric(label: string, value?: string): boolean {
  const trimmedLabel = label.trim()
  if (RUNTIME_METRIC_SKIP_LABELS.has(trimmedLabel)) return true
  if (SHORT_APPROACH_LABEL_RE.test(trimmedLabel)) return true
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
  return formatGreenUtilizationRaw(v)
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

function appendAllTurnMetricItems(
  push: (item: NarrativeRuntimeItem) => void,
  evidence?: ProblemEvidence | null,
) {
  const turns = normalizeTurnMetrics(evidence?.by_turn)
  if (!turns.length) return
  for (const turn of sortTurnMetrics(turns)) {
    const sat = turn.turn_saturation
    if (sat != null) {
      push({
        id: `turn-${turn.label}-sat`,
        label: `${turn.label}饱和度`,
        value: formatTurnSatValue(sat),
        severity: saturationSeverity(sat),
        category: 'metrics',
      })
    }
    const gu = turn.green_utilization
    if (gu != null) {
      push({
        id: `turn-${turn.label}-gu`,
        label: `${turn.label}绿灯利用`,
        value: formatGreenUtil(gu),
        severity: gu >= 0.9 ? 'high' : gu <= 0.6 ? 'low' : 'medium',
        category: 'metrics',
      })
    }
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

function hasTurnLevelSaturationSource(
  evidence?: ProblemEvidence | null,
  governance?: FlowTimingGovernance | null,
): boolean {
  const turns = normalizeTurnMetrics(evidence?.by_turn)
  if (turns.some((turn) => turn.turn_saturation != null || turn.green_utilization != null)) {
    return true
  }
  const tb = governance?.primary_diagnosis?.turn_balance
  return Boolean(
    tb?.over?.turn_saturation != null ||
      tb?.over?.green_utilization != null ||
      tb?.spare?.turn_saturation != null ||
      tb?.spare?.green_utilization != null,
  )
}

const APPROACH_DIR_ORDER = ['东', '南', '西', '北'] as const

function appendApproachSaturationItems(
  push: (item: NarrativeRuntimeItem) => void,
  cognition?: { metrics_by_arm?: Array<{ dir4_label?: string; saturation?: number | null; level?: string }> } | null,
) {
  const arms = cognition?.metrics_by_arm ?? []
  if (!arms.length) return
  for (const dir of APPROACH_DIR_ORDER) {
    const arm = arms.find((a) => String(a.dir4_label ?? '').startsWith(dir))
    if (arm?.saturation == null) continue
    const sat = Number(arm.saturation)
    push({
      id: `approach-${dir}-sat`,
      label: `${dir}进口饱和度`,
      value: formatTurnSatValue(sat),
      severity: saturationSeverity(sat),
      category: 'metrics',
    })
  }
}

export function buildNarrativeRuntimeItems(input: {
  runtimeMetrics?: RuntimeMetrics | null
  dataInsight?: DataInsight | null
  evidence?: ProblemEvidence | null
  flowTimingGovernance?: FlowTimingGovernance | null
  cognition?: { metrics_by_arm?: Array<{ dir4_label?: string; saturation?: number | null }> } | null
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
  const turnLevelReady = hasTurnLevelSaturationSource(ev, input.flowTimingGovernance)

  for (const m of insightMetrics) {
    if (turnLevelReady && APPROACH_SAT_LABEL_RE.test(m.label.trim())) continue
    if (shouldSkipRuntimeMetric(m.label, m.value)) continue
    push({
      id: `metric-${m.label}`,
      label: m.label,
      value: m.value,
      severity: (m.severity as 'high' | 'medium' | 'low' | undefined) ?? undefined,
      category: 'metrics',
    })
  }

  if (!hasTurnLevelSaturationSource(ev, input.flowTimingGovernance)) {
    appendApproachSaturationItems(push, input.cognition)
  }

  appendAllTurnMetricItems(push, ev)
  if (!ev?.by_turn?.length) {
    appendTurnBalanceItems(push, input.flowTimingGovernance)
  }

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

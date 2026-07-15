import type { DownstreamDiagnosis } from '@/api/types'

export interface DownstreamCriterion {
  key: string
  label: string
  hit: boolean
}

const CRITERIA_LABELS: Record<string, string> = {
  target_queue_high: '目标进口排队偏高',
  target_saturation_high: '目标进口饱和度偏高',
  target_green_utilization_high: '目标绿灯利用率偏高',
  downstream_queue_high: '下游排队偏高',
  downstream_near_saturation: '下游接近饱和',
  downstream_metrics_unknown: '下游排队/饱和度指标不足',
  add_green_spillback_risk: '加绿存在溢出风险',
}

/** 评判依据：将后端 judgment_criteria 布尔判据映射为可读命中项，展示结论推导过程。 */
export function downstreamCriteria(dd: DownstreamDiagnosis | null | undefined): DownstreamCriterion[] {
  const c = dd?.judgment_criteria
  if (!c || typeof c !== 'object' || Array.isArray(c)) return []
  return Object.entries(CRITERIA_LABELS)
    .filter(([key]) => key in c)
    .map(([key, label]) => ({ key, label, hit: Boolean(c[key]) }))
}

/**
 * 专业化承接结论：依据 judgment_criteria + can_simple_add_green 推导，
 * 禁用「绿灯给了也用不上」等口语/剧本表达。
 */
export function downstreamConclusion(dd: DownstreamDiagnosis | null | undefined): string {
  if (!dd) return '下游承接能力待核验'
  const c = dd.judgment_criteria ?? {}
  if (c.downstream_metrics_unknown || dd.primary_downstream?.capacity?.unknown) {
    return '下游排队/饱和度指标不足，无法判定承接，不得进入典型点线治理'
  }
  const can = dd.can_simple_add_green
  const downstreamTight = Boolean(
    c.downstream_queue_high || c.downstream_near_saturation || c.add_green_spillback_risk,
  )
  if (downstreamTight) return '下游承接不足，不宜简单加绿，需下游联控'
  const capacity = dd.primary_downstream?.capacity
  if (capacity?.can_release && !capacity?.blocked) {
    return can === true
      ? '下游具备承接空间，可小步增加有效绿'
      : '下游具备承接余量，目标进口排队需在本路口处置'
  }
  if (can === true) return '下游具备承接空间，可小步增加有效绿'
  if (c.target_saturation_high && !c.target_green_utilization_high)
    return '本路口绿灯利用不足，需排查出口、渠化或检测，不宜简单加绿'
  if (can === false) return '本路口暂不宜直接加绿，需先核验相位利用与检测质量'
  return '需结合上下游拓扑与连续时序进一步核验'
}

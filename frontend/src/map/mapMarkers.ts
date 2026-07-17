import type { Metrics, RunResponse } from '@/api/types'
import { ratio } from '@/utils/format'

export type HudMetric = { label: string; value: string; severity: 'high' | 'medium' | 'low' }

export type MapMarkerSpec = {
  position: [number, number]
  kind: 'metric' | 'evidence' | 'alert'
  title: string
  value: string
  subtitle?: string
  severity: 'high' | 'medium' | 'low'
}

function sevFromSaturation(sat: number | null | undefined): 'high' | 'medium' | 'low' {
  if (sat == null) return 'low'
  if (sat >= 0.85) return 'high'
  if (sat >= 0.65) return 'medium'
  return 'low'
}

function sevFromQueueRatio(q: number | null | undefined): 'high' | 'medium' | 'low' {
  if (q == null) return 'low'
  if (q >= 0.15) return 'high'
  if (q >= 0.08) return 'medium'
  return 'low'
}

function saturationOf(m: Metrics): number | null | undefined {
  return m.saturation ?? m.saturation_rate
}

export function buildHudMetrics(resp: RunResponse | null): HudMetric[] {
  const m = resp?.phases?.diagnosis?.metrics
  if (!m) return []
  const items: HudMetric[] = []
  const saturation = saturationOf(m)
  if (m.queue_ratio != null) {
    items.push({ label: '排队比', value: ratio(m.queue_ratio), severity: sevFromQueueRatio(m.queue_ratio) })
  }
  if (saturation != null && saturation > 0) {
    // 小数形式（禁百分比），阈值语义色不变
    items.push({ label: '饱和度', value: ratio(saturation), severity: sevFromSaturation(saturation) })
  }
  if (m.green_utilization != null) {
    items.push({
      label: '绿灯利用率',
      value: ratio(m.green_utilization),
      severity: m.green_utilization < 0.5 ? 'medium' : 'low',
    })
  }
  if (typeof m.imbalance_index === 'number') {
    items.push({
      label: '方向失衡',
      value: ratio(m.imbalance_index),
      severity: m.imbalance_index >= 0.3 ? 'medium' : 'low',
    })
  }
  if (m.queue_length_m != null) {
    items.push({ label: '排队长度', value: `${Math.round(m.queue_length_m)}m`, severity: 'low' })
  }
  // 进口道长度＝排队比分母（storage_length_m；queue_ratio = queue_length_m / storage_length_m）
  if (m.storage_length_m != null) {
    items.push({ label: '进口道长度', value: `${Math.round(m.storage_length_m)}m`, severity: 'low' })
  }
  return items
}

export function markerHtml(spec: MapMarkerSpec): string {
  const sevClass = `sev-${spec.severity}`
  return `<div class="map-marker ${sevClass} kind-${spec.kind}">
    <span class="map-marker__badge">${spec.title}</span>
    <span class="map-marker__value">${spec.value}</span>
    ${spec.subtitle ? `<span class="map-marker__sub">${spec.subtitle}</span>` : ''}
  </div>`
}

/** 指标全部锚定真实目标坐标；屏幕像素避让由统一 label layout 完成。 */
export function buildMetricMarkers(
  resp: RunResponse | null,
  center: [number, number] | null,
): MapMarkerSpec[] {
  if (!center || !resp?.phases?.diagnosis?.metrics) return []
  const m = resp.phases.diagnosis.metrics
  const ticket = resp.diagnosis_ticket
  const dir = ticket?.direction ?? '目标方向'
  const markers: MapMarkerSpec[] = []
  const saturation = saturationOf(m)

  if (saturation != null && saturation > 0) {
    markers.push({
      position: center,
      kind: 'metric',
      title: `${dir}向饱和`,
      value: ratio(saturation),
      severity: sevFromSaturation(saturation),
    })
  }
  if (m.queue_ratio != null) {
    markers.push({
      position: center,
      kind: 'evidence',
      title: '排队比',
      value: ratio(m.queue_ratio),
      subtitle: '溢出验证',
      severity: sevFromQueueRatio(m.queue_ratio),
    })
  }

  const overflow = resp.phases.diagnosis.overflow_verification
  if (overflow?.message) {
    markers.push({
      position: center,
      kind: 'alert',
      title: '溢出',
      value: overflow.verified ? '已验证' : '待证',
      subtitle: overflow.message?.slice(0, 12) ?? '',
      severity: overflow.verified ? 'high' : 'medium',
    })
  }

  return markers
}

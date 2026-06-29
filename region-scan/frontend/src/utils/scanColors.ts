import type { ColorMode, MetricKey, ProblemBand, ScanRecord } from '../types/scan'

export const NO_DATA_COLOR = '#5b6472'

/** problem_band 色板：试点首选(配时可解)亮蓝；工程可解暗红；平稳绿；无数据灰。 */
export const BAND_COLORS: Record<ProblemBand, string> = {
  配时可解: '#2f9bff',
  工程可解: '#c0392b',
  无明显问题: '#27ae60',
  数据不足: NO_DATA_COLOR,
}

export function bandColor(band: ProblemBand | string | null | undefined): string {
  if (band && band in BAND_COLORS) return BAND_COLORS[band as ProblemBand]
  return NO_DATA_COLOR
}

/** 饱和度热度：<0.6 畅通绿；0.6–0.8 偏黄；0.8–0.9 橙；≥0.9（过饱和）红；空值灰。 */
export function saturationColor(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_DATA_COLOR
  if (value >= 0.9) return '#c0392b'
  if (value >= 0.8) return '#e67e22'
  if (value >= 0.6) return '#f1c40f'
  return '#27ae60'
}

/** 失衡系数：越高越红。0.3 为诊断阈值。 */
export function unbalanceColor(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_DATA_COLOR
  if (value >= 0.4) return '#c0392b'
  if (value >= 0.3) return '#e67e22'
  if (value >= 0.2) return '#f1c40f'
  return '#27ae60'
}

/** 绿灯利用率：越低越红（浪费越大）。 */
export function greenUtilizationColor(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return NO_DATA_COLOR
  if (value < 0.4) return '#c0392b'
  if (value < 0.6) return '#e67e22'
  if (value < 0.75) return '#f1c40f'
  return '#27ae60'
}

export function metricColor(metric: MetricKey, value: number | null | undefined): string {
  switch (metric) {
    case 'saturation_max':
      return saturationColor(value)
    case 'unbalance_index':
      return unbalanceColor(value)
    case 'green_utilization':
      return greenUtilizationColor(value)
    default:
      return NO_DATA_COLOR
  }
}

/** 统一着色入口：按 band 或某指标给一条记录定色。 */
export function recordColor(record: ScanRecord, mode: ColorMode): string {
  if (!record.has_data) return NO_DATA_COLOR
  if (mode === 'band') return bandColor(record.problem_band)
  return metricColor(mode, record.metrics?.[mode])
}

export interface LegendItem {
  label: string
  color: string
}

export function legendFor(mode: ColorMode): LegendItem[] {
  if (mode === 'band') {
    return [
      { label: '配时可解（试点首选）', color: BAND_COLORS['配时可解'] },
      { label: '工程可解（配时无效）', color: BAND_COLORS['工程可解'] },
      { label: '无明显问题', color: BAND_COLORS['无明显问题'] },
      { label: '数据不足', color: BAND_COLORS['数据不足'] },
    ]
  }
  if (mode === 'green_utilization') {
    return [
      { label: '低（浪费大）', color: '#c0392b' },
      { label: '偏低', color: '#e67e22' },
      { label: '中', color: '#f1c40f' },
      { label: '高', color: '#27ae60' },
      { label: '无数据', color: NO_DATA_COLOR },
    ]
  }
  return [
    { label: '高', color: '#c0392b' },
    { label: '偏高', color: '#e67e22' },
    { label: '中', color: '#f1c40f' },
    { label: '低', color: '#27ae60' },
    { label: '无数据', color: NO_DATA_COLOR },
  ]
}

export const METRIC_LABELS: Record<ColorMode, string> = {
  band: '问题分层',
  saturation_max: '饱和度',
  unbalance_index: '失衡系数',
  green_utilization: '绿灯利用率',
}

/** 过饱和判断：用于「工程可解 / 配时无效」标注。 */
export function isOversaturated(record: ScanRecord, threshold = 0.9): boolean {
  const sat = record.metrics?.saturation_max
  return sat !== null && sat !== undefined && sat >= threshold
}

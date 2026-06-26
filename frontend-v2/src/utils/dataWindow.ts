import type { DataWindowMeta } from '../types/api'

const SOURCE_LABELS: Record<string, string> = {
  dwd_rolling_7d: 'DWD 近7日明细',
  dws_weekday_pattern: 'DWS 周模式（降级）',
  mock: 'Mock 数据',
  none: '无数据',
}

const FALLBACK_LABELS: Record<string, string> = {
  dwd_empty_rolling_7d: '近7日无明细，已按提问日星期降级',
}

const DOW_LABELS = ['', '一', '二', '三', '四', '五', '六', '日']

function formatDows(dows: number[]): string {
  return dows.map((d) => `周${DOW_LABELS[d] ?? d}`).join('、')
}

export function formatDataWindowSummary(dw: DataWindowMeta): string {
  const source = SOURCE_LABELS[dw.source_tier ?? ''] ?? dw.source_tier ?? '未知来源'
  const activeDows = dw.dws_dow_filter?.length ? dw.dws_dow_filter : dw.dow_filter ?? []
  const dowText = formatDows(activeDows)
  const samples = dw.sample_count != null ? `，样本 ${dw.sample_count} 条` : ''
  const fallback = dw.fallback_reason
    ? ` · ${FALLBACK_LABELS[dw.fallback_reason] ?? dw.fallback_reason}`
    : ''
  return (
    `${dw.date_from} ~ ${dw.date_to} · 每日 ${dw.time_slot ?? ''}` +
    `（${dw.time_label ?? ''}）· ${dowText || '按日历'} · ${source}${samples}${fallback}`
  )
}

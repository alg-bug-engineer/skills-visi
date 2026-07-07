export function isNum(x: unknown): x is number {
  return typeof x === 'number' && Number.isFinite(x)
}

/** 百分比：0.5741 → "57.4%"；空值 → "—" */
export function pct(x: number | null | undefined, digits = 1): string {
  return isNum(x) ? `${(x * 100).toFixed(digits)}%` : '—'
}

/** 比值：1.0873 → "1.09"；空值 → "—" */
export function ratio(x: number | null | undefined, digits = 2): string {
  return isNum(x) ? x.toFixed(digits) : '—'
}

/** 米 */
export function meters(x: number | null | undefined, digits = 0): string {
  return isNum(x) ? `${x.toFixed(digits)}m` : '—'
}

/** 秒 */
export function seconds(x: number | null | undefined): string {
  return isNum(x) ? `${x}s` : '—'
}

export function num(x: number | null | undefined, digits = 0): string {
  return isNum(x) ? x.toFixed(digits) : '—'
}

/** 排队比 / 饱和度阈值 → 语义色 token 名 */
export function ratioTone(x: number | null | undefined): 'alarm' | 'evidence' | 'primary' | 'mute' {
  if (!isNum(x)) return 'mute'
  if (x >= 1.0) return 'alarm'
  if (x >= 0.8) return 'evidence'
  return 'primary'
}

/** 车道排队比 → 颜色（渠化小窗） */
export function laneTone(x: number | null | undefined): 'alarm' | 'evidence' | 'protected' | 'mute' {
  if (!isNum(x)) return 'mute'
  if (x >= 0.9) return 'alarm'
  if (x >= 0.6) return 'evidence'
  return 'protected'
}

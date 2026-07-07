import { isNum } from './format'

/**
 * 供需比 V/C = demand / supply。
 * 后端当前未透出 supply/demand 强度（附录 B）——字段缺失一律返回 null，
 * 由 UI 显示「数据暂缺」，禁止编造（rule 14 / F-11）。
 */
export function deriveVC(demand: unknown, supply: unknown): number | null {
  if (!isNum(demand) || !isNum(supply) || supply === 0) return null
  return demand / supply
}

/** V/C → HSL 颜色（绿→黄→红），仅当有值。 */
export function vcColor(vc: number | null): string | null {
  if (vc == null) return null
  if (vc <= 0.7) return 'hsl(140, 70%, 42%)'
  if (vc < 0.9) return `hsl(${Math.round(140 - (vc - 0.7) / 0.2 * 95)}, 74%, 46%)`
  if (vc < 1.0) return 'hsl(45, 80%, 50%)'
  return 'hsl(0, 72%, 52%)'
}

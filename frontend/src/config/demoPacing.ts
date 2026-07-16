/**
 * 演示节奏配置：集中管理打字速度与幕间停留，便于汇报现场调节。
 * 全部可经 Vite 环境变量覆盖；幕间停留默认 0（无额外暂停）。
 */

function envNum(value: unknown, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) && n >= 0 ? n : fallback
}

/** 打字机每字间隔（ms）。 */
export const DEMO_TYPING_MS = envNum(import.meta.env.VITE_DEMO_TYPING_MS, 28)

/** 第一幕打字完成后的停留（ms），默认 0。 */
export const DEMO_ACT_DWELL_FIRST_MS = envNum(import.meta.env.VITE_DEMO_ACT_DWELL_FIRST_MS, 0)

/** 第二幕及之后每幕停留（ms），默认 0。 */
export const DEMO_ACT_DWELL_AFTER_MS = envNum(import.meta.env.VITE_DEMO_ACT_DWELL_AFTER_MS, 0)

/**
 * 地图动作重点幕的额外停留（ms），默认 0。
 * 需要时可通过环境变量打开，避免证据核验 / 归因分析镜头一闪而过。
 */
export const DEMO_ACT_DWELL_MAP_EXTRA_MS = envNum(import.meta.env.VITE_DEMO_ACT_DWELL_MAP_EXTRA_MS, 0)

/** 需要额外地图观察时间的处置幕 id。 */
const MAP_HEAVY_ACT_IDS = new Set(['act3_overflow', 'act4_attribution'])

/**
 * 某一幕打字完成到自动推进下一幕的停留时长。
 * - instant（测试 / prefers-reduced-motion / webdriver）返回 0，保持确定性与即时完成。
 * - 默认无额外暂停；可通过 VITE_DEMO_ACT_DWELL_* 环境变量按需调节。
 * - 证据核验、归因分析在基础停留上再加 MAP_EXTRA（默认亦为 0）。
 */
export function actDwellMs(
  actIndex: number,
  instant: boolean,
  actId?: string | null,
): number {
  if (instant) return 0
  const base = actIndex <= 0 ? DEMO_ACT_DWELL_FIRST_MS : DEMO_ACT_DWELL_AFTER_MS
  const extra = actId && MAP_HEAVY_ACT_IDS.has(actId) ? DEMO_ACT_DWELL_MAP_EXTRA_MS : 0
  return base + extra
}

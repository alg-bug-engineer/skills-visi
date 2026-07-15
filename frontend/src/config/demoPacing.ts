/**
 * 演示节奏配置（需求17-R1）：集中管理打字速度与幕间停留，便于汇报现场调节。
 * 全部可经 Vite 环境变量覆盖；缺省值面向大屏领导演示（比原 18ms/750ms 更从容）。
 */

function envNum(value: unknown, fallback: number): number {
  const n = Number(value)
  return Number.isFinite(n) && n >= 0 ? n : fallback
}

/** 打字机每字间隔（ms）。 */
export const DEMO_TYPING_MS = envNum(import.meta.env.VITE_DEMO_TYPING_MS, 28)

/** 第一幕打字完成后的停留（ms）——第一步已被后端等待掩盖，无需过长。 */
export const DEMO_ACT_DWELL_FIRST_MS = envNum(import.meta.env.VITE_DEMO_ACT_DWELL_FIRST_MS, 750)

/** 第二幕及之后每幕停留（ms）——给证据卡足够阅读时间，避免“刷过去”。 */
export const DEMO_ACT_DWELL_AFTER_MS = envNum(import.meta.env.VITE_DEMO_ACT_DWELL_AFTER_MS, 2000)

/**
 * 地图动作重点幕的额外停留（ms）。
 * 旁白缩短后，证据核验 / 归因分析等镜头切换仍需可读时间。
 */
export const DEMO_ACT_DWELL_MAP_EXTRA_MS = envNum(import.meta.env.VITE_DEMO_ACT_DWELL_MAP_EXTRA_MS, 2000)

/** 需要额外地图观察时间的处置幕 id。 */
const MAP_HEAVY_ACT_IDS = new Set(['act3_overflow', 'act4_attribution'])

/**
 * 某一幕打字完成到自动推进下一幕的停留时长。
 * - instant（测试 / prefers-reduced-motion / webdriver）返回 0，保持确定性与即时完成。
 * - 第一幕（index 0）用较短停留；第二幕起用较长停留。
 * - 证据核验、归因分析在基础停留上再加 2s，避免地图镜头一闪而过。
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

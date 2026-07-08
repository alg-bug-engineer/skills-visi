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
 * 某一幕打字完成到自动推进下一幕的停留时长。
 * - instant（测试 / prefers-reduced-motion / webdriver）返回 0，保持确定性与即时完成。
 * - 第一幕（index 0）用较短停留；第二幕起用较长停留。
 */
export function actDwellMs(actIndex: number, instant: boolean): number {
  if (instant) return 0
  return actIndex <= 0 ? DEMO_ACT_DWELL_FIRST_MS : DEMO_ACT_DWELL_AFTER_MS
}

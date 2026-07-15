/**
 * 处置闭环固定旁白（尽量精简，避免与动态字段互相矛盾）。
 * 数值结论一律由 useTimeline 从 RunResponse 动态拼接。
 */

export const ACT_DOMAIN_INTRO: Record<string, string[]> = {
  act5_bottleneck: ['单点加绿前须判别下游承接能力'],
  act8_strategy: ['策略须与决策契约一致，并识别红线'],
  // act9 不再放固定方法论，避免打字过长
}

export function domainIntroFor(actId: string): string[] {
  return ACT_DOMAIN_INTRO[actId] ?? []
}

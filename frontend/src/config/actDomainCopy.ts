/**
 * 处置闭环各步骤领域讲解（固定专业口径，旁白与语音共用）。
 * 动态数值仍来自 RunResponse，此处仅承载方法论与判据说明。
 */

export const ACT_DOMAIN_INTRO: Record<string, string[]> = {
  act3_overflow: [
    '依据信控诊断口径，先核验进口道是否出现排队溢出',
    '饱和度反映需求与通行能力匹配程度；绿灯利用率反映有效绿是否被车辆充分占用',
  ],
  act4_bottleneck: [
    '单点加绿前须判别下游承接能力',
    '若下游接近饱和或存在回溢风险，应优先采取下游保护或干线联控，不宜简单拉长绿灯。',
  ],
  act5_corridor: [
    '将诊断从单点扩展到干线，追溯上下游',
    '用于判断瓶颈在本地进口、相邻节点还是干线级协调失效。',
  ],
  act6_cause: [
    '成因归因采用「实时指标—历史案例—专家经验」三联校验。',
    '避免仅凭单点指标误判',
  ],
  act7_strategy: [
    '治理策略须在干线联控框架下制定',
    '同时识别硬约束红线，防止策略越界引发次生拥堵。',
  ],
  act8_plan: [
    '配时方案将策略参数化为可执行相位方案',
    '生成后逐项通过护栏校验，确保可下发。',
  ],
}

export function domainIntroFor(actId: string): string[] {
  return ACT_DOMAIN_INTRO[actId] ?? []
}

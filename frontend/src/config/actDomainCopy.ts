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

/** 语音模板中的固定方法说明（与旁白 intro 语义对齐，适合 TTS 连读）。 */
export const ACT_VOICE_METHOD: Record<string, string> = {
  act3_overflow:
    '先查排队比是否突破阈值，再结合饱和度与绿灯利用率判断溢出性质与严重程度。',
  act4_bottleneck:
    '对比本路口与下游节点的排队、饱和度与服务水平，并评估剩余蓄车空间与加绿回溢风险。',
  act5_corridor:
    '沿干线追溯上下游转向流量占比，识别主要来车方向与潜在瓶颈节点。',
  act6_cause:
    '将指标异常与案例库匹配，按成因维度排序并确认主因与辅因。',
  act7_strategy:
    '在策略包中明确控制边界、协调对象与优先保护下游等治理原则。',
  act8_plan:
    '将推荐策略映射为配时参数，并完成最小绿、周期与协调护栏校验。',
}

export function domainIntroFor(actId: string): string[] {
  return ACT_DOMAIN_INTRO[actId] ?? []
}

export function voiceMethodFor(actId: string): string {
  return ACT_VOICE_METHOD[actId] ?? ''
}

/** Fixed guide phrases for pipeline steps. */

export const VOICE_GUIDE = {
  understand: '已理解您描述的路口问题，开始分析。',
  intersection: (name: string) => `已匹配到路口${name}。`,
  cognition: '正在查看路口渠化，请关注地图进口高亮。',
  dataFetch: '开始分析运行数据，重点看饱和度和失衡。',
  evidenceIntro: '进入问题验证，请留意左侧证据卡。',
  ruleIntro: '进入规则诊断，核对业务规则命中情况。',
  suggestionConfirm: '诊断成立，请查看治理建议。',
  absorptionStart: '开始吸收本次诊断经验。',
  absorptionDone: '经验吸收与技能写入完成。',
  skillBuildStart: '开始固化路口技能包。',
  skillBuildDone: '技能包已生成。',
} as const

export function voiceSaturation(saturation: number, state: string): string {
  const pct = Math.round(saturation * 100)
  return `整体饱和度百分之${pct}，${state}。`
}

export function voiceImbalance(imbalance: number, uneven: boolean): string {
  const pct = Math.round(imbalance * 100)
  const tail = uneven ? '各进口差异明显' : '各向相对均衡'
  return `失衡系数百分之${pct}，${tail}。`
}

export function voiceSuggestion(direction: string | undefined, delta: number | undefined): string {
  if (delta == null) return '已生成治理建议，请查看右侧说明。'
  const verb = direction === 'increase' ? '增加' : '减少'
  return `建议${verb}主要方向绿灯约 ${Math.abs(delta)} 秒。`
}

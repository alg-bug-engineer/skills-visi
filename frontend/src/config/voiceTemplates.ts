/**
 * 处置闭环各步骤语音播报模板（固定步骤名 + 目的 + 方法，不含结论）。
 * 方法槽位由 voiceSlotFillers 依据 actDomainCopy 填充。
 */

export interface VoiceTemplateDef {
  /** 步骤简称，播报开头 */
  stepTitle: string
  /** 本步目的（固定文案） */
  purpose: string
  /** 方法说明模板，{method} 占位或固定文本 */
  methodTemplate: string
}

/** 九幕逐步触发模板，键对齐 ActDef.id */
export const VOICE_TEMPLATES: Record<string, VoiceTemplateDef> = {
  act1_ticket: {
    stepTitle: '诊断对象识别',
    purpose: '形成诊断工单。',
    methodTemplate: '',
  },
  act2_locate: {
    stepTitle: '诊断对象定位',
    purpose: '将问题落到真实路网空间对象',
    methodTemplate: '',
  },
  act3_overflow: {
    stepTitle: '溢出证据核验',
    purpose: '依据排队比、饱和度与绿灯利用率，核验进口道问题。',
    methodTemplate: '{method}',
  },
  act4_bottleneck: {
    stepTitle: '下游承接能力判别',
    purpose: '评估相邻下游信控节点能否承接本路口额外放行，避免加绿引发回溢。',
    methodTemplate: '{method}',
  },
  act5_corridor: {
    stepTitle: '上下游流向溯源',
    purpose: '沿干线追溯上下游转向流量占比，判断瓶颈位于单点还是干线级。',
    methodTemplate: '{method}',
  },
  act6_cause: {
    stepTitle: '成因归因与案例校验',
    purpose: '结合实时指标异常与历史案例，锁定主因并校验归因可靠性。',
    methodTemplate: '{method}',
  },
  act7_strategy: {
    stepTitle: '治理策略与边界约束',
    purpose: '在干线联控约束下生成治理策略包，明确控制原则与不可突破红线。',
    methodTemplate: '{method}',
  },
  act8_plan: {
    stepTitle: '配时方案生成',
    purpose: '将策略参数化为可执行配时方案，并完成信号护栏校验。',
    methodTemplate: '{method}',
  },
  act9_feedback: {
    stepTitle: '方案确认与经验沉淀',
    purpose: '等待方案确认，并将本次处置结果沉淀为可复用经验。',
    methodTemplate: '记录决策、效果与约束，供后续同类场景检索复用。',
  },
}

/** 将模板中的 {key} 替换为槽位值，未命中槽位保留原文。 */
export function renderVoiceTemplate(template: string, slots: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => slots[key] ?? `{${key}}`)
}

/** 拼接完整播报：步骤名 + 目的 + 方法 + 结论（诊断幕起，结论来自快照）。 */
export function composeVoiceAnnounce(
  def: VoiceTemplateDef,
  slots: Record<string, string>,
  options?: { conclusionOnly?: boolean },
): string {
  const method = renderVoiceTemplate(def.methodTemplate, slots).trim()
  const conclusion = (slots.conclusion ?? '').trim()
  if (options?.conclusionOnly) {
    const parts = [def.stepTitle, conclusion].filter(Boolean)
    return `${parts.join('。')}。`
  }
  const parts = [def.stepTitle, def.purpose.trim(), method, conclusion].filter(Boolean)
  return `${parts.join('。')}。`
}

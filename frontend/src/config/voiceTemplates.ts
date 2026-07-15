/**
 * 语音播报模板加载与合成。
 * 固定文案见同目录 voiceTemplates.json（词槽 {method}、{conclusion} 占位）。
 */
import raw from './voiceTemplates.json'

export type VoiceComposeMode = 'full' | 'conclusionOnly' | 'titleOnly'

export interface VoiceTemplateDef {
  /** 步骤简称，播报开头 */
  stepTitle: string
  /** 本步目的（固定文案） */
  purpose: string
  /** 方法说明模板，{method} 占位或固定文本 */
  methodTemplate: string
  /** 拼接模式，默认 full */
  compose?: VoiceComposeMode
  /** 是否填充并追加运行时结论词槽 {conclusion} */
  useConclusion?: boolean
}

type VoiceTemplatesFile = {
  acts: Record<string, VoiceTemplateDef>
  methods: Record<string, string>
  absorption: {
    guide: { absorptionStart: string; absorptionDone: string }
    stages: Record<string, string>
  }
}

const config = raw as VoiceTemplatesFile

/** 处置闭环逐步触发模板，键对齐 ActDef.id；act10_feedback 故意不配置（不播报）。 */
export const VOICE_TEMPLATES: Record<string, VoiceTemplateDef> = config.acts

/** 各步骤固定方法词槽文案（填入 {method}） */
export const VOICE_METHODS: Record<string, string> = config.methods

export function voiceMethodFor(actId: string): string {
  return VOICE_METHODS[actId] ?? ''
}

export function voiceComposeMode(actId: string): VoiceComposeMode {
  return VOICE_TEMPLATES[actId]?.compose ?? 'full'
}

export function voiceUsesConclusion(actId: string): boolean {
  return VOICE_TEMPLATES[actId]?.useConclusion === true
}

/** 经验吸收阶段固定语音文案 */
export const ABSORPTION_VOICE_GUIDE = config.absorption.guide

/** 吸收阶段 key → 播报文案；无配置的 stage 不播报 */
export const ABSORPTION_STAGE_VOICE: Record<string, string> = config.absorption.stages

/** 将模板中的 {key} 替换为槽位值，未命中槽位保留原文。 */
export function renderVoiceTemplate(template: string, slots: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => slots[key] ?? `{${key}}`)
}

/** 拼接完整播报：步骤名 + 目的 + 方法 + 结论（诊断幕起，结论来自快照）。 */
export function composeVoiceAnnounce(
  def: VoiceTemplateDef,
  slots: Record<string, string>,
  options?: { conclusionOnly?: boolean; titleOnly?: boolean },
): string {
  const titleOnly = options?.titleOnly ?? def.compose === 'titleOnly'
  const conclusionOnly = options?.conclusionOnly ?? def.compose === 'conclusionOnly'

  if (titleOnly) return `${def.stepTitle}。`

  const method = renderVoiceTemplate(def.methodTemplate, slots).trim()
  const conclusion = (slots.conclusion ?? '').trim()

  if (conclusionOnly) {
    const parts = [def.stepTitle, conclusion].filter(Boolean)
    return `${parts.join('。')}。`
  }

  const parts = [def.stepTitle, def.purpose.trim(), method, conclusion].filter(Boolean)
  return `${parts.join('。')}。`
}

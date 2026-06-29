/**
 * 理解过程步骤 index ↔ 语音旁白文案映射。
 * 语音仅在对应步骤首次出现在理解过程面板时播放（见 useUnderstandingProcess.onStepStart）。
 */
import { ANALYSIS_STEP_LABELS, STEP_INDICES } from '../constants'
import { VOICE_GUIDE } from './voiceCueTemplates'
import { voiceGuide } from './voiceConfig'

export interface ProcessStepVoiceContext {
  intersectionName?: string | null
  /** 问题诊断步命中流量溯源（高饱和+上游集中来源）时，播报溯源旁白 */
  flowTraceAvailable?: boolean
}

/** 理解过程步骤 index → 面板标签（用于测试与文档对齐） */
export const PROCESS_STEP_VOICE_MAP: ReadonlyArray<{
  index: number
  label: string
  configKey: string
}> = [
  { index: STEP_INDICES.UNDERSTAND, label: ANALYSIS_STEP_LABELS[0], configKey: 'understand' },
  { index: STEP_INDICES.INTERSECTION, label: ANALYSIS_STEP_LABELS[1], configKey: 'intersection' },
  { index: STEP_INDICES.COGNITION, label: ANALYSIS_STEP_LABELS[2], configKey: 'cognition' },
  { index: STEP_INDICES.DATA_FETCH, label: ANALYSIS_STEP_LABELS[3], configKey: 'dataFetch' },
  { index: STEP_INDICES.PROBLEM_EVIDENCE, label: ANALYSIS_STEP_LABELS[4], configKey: 'evidenceIntro' },
  { index: STEP_INDICES.RULE, label: ANALYSIS_STEP_LABELS[5], configKey: 'ruleIntro' },
  { index: STEP_INDICES.SUGGESTION, label: ANALYSIS_STEP_LABELS[6], configKey: 'suggestionConfirm' },
]

export function processStepPhase(stepIndex: number): string {
  const row = PROCESS_STEP_VOICE_MAP.find((item) => item.index === stepIndex)
  return row?.configKey ?? `step-${stepIndex}`
}

/** 返回该理解步骤应对应播报的旁白；无配置或缺少上下文时返回 null */
export function resolveProcessStepVoice(
  stepIndex: number,
  context: ProcessStepVoiceContext = {},
): string | null {
  switch (stepIndex) {
    case STEP_INDICES.UNDERSTAND:
      return VOICE_GUIDE.understand
    case STEP_INDICES.INTERSECTION:
      return context.intersectionName
        ? VOICE_GUIDE.intersection(context.intersectionName)
        : null
    case STEP_INDICES.COGNITION:
      return null
    case STEP_INDICES.DATA_FETCH:
      return VOICE_GUIDE.dataFetch
    case STEP_INDICES.PROBLEM_EVIDENCE:
      return context.flowTraceAvailable
        ? voiceGuide('flowTrace')
        : VOICE_GUIDE.evidenceIntro
    case STEP_INDICES.RULE:
      return VOICE_GUIDE.ruleIntro
    case STEP_INDICES.SUGGESTION:
      return VOICE_GUIDE.suggestionConfirm
    default:
      return null
  }
}

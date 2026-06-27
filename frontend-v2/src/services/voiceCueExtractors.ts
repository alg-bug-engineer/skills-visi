import type { ProblemEvidence } from '../types/evidence'
import type { VoiceCue } from '../types/voice'
import { STEP_INDICES } from '../constants'
import { VOICE_GUIDE } from './voiceCueTemplates'

function cue(
  id: string,
  stepIndex: number,
  phase: string,
  text: string,
  kind: VoiceCue['kind'] = 'guide',
  priority: VoiceCue['priority'] = 0,
): VoiceCue {
  return { id, stepIndex, phase, kind, text, priority }
}

/** One strongest evidence highlight — not the full panel text. */
export function buildEvidenceVoiceCue(data: Record<string, unknown>): VoiceCue {
  const evidence = data as ProblemEvidence
  const chronic = evidence.chronic
  if (chronic?.is_chronic && chronic.congested_days != null) {
    const window = chronic.window_days ?? 7
    return cue(
      'step:4:evidence:chronic',
      STEP_INDICES.PROBLEM_EVIDENCE,
      'evidence',
      `近 ${window} 天中有 ${chronic.congested_days} 天常发拥堵，印证问题存在。`,
      'highlight',
      1,
    )
  }

  const dow = evidence.dow_pattern
  if (dow?.dow_label) {
    const label = dow.dow_label.replace(/^周/, '')
    const rate =
      dow.hit_rate != null ? `，约 ${Math.round(dow.hit_rate * 100)}% 的周会中招` : ''
    return cue(
      'step:4:evidence:dow',
      STEP_INDICES.PROBLEM_EVIDENCE,
      'evidence',
      `每逢周${label}更容易出现这个问题${rate}。`,
      'highlight',
      1,
    )
  }

  const story = evidence.diagnosis_story?.[0]
  if (story?.title || story?.text) {
    const title = (story.title ?? '').replace(/[：:]\s*$/, '')
    const text = (story.text ?? '').split(/[。；]/)[0] ?? ''
    const combined = [title, text].filter(Boolean).join('，').slice(0, 48)
    return cue(
      'step:4:evidence:story',
      STEP_INDICES.PROBLEM_EVIDENCE,
      'evidence',
      combined || VOICE_GUIDE.evidenceIntro,
      'highlight',
      1,
    )
  }

  const sat = evidence.metrics?.saturation_rate
  if (sat != null && sat >= 0.85) {
    const pct = Math.round(sat * 100)
    return cue(
      'step:4:evidence:sat',
      STEP_INDICES.PROBLEM_EVIDENCE,
      'evidence',
      `整体饱和度百分之${pct}，已过饱和，问题成立。`,
      'highlight',
      1,
    )
  }

  return cue(
    'step:4:evidence:fallback',
    STEP_INDICES.PROBLEM_EVIDENCE,
    'evidence',
    '运行数据与描述基本一致，请查看左侧证据卡。',
    'guide',
    0,
  )
}

export function buildEvidenceIntroCue(): VoiceCue {
  return cue(
    'step:4:evidence:intro',
    STEP_INDICES.PROBLEM_EVIDENCE,
    'evidence',
    VOICE_GUIDE.evidenceIntro,
    'guide',
    0,
  )
}

export function buildSaturationCue(saturation: number | null | undefined): VoiceCue | null {
  if (saturation == null) return null
  let state = '总体可控'
  if (saturation >= 0.85) state = '已达过饱和'
  else if (saturation >= 0.65) state = '处于偏高'
  const pct = Math.round(saturation * 100)
  return cue(
    'step:3:saturation',
    STEP_INDICES.DATA_FETCH,
    'saturation',
    `整体饱和度百分之${pct}，${state}。`,
    'highlight',
    2,
  )
}

export function buildImbalanceCue(
  imbalance: number | null | undefined,
  greenUtil?: number | null,
): VoiceCue | null {
  if (imbalance == null) return null
  const pct = Math.round(imbalance * 100)
  const uneven = imbalance >= 0.3
  const tail = uneven ? '各进口差异明显' : '各向相对均衡'
  let text = `失衡系数百分之${pct}，${tail}。`
  if (greenUtil != null) {
    text = `${text.replace(/。$/, '')}，绿灯利用率百分之${Math.round(greenUtil * 100)}。`
  }
  return cue(
    'step:3:imbalance',
    STEP_INDICES.DATA_FETCH,
    'imbalance',
    text,
    'highlight',
    2,
  )
}

export function buildRuleCue(data: Record<string, unknown>): VoiceCue | null {
  if (!data.diagnosed) return null
  const rules = (data.matched_rules as Array<Record<string, unknown>> | undefined) ?? []
  const first = rules[0]
  if (!first) return null
  const name = String(first.name ?? first.id ?? '规则')
  const conclusion = String(first.conclusion ?? '').split(/[。；\n]/)[0]
  const text = conclusion
    ? `命中${name}，${conclusion.slice(0, 36)}。`
    : `命中${name}，请查看规则诊断结论。`
  return cue('step:5:rule', STEP_INDICES.RULE, 'rule', text, 'highlight', 1)
}

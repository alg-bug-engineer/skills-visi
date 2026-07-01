import type { VoiceCue } from '../types/voice'
import { STEP_INDICES } from '../constants'
import { summarizeNarrationForVoice } from '../utils/voiceTextSummarize'
import {
  imbalanceTailLabel,
  saturationStateLabel,
  voiceGuide,
  voiceGuideForProblem,
  voiceTemplate,
} from './voiceConfig'

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

/** 问题印证步骤仅播引导语，结论留给面板展示。 */
export function buildEvidenceVoiceCue(data: Record<string, unknown>): VoiceCue {
  const problemTypes = data.problem_types as string[] | undefined
  return buildEvidenceIntroCue(problemTypes)
}

export function buildEvidenceIntroCue(problemTypes?: string[]): VoiceCue {
  return cue(
    'step:4:evidence:intro',
    STEP_INDICES.PROBLEM_EVIDENCE,
    'evidence',
    voiceGuideForProblem('evidenceIntro', problemTypes),
    'guide',
    0,
  )
}

export function buildImbalanceCue(imbalance: number | null | undefined): VoiceCue | null {
  if (imbalance == null) return null
  const tail = imbalanceTailLabel(imbalance)
  const text = voiceTemplate('imbalance', { value: imbalance.toFixed(2), tail })
  return cue(
    'step:3:imbalance',
    STEP_INDICES.DATA_FETCH,
    'imbalance',
    text,
    'highlight',
    1,
  )
}

export function buildRuleCue(data: Record<string, unknown>): VoiceCue | null {
  if (!data.diagnosed) return null
  const rules = (data.matched_rules as Array<Record<string, unknown>> | undefined) ?? []
  const first = rules[0]
  if (!first) return null
  const ruleName = String(first.name ?? first.id ?? '规则')
  const conclusion = String(first.conclusion ?? '').split(/[。；\n]/)[0]
  const text = conclusion
    ? voiceTemplate('ruleHit', { ruleName, conclusion: conclusion.slice(0, 36) })
    : voiceTemplate('ruleHitFallback', { ruleName })
  return cue('step:5:rule', STEP_INDICES.RULE, 'rule', text, 'highlight', 1)
}

export interface AxisRoadsPayload {
  speakable?: string | null
  axis_roads?: Record<string, string>
  intersectionName?: string | null
}

const DATA_DEPENDENT_VOICE_RE =
  /饱和度|延误|失衡|过饱和|排队|绿灯利用率|最小绿|不匹配|常发|投诉|绿波|周期约/

function isStructureOnlyVoice(text: string): boolean {
  const body = text.trim()
  if (!body) return false
  return !DATA_DEPENDENT_VOICE_RE.test(body)
}

/** TTS for links/cognition phase with axis road names only (no counts / metrics). */
export function buildCognitionVoiceCue(payload: AxisRoadsPayload): VoiceCue | null {
  const axis = payload.axis_roads ?? {}
  const ew = axis['东西向']
  const ns = axis['南北向']
  let text = payload.speakable?.trim() ?? ''
  if (!text && (ew || ns)) {
    const parts: string[] = []
    if (ew) parts.push(`东西向为${ew}`)
    if (ns) parts.push(`南北向为${ns}`)
    text = parts.length ? `${parts.join('，')}。` : ''
  }
  if (!text || !isStructureOnlyVoice(text)) return null
  return cue('step:2:cognition:roads', STEP_INDICES.COGNITION, 'links', text, 'highlight', 1)
}

export interface DirectionRoleRow {
  group: string
  role: 'focus' | 'protect' | 'neutral'
  saturation?: number | null
}

/** TTS for data-fetch narration beats (corridor / timing / external / traffic / granularity). */
export function buildNarrationPhaseVoiceCue(
  phase: string,
  text: string,
  title?: string | null,
  problemTypes?: string[] | null,
): VoiceCue | null {
  const spoken = summarizeNarrationForVoice(phase, text, title, undefined, problemTypes)
  if (!spoken) return null
  return cue(
    `step:3:narration:${phase}`,
    STEP_INDICES.DATA_FETCH,
    phase,
    spoken,
    'highlight',
    1,
  )
}

export function buildDirectionVoiceCue(roles: DirectionRoleRow[]): VoiceCue | null {
  const focus = roles.find((r) => r.role === 'focus')
  const protect = roles.find((r) => r.role === 'protect')
  const parts: string[] = []
  if (focus?.saturation != null) {
    parts.push(
      voiceTemplate('directionFocus', {
        focusGroup: focus.group,
        value: Number(focus.saturation).toFixed(2),
        state: saturationStateLabel(Number(focus.saturation)),
      }),
    )
  }
  if (protect?.saturation != null) {
    parts.push(
      voiceTemplate('directionProtected', {
        protectGroup: protect.group,
        value: Number(protect.saturation).toFixed(2),
      }),
    )
  }
  if (!parts.length) return null
  return cue(
    'step:3:direction:roles',
    STEP_INDICES.DATA_FETCH,
    'direction',
    parts.join(''),
    'highlight',
    1,
  )
}

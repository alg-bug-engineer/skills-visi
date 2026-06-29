import type { ProblemEvidence } from '../types/evidence'
import type { VoiceCue } from '../types/voice'
import { STEP_INDICES } from '../constants'
import { summarizeNarrationForVoice } from '../utils/voiceTextSummarize'
import {
  imbalanceTailLabel,
  saturationStateLabel,
  voiceConfig,
  voiceGuide,
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
      voiceTemplate('evidenceChronic', { window, days: chronic.congested_days }),
      'highlight',
      1,
    )
  }

  const dow = evidence.dow_pattern
  if (dow?.dow_label) {
    const label = dow.dow_label.replace(/^周/, '')
    const rateSuffix =
      dow.hit_rate != null
        ? voiceTemplate('evidenceDowRateSuffix', { rate: Math.round(dow.hit_rate * 100) })
        : ''
    return cue(
      'step:4:evidence:dow',
      STEP_INDICES.PROBLEM_EVIDENCE,
      'evidence',
      voiceTemplate('evidenceDow', { label, rateSuffix }),
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
      combined || voiceGuide('evidenceIntro'),
      'highlight',
      1,
    )
  }

  return cue(
    'step:4:evidence:fallback',
    STEP_INDICES.PROBLEM_EVIDENCE,
    'evidence',
    voiceConfig.templates.evidenceFallback,
    'guide',
    0,
  )
}

export function buildEvidenceIntroCue(): VoiceCue {
  return cue(
    'step:4:evidence:intro',
    STEP_INDICES.PROBLEM_EVIDENCE,
    'evidence',
    voiceGuide('evidenceIntro'),
    'guide',
    0,
  )
}

export function buildImbalanceCue(
  imbalance: number | null | undefined,
  greenUtil?: number | null,
): VoiceCue | null {
  if (imbalance == null) return null
  const tail = imbalanceTailLabel(imbalance)
  const text =
    greenUtil != null
      ? voiceTemplate('imbalanceWithGreenUtil', {
          value: imbalance.toFixed(2),
          tail,
          greenUtil: Math.round(greenUtil * 100),
        })
      : voiceTemplate('imbalance', { value: imbalance.toFixed(2), tail })
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

/** TTS for links/cognition phase with axis road names. */
export function buildCognitionVoiceCue(payload: AxisRoadsPayload): VoiceCue | null {
  const axis = payload.axis_roads ?? {}
  const ew = axis['东西向']
  const ns = axis['南北向']
  const interName = payload.intersectionName ?? ''
  let text = payload.speakable?.trim() ?? ''
  if (!text && (ew || ns)) {
    text = voiceTemplate('axisRoads', {
      interName: interName || '该路口',
      ewRoad: ew || '—',
      nsRoad: ns || '—',
    })
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
): VoiceCue | null {
  const spoken = summarizeNarrationForVoice(phase, text, title)
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

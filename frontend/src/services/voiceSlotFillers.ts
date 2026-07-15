import type { RunResponse } from '@/api/types'
import type { ActDef } from '@/composables/useTimeline'
import { summaryFor } from '@/composables/useTimeline'
import {
  voiceComposeMode,
  voiceMethodFor,
  voiceUsesConclusion,
} from '@/config/voiceTemplates'
import { translatePlanId } from '@/labels/enums'
import { productCopy } from '@/utils/productCopy'
import { downstreamConclusion } from '@/utils/downstream'
import { meters, ratio } from '@/utils/format'
import { compactTimingSummary } from '@/utils/planPresentation'

const MECHANISM_VOICE: Record<string, string> = {
  discharge_anomaly: '本路口放行过程异常',
  local_release_insufficient: '本路口放行不足',
  downstream_blocked: '下游回堵',
  upstream_arrival_shock: '上游冲击',
  evidence_insufficient: '证据不足，待补盲',
}

export function voiceConclusionOnly(act: ActDef): boolean {
  return voiceComposeMode(act.id) === 'conclusionOnly'
}

export function voiceTitleOnly(act: ActDef): boolean {
  return voiceComposeMode(act.id) === 'titleOnly'
}

/** 禁止 TTS 读出「核心结论」标签，并去掉冗余「结论：」前缀。 */
function sanitizeVoiceConclusion(text: string): string {
  return text.replace(/核心结论/g, '').replace(/^结论[：:]\s*/, '').trim()
}

function mechanismOf(resp: RunResponse | null): string | null {
  const diag = resp?.phases?.diagnosis as { overflow_mechanism?: { primary?: string } } | undefined
  const cause = resp?.phases?.cause as { overflow_mechanism?: { primary?: string } } | undefined
  return diag?.overflow_mechanism?.primary ?? cause?.overflow_mechanism?.primary ?? null
}

/** 归因分析：优先播报溢出机制短句，与打字旁白口径一致。 */
function attributionVoiceConclusion(resp: RunResponse | null): string {
  const mech = mechanismOf(resp)
  if (mech === 'discharge_anomaly') {
    const metrics = resp?.phases?.diagnosis?.metrics
    return `目标进口排队比${ratio(metrics?.queue_ratio)}，绿灯有效利用率${ratio(metrics?.green_utilization)}，下游仍有余量，判断问题集中在本路口放行过程`
  }
  if (mech) return MECHANISM_VOICE[mech] ?? mech
  const cause = resp?.phases?.cause
  const ranked = cause?.cause_ranking?.find((item) => item.role?.includes('主'))?.cause
  const raw = ranked ?? cause?.cause_analysis?.primary_cause ?? ''
  const text = productCopy(raw)
  const short = text.split(/[（(]/)[0]?.trim() ?? text
  return short || '归因分析完成'
}

/** 下游承接：优先 downstream_state，再回退专业承接结论。 */
function bottleneckVoiceConclusion(resp: RunResponse | null): string {
  const diag = resp?.phases?.diagnosis as
    | {
        downstream_state?: { decision?: string; direct_downstream_inter_name?: string }
        downstream_diagnosis?: Parameters<typeof downstreamConclusion>[0]
      }
    | undefined
  const ds = diag?.downstream_state
  const name = ds?.direct_downstream_inter_name || '直接下游'
  if (ds?.decision === 'slack') {
    const storage = diag?.downstream_diagnosis?.primary_downstream?.remaining_storage_m
    const storageText = typeof storage === 'number' ? `，剩余蓄车${meters(storage)}` : ''
    return `${name}当前有承接余量${storageText}，可开展小步增绿试运行`
  }
  if (ds?.decision === 'blocked') {
    return `${name}承接受限，优先下游保护，不宜本路口直接加绿`
  }
  if (ds?.decision === 'unknown') {
    return '下游指标不足，暂不判定承接能力'
  }
  return productCopy(downstreamConclusion(diag?.downstream_diagnosis))
}

/** 案例校验：播报命中与高相似数量，不再夹带主因叙述。 */
function casesVoiceConclusion(resp: RunResponse | null): string {
  const cards = resp?.phases?.cause?.case_cards
  if (!cards || cards.matched_count == null) return '案例校验完成'
  const high = cards.high_similarity_count ?? 0
  return `匹配同类案例 ${cards.matched_count} 个，高度相似 ${high} 个`
}

/** 治理策略：对齐决策契约中的绿灯路径。 */
function strategyVoiceConclusion(resp: RunResponse | null): string {
  const strategy = resp?.phases?.strategy as
    | { decision?: { decision_mode?: string; reason?: string }; strategy?: { principles?: string[] } }
    | undefined
  const mode = strategy?.decision?.decision_mode
  if (mode === 'verify_then_adjust') {
    return productCopy(
      strategy?.decision?.reason || '先验后调：核验通过后再小步增绿，周期尽量不变',
    )
  }
  if (mode === 'incremental_release_trial') {
    const cycles = resp?.plan?.trial_loop?.observation_cycles ?? 5
    return `建议立即下发小步增绿方案，试运行${cycles}个周期，系统同步监测目标进口和下游排队，异常自动回滚`
  }
  if (mode === 'protect_downstream') {
    return '下游保护：本路口保守放行或不增绿'
  }
  return productCopy(strategy?.strategy?.principles?.[0] ?? summaryFor(
    { id: 'act8_strategy' } as ActDef,
    resp,
  ))
}

/** 配时方案：说明当前配时动作（维持现状 / 小步增绿）。 */
function planVoiceConclusion(resp: RunResponse | null): string {
  const plan = resp?.plan
  const planId = plan?.recommendation?.recommended_plan_id ?? plan?.recommended?.plan_id
  const summary = compactTimingSummary(plan?.recommended)
  if (plan?.plan_status === 'trial_ready' && summary) {
    return `试运行配时已经生成，${summary}，下发后运行${plan.trial_loop?.observation_cycles ?? 5}个周期，异常自动回滚`
  }
  if (planId === 'verification_plan') {
    return '当前数据不足，尚未形成可安全下发的配时方案'
  }
  if (planId === 'conditional_incremental_release') {
    return summary ? `小步增绿试运行：${summary}` : '小步增绿试运行方案已经生成'
  }
  if (planId === 'incremental_release') {
    return '目标路口小步释放：增加目标方向有效绿，并监测下游排队比'
  }
  if (planId) return `推荐方案${translatePlanId(planId)}`
  return '方案生成完成'
}

function voiceConclusionFor(act: ActDef, resp: RunResponse | null): string {
  if (act.id === 'act4_attribution') return attributionVoiceConclusion(resp)
  if (act.id === 'act5_bottleneck') return bottleneckVoiceConclusion(resp)
  if (act.id === 'act7_cases') return casesVoiceConclusion(resp)
  if (act.id === 'act8_strategy') return strategyVoiceConclusion(resp)
  if (act.id === 'act9_plan') return planVoiceConclusion(resp)
  return sanitizeVoiceConclusion(summaryFor(act, resp))
}

/** 依据当前步骤填充语音方法槽位与结论槽位。 */
export function voiceSlotsForAct(act: ActDef, resp: RunResponse | null = null): Record<string, string> {
  const slots: Record<string, string> = {}
  if (!voiceConclusionOnly(act)) {
    const method = voiceMethodFor(act.id)
    if (method) slots.method = method
  }
  if (voiceUsesConclusion(act.id) && resp) {
    const conclusion = voiceConclusionFor(act, resp)
    if (conclusion) slots.conclusion = conclusion
  }
  return slots
}

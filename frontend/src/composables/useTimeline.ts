import type { RunResponse } from '@/api/types'
import { directionMovement, t } from '@/labels/enums'
import { pct, ratio, meters } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'
import type { EvidenceStage } from '@/map/sceneEvidencePolicy'

/** 地图场景类型（MapController 消费）。 */
export type MapSceneKind = 'city' | 'intersection' | 'lane' | 'trace' | 'control' | 'corridor'

export interface ActMapScene {
  kind: MapSceneKind
  pitch: number
  zoom?: number
  evidence?: EvidenceStage
}

/** 左侧证据卡组件键。 */
export type CardKey =
  | 'ticket'
  | 'metrics'
  | 'bottleneck'
  | 'corridor'
  | 'cause'
  | 'strategy'
  | 'plan'
  | 'feedback'

/** 公开 phase 名（对齐后端快照 phases 键）。 */
export type PhaseKey = 'intent' | 'diagnosis' | 'cause' | 'strategy' | 'plan'

export interface ActDef {
  index: number
  id: string
  /** 该阶段所需的后端 phase：流式下未就绪则门控等待。 */
  phase: PhaseKey
  pipelineNode: string
  processTitle: string
  reveal: CardKey | null
  scene: ActMapScene
}

/** 静态处置阶段定义（旁白按需由 narrationFor 计算，避免随快照更新重建）。 */
export const ACT_DEFS: ActDef[] = [
  { index: 0, id: 'act1_ticket', phase: 'intent', pipelineNode: '对象识别', processTitle: '诊断对象识别', reveal: 'ticket', scene: { kind: 'city', pitch: 20, zoom: 11, evidence: 'overview' } },
  { index: 1, id: 'act2_locate', phase: 'intent', pipelineNode: '空间定位', processTitle: '路网对象定位', reveal: null, scene: { kind: 'intersection', pitch: 15, zoom: 16, evidence: 'recognition' } },
  // 渠化详情：连贯下钻到 18（车道级）
  { index: 2, id: 'act3_overflow', phase: 'diagnosis', pipelineNode: '溢出验证', processTitle: '溢出证据核验', reveal: 'metrics', scene: { kind: 'lane', pitch: 0, zoom: 18, evidence: 'overflow_validation' } },
  { index: 3, id: 'act4_bottleneck', phase: 'diagnosis', pipelineNode: '下游承接', processTitle: '下游承接能力判别', reveal: 'bottleneck', scene: { kind: 'lane', pitch: 10, zoom: 18, evidence: 'downstream_topology' } },
  // 干线溯源：从 18 平滑抬升到 17（干线级）
  { index: 4, id: 'act5_corridor', phase: 'diagnosis', pipelineNode: '流向溯源', processTitle: '上下游流向溯源', reveal: 'corridor', scene: { kind: 'trace', pitch: 50, zoom: 17, evidence: 'flow_trace' } },
  { index: 5, id: 'act6_cause', phase: 'cause', pipelineNode: '成因归因', processTitle: '成因归因与案例校验', reveal: 'cause', scene: { kind: 'trace', pitch: 50, zoom: 17, evidence: 'flow_trace' } },
  { index: 6, id: 'act7_strategy', phase: 'strategy', pipelineNode: '策略约束', processTitle: '治理策略与边界约束', reveal: 'strategy', scene: { kind: 'control', pitch: 45, zoom: 17, evidence: 'control_scope' } },
  { index: 7, id: 'act8_plan', phase: 'plan', pipelineNode: '方案交付', processTitle: '配时方案生成', reveal: 'plan', scene: { kind: 'lane', pitch: 20, zoom: 18, evidence: 'plan_output' } },
  { index: 8, id: 'act9_feedback', phase: 'plan', pipelineNode: '反馈沉淀', processTitle: '方案确认与经验沉淀', reveal: 'feedback', scene: { kind: 'corridor', pitch: 50, zoom: 17, evidence: 'feedback' } },
]

function lines(...xs: (string | null | undefined | false)[]): string[] {
  return xs
    .filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
    .map((x) => productCopy(x))
}

/** 依据当前响应为某一阶段生成说明（真实字段，缺失降级）。 */
export function narrationFor(act: ActDef, resp: RunResponse | null): string[] {
  const ticket = resp?.diagnosis_ticket
  const intent = resp?.phases?.intent
  const diag = resp?.phases?.diagnosis
  const cause = resp?.phases?.cause
  const strategy = resp?.phases?.strategy
  const plan = resp?.plan

  switch (act.id) {
    case 'act1_ticket':
      return lines(
        '正在解析口头描述，提取实体…',
        `对象：${t('object_type', ticket?.object_type)}｜路口：${ticket?.intersection_name ?? '目标路口'}`,
        `时间：${ticket?.time_range ?? '—'}（${t('period', ticket?.period)}）`,
        `方向转向：${directionMovement(ticket?.direction, ticket?.movement)}｜问题：${t('problem_type', ticket?.problem_type)}`,
        ticket?.constraints?.[0] && `关键约束：${ticket.constraints[0]}`,
      )
    case 'act2_locate':
      return lines(
        '将自然语言落到真实路网…',
        ...(intent?.spatial_scene?.recognition_steps ?? []).map(
          (s) => `${s.status === 'done' ? '✓' : '…'} ${s.label}`,
        ),
        intent?.spatial_scene?.available === false && '拓扑数据不足，转文本兜底展示',
      )
    case 'act3_overflow':
      return lines(
        '拉取关键指标，排队比 = 排队长度 ÷ 进口道可容纳长度…',
        `排队比 ${ratio(diag?.metrics?.queue_ratio)}｜饱和度 ${pct(diag?.metrics?.saturation)}｜绿灯利用率 ${pct(diag?.metrics?.green_utilization)}`,
        diag?.overflow_verification?.message,
      )
    case 'act4_bottleneck':
      return lines(
        '核验下游剩余接纳空间与相邻路口状态…',
        diag?.downstream_diagnosis?.narrative,
        diag?.downstream_diagnosis?.release_answer && `核心判断：${diag.downstream_diagnosis.release_answer}`,
      )
    case 'act5_corridor':
      return lines(
        '把诊断范围从单路口扩大到干线…',
        `上游到达 ${meters(diag?.arterial_analysis?.upstream_arrival_flow_vph)}／放行强度分析中`,
        diag?.arterial_analysis?.summary,
      )
    case 'act6_cause':
      return lines(
        '把实时指标与历史案例放在一起判断…',
        cause?.cause_analysis?.primary_cause && `主因：${cause.cause_analysis.primary_cause}`,
        cause?.case_cards?.matched_count != null &&
          `匹配同类案例 ${cause.case_cards.matched_count} 个，高度相似 ${cause.case_cards.high_similarity_count ?? 0} 个`,
      )
    case 'act7_strategy':
      return lines(
        '将单点放行调整纳入干线联控约束…',
        strategy?.strategy?.principles?.[0] && `原则：${strategy.strategy.principles[0]}`,
        strategy?.strategy?.hard_constraints?.[0] && `红线：${strategy.strategy.hard_constraints[0]}`,
      )
    case 'act8_plan':
      return lines(
        '把策略转成可执行方案，逐项完成安全校验…',
        plan?.recommendation?.recommended_plan_id &&
          `推荐：${t('plan_id', plan.recommendation.recommended_plan_id.split('_').slice(0, 2).join('_'))}`,
        plan?.all_guardrails_passed != null && `安全校验：${plan.all_guardrails_passed ? '全部通过' : '存在告警'}`,
      )
    case 'act9_feedback':
      return lines('记录本次处置结果，形成后续复用依据…', '请确认下发、退回修改或提交再生成。')
    default:
      return []
  }
}

/** 阶段完成后折叠展示的汇总结论。 */
export function summaryFor(act: ActDef, resp: RunResponse | null): string {
  const ticket = resp?.diagnosis_ticket
  const intent = resp?.phases?.intent
  const diag = resp?.phases?.diagnosis
  const cause = resp?.phases?.cause
  const strategy = resp?.phases?.strategy
  const plan = resp?.plan

  switch (act.id) {
    case 'act1_ticket':
      return productCopy(`${ticket?.intersection_name ?? '目标路口'}｜${t('problem_type', ticket?.problem_type)}｜${directionMovement(ticket?.direction, ticket?.movement)}`)
    case 'act2_locate':
      return intent?.spatial_scene?.target?.inter_name
        ? productCopy(`已锁定 ${intent.spatial_scene.target.inter_name}`)
        : '空间定位完成'
    case 'act3_overflow':
      return productCopy(diag?.overflow_verification?.message ?? `排队比 ${ratio(diag?.metrics?.queue_ratio)}，饱和度 ${pct(diag?.metrics?.saturation)}`)
    case 'act4_bottleneck':
      return productCopy(diag?.downstream_diagnosis?.release_answer ?? diag?.downstream_diagnosis?.narrative ?? '瓶颈判断完成')
    case 'act5_corridor':
      return productCopy(diag?.arterial_analysis?.summary ?? '干线溯源完成')
    case 'act6_cause':
      return productCopy(cause?.cause_analysis?.narrative ?? cause?.cause_analysis?.primary_cause ?? '成因判断完成')
    case 'act7_strategy':
      return productCopy(strategy?.strategy?.principles?.[0] ?? '策略推荐完成')
    case 'act8_plan':
      return plan?.recommendation?.recommended_plan_id
        ? `推荐方案 ${t('plan_id', plan.recommendation.recommended_plan_id.split('_').slice(0, 2).join('_'))}`
        : '方案生成完成'
    case 'act9_feedback':
      return '等待方案确认或退回修改'
    default:
      return act.processTitle
  }
}

/** 快照中某 phase 是否已就绪（plan 阶段查 plan 块）。 */
export function phaseReady(resp: RunResponse | null, phase: PhaseKey): boolean {
  if (!resp) return false
  if (phase === 'plan') return resp.plan != null || resp.phases?.plan != null
  return resp.phases?.[phase] != null
}

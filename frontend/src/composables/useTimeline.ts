import type { Metrics, RunResponse } from '@/api/types'
import { directionMovement, t, translatePlanId } from '@/labels/enums'
import { ratio, meters } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'
import { domainIntroFor } from '@/config/actDomainCopy'
import { downstreamConclusion } from '@/utils/downstream'
import {
  ticketDirectionProblemLine,
  ticketLocationLine,
  ticketPrimaryConstraint,
  ticketTimeLabel,
} from '@/utils/ticketCopy'
import type { EvidenceStage } from '@/map/sceneEvidencePolicy'

function saturationOf(metrics: Metrics | undefined): number | null | undefined {
  return metrics?.saturation ?? metrics?.saturation_rate
}

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
  | 'verification'
  | 'governance'
  | 'healthy'

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
  /** 追加证据卡（与 reveal 同门控揭示，不新增幕，避免地图场景重排）。 */
  extraCards?: CardKey[]
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
  { index: 5, id: 'act6_cause', phase: 'cause', pipelineNode: '成因归因', processTitle: '成因归因与案例校验', reveal: 'cause', scene: { kind: 'lane', pitch: 10, zoom: 18, evidence: 'cause_annotation' } },
  // 治理策略：在干线级(17)基础上 +1 放大（需求21-R3），聚焦控制范围
  { index: 6, id: 'act7_strategy', phase: 'strategy', pipelineNode: '策略约束', processTitle: '治理策略与边界约束', reveal: 'governance', scene: { kind: 'control', pitch: 45, zoom: 18, evidence: 'control_scope' } },
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
        ticketLocationLine(ticket),
        `时段：${ticketTimeLabel(ticket)}`,
        ticketDirectionProblemLine(ticket),
        ticketPrimaryConstraint(ticket) && `关键约束：${ticketPrimaryConstraint(ticket)}`,
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
        ...domainIntroFor('act3_overflow'),
        `指标研判：排队比 ${ratio(diag?.metrics?.queue_ratio)}｜饱和度 ${ratio(saturationOf(diag?.metrics))}｜绿灯利用率 ${ratio(diag?.metrics?.green_utilization)}`,
        diag?.healthy
          ? '结论：各项指标均在正常区间，路口运行平稳、无溢出风险，无需干预'
          : diag?.overflow_verification?.message && `结论：${diag.overflow_verification.message}`,
      )
    case 'act4_bottleneck': {
      const dd = diag?.downstream_diagnosis
      const pd = dd?.primary_downstream
      const dm = pd?.metrics
      const tm = diag?.metrics
      const storage = typeof pd?.remaining_storage_m === 'number' && pd.remaining_storage_m > 0
        ? `｜剩余蓄车 ${meters(pd.remaining_storage_m)}`
        : ''
      return lines(
        ...domainIntroFor('act4_bottleneck'),
        tm &&
          `本路口：饱和度 ${ratio(tm.saturation)}｜绿灯利用率 ${ratio(tm.green_utilization)}｜服务水平 ${tm.los ?? '—'}`,
        pd?.inter_name &&
          `下游 ${pd.inter_name}：饱和度 ${ratio(dm?.saturation_rate ?? dm?.saturation)}｜服务水平 ${dm?.level_of_service ?? '—'}${storage}`,
        `结论：${downstreamConclusion(dd)}`,
      )
    }
    case 'act5_corridor':
      return lines(
        ...domainIntroFor('act5_corridor'),
        diag?.arterial_analysis?.upstream_arrival_flow_vph != null &&
          `上游到达流量 ${meters(diag.arterial_analysis.upstream_arrival_flow_vph)}，正在比对放行强度与干线瓶颈位置`,
        diag?.arterial_analysis?.summary && `结论：${diag.arterial_analysis.summary}`,
      )
    case 'act6_cause':
      return lines(
        ...domainIntroFor('act6_cause'),
        cause?.cause_analysis?.primary_cause && `主因：${cause.cause_analysis.primary_cause}`,
        cause?.cause_ranking?.[0]?.cause &&
          cause.cause_ranking[0].cause !== cause?.cause_analysis?.primary_cause &&
          `辅因：${cause.cause_ranking[0].cause}`,
        cause?.case_cards?.matched_count != null &&
          `案例校验：匹配同类案例 ${cause.case_cards.matched_count} 个，高度相似 ${cause.case_cards.high_similarity_count ?? 0} 个`,
      )
    case 'act7_strategy':
      return lines(
        ...domainIntroFor('act7_strategy'),
        strategy?.strategy_package && `策略包：${t('strategy_package', strategy.strategy_package)}`,
        strategy?.strategy?.principles?.[0] && `原则：${strategy.strategy.principles[0]}`,
        strategy?.strategy?.hard_constraints?.[0] && `红线：${strategy.strategy.hard_constraints[0]}`,
        strategy?.strategy?.coordination_scope &&
          `协调范围：${productCopy(strategy.strategy.coordination_scope)}`,
      )
    case 'act8_plan':
      return lines(
        ...domainIntroFor('act8_plan'),
        plan?.recommendation?.recommended_plan_id &&
          `推荐方案：${translatePlanId(plan.recommendation.recommended_plan_id)}`,
        plan?.all_guardrails_passed != null &&
          `护栏校验：${plan.all_guardrails_passed ? '最小绿、周期与协调约束全部通过' : '存在未通过项，需人工复核'}`,
        plan?.recommendation?.rationale && `推荐理由：${plan.recommendation.rationale}`,
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
      if (diag?.healthy) return '运行平稳，无溢出风险，无需干预'
      return productCopy(diag?.overflow_verification?.message ?? `排队比 ${ratio(diag?.metrics?.queue_ratio)}，饱和度 ${ratio(saturationOf(diag?.metrics))}`)
    case 'act4_bottleneck':
      return productCopy(downstreamConclusion(diag?.downstream_diagnosis))
    case 'act5_corridor':
      return productCopy(diag?.arterial_analysis?.summary ?? '干线溯源完成')
    case 'act6_cause':
      return productCopy(cause?.cause_analysis?.primary_cause ?? '成因判断完成')
    case 'act7_strategy':
      return productCopy(strategy?.strategy?.principles?.[0] ?? '策略推荐完成')
    case 'act8_plan':
      return plan?.recommendation?.recommended_plan_id
        ? `推荐方案 ${translatePlanId(plan.recommendation.recommended_plan_id)}`
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

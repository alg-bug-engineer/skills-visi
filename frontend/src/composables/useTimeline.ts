import type { RunResponse } from '@/api/types'
import { directionMovement, t } from '@/labels/enums'
import { pct, ratio, meters } from '@/utils/format'

/** 地图场景类型（MapController 消费）。 */
export type MapSceneKind = 'city' | 'intersection' | 'lane' | 'trace' | 'control' | 'corridor'

export interface ActMapScene {
  kind: MapSceneKind
  pitch: number
  zoom?: number
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
  /** 该幕所需的后端 phase：流式下未就绪则门控等待。 */
  phase: PhaseKey
  pipelineNode: string
  processTitle: string
  reveal: CardKey | null
  scene: ActMapScene
}

/** 静态九幕定义（旁白按需由 narrationFor 计算，避免随快照更新重建）。 */
export const ACT_DEFS: ActDef[] = [
  { index: 0, id: 'act1_ticket', phase: 'intent', pipelineNode: '问题理解', processTitle: '理解问题', reveal: 'ticket', scene: { kind: 'city', pitch: 20, zoom: 11 } },
  { index: 1, id: 'act2_locate', phase: 'intent', pipelineNode: '拓扑定位', processTitle: '空间定位', reveal: null, scene: { kind: 'intersection', pitch: 15, zoom: 16 } },
  { index: 2, id: 'act3_overflow', phase: 'diagnosis', pipelineNode: '溢出验证', processTitle: '指标加载与溢出验证', reveal: 'metrics', scene: { kind: 'lane', pitch: 0, zoom: 17 } },
  { index: 3, id: 'act4_bottleneck', phase: 'diagnosis', pipelineNode: '瓶颈判断', processTitle: '本路口放不出去 vs 下游接不住', reveal: 'bottleneck', scene: { kind: 'lane', pitch: 10, zoom: 16 } },
  { index: 4, id: 'act5_corridor', phase: 'diagnosis', pipelineNode: '干线溯源', processTitle: '流量溯源', reveal: 'corridor', scene: { kind: 'trace', pitch: 50, zoom: 15 } },
  { index: 5, id: 'act6_cause', phase: 'cause', pipelineNode: '成因/案例', processTitle: '成因判断与相似检索', reveal: 'cause', scene: { kind: 'trace', pitch: 50, zoom: 15 } },
  { index: 6, id: 'act7_strategy', phase: 'strategy', pipelineNode: '策略生成', processTitle: '策略推荐', reveal: 'strategy', scene: { kind: 'control', pitch: 45, zoom: 15 } },
  { index: 7, id: 'act8_plan', phase: 'plan', pipelineNode: '方案生成', processTitle: '方案决策', reveal: 'plan', scene: { kind: 'lane', pitch: 20, zoom: 16 } },
  { index: 8, id: 'act9_feedback', phase: 'plan', pipelineNode: '反馈下发', processTitle: '等待方案下发确认', reveal: 'feedback', scene: { kind: 'corridor', pitch: 50, zoom: 14 } },
]

function lines(...xs: (string | null | undefined | false)[]): string[] {
  return xs.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
}

/** 依据当前响应为某一幕生成旁白（真实字段，缺失降级）。 */
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
        '加绿之前，先判断车有没有地方去…',
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
        '从「单点加绿」升级为「干线联控」…',
        strategy?.strategy?.principles?.[0] && `原则：${strategy.strategy.principles[0]}`,
        strategy?.strategy?.not_recommended?.[0] && `不推荐：${strategy.strategy.not_recommended[0]}`,
      )
    case 'act8_plan':
      return lines(
        '把策略转成可执行方案，逐项过护栏…',
        plan?.recommendation?.recommended_plan_id &&
          `推荐：${t('plan_id', plan.recommendation.recommended_plan_id.split('_').slice(0, 2).join('_'))}`,
        plan?.all_guardrails_passed != null && `护栏校验：${plan.all_guardrails_passed ? '全部通过' : '存在告警'}`,
      )
    case 'act9_feedback':
      return lines('一次处置不是结束，而是下一次判断的经验…', '请专家接受 / 拒绝 / 修改后再生成。')
    default:
      return []
  }
}

/** 快照中某 phase 是否已就绪（plan 幕查 plan 块）。 */
export function phaseReady(resp: RunResponse | null, phase: PhaseKey): boolean {
  if (!resp) return false
  if (phase === 'plan') return resp.plan != null || resp.phases?.plan != null
  return resp.phases?.[phase] != null
}

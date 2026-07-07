import type { RunResponse } from '@/api/types'
import { directionMovement, t } from '@/labels/enums'
import { pct, ratio, meters } from '@/utils/format'

/** 地图场景类型（MapController 消费）。 */
export type MapSceneKind =
  | 'city'
  | 'intersection'
  | 'lane'
  | 'trace'
  | 'control'
  | 'corridor'

export interface ActMapScene {
  kind: MapSceneKind
  /** 3D 俯仰角：微观诊断近 2D(0)，干线宏观 3D(45~55)。 */
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

export interface ActDef {
  index: number
  id: string
  /** 底部进度条节点名。 */
  pipelineNode: string
  /** 右侧过程栏标题。 */
  processTitle: string
  /** 打字旁白行（来自真实响应，缺失降级）。 */
  narration: string[]
  /** 打字完成后揭示的证据卡（null=不揭示新卡，如识别步骤本身在过程栏）。 */
  reveal: CardKey | null
  scene: ActMapScene
}

function lines(...xs: (string | null | undefined | false)[]): string[] {
  return xs.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
}

/** 依据一次性响应构建九幕运行时（数据源自真实字段，缺失降级）。 */
export function buildActs(resp: RunResponse): ActDef[] {
  const ticket = resp.diagnosis_ticket
  const intent = resp.phases?.intent
  const diag = resp.phases?.diagnosis
  const cause = resp.phases?.cause
  const strategy = resp.phases?.strategy
  const plan = resp.plan

  const dirMov = directionMovement(ticket?.direction, ticket?.movement)
  const interName = ticket?.intersection_name ?? '目标路口'

  return [
    {
      index: 0,
      id: 'act1_ticket',
      pipelineNode: '问题理解',
      processTitle: '理解问题',
      narration: lines(
        `正在解析口头描述，提取实体…`,
        `对象：${t('object_type', ticket?.object_type)}｜路口：${interName}`,
        `时间：${ticket?.time_range ?? '—'}（${t('period', ticket?.period)}）`,
        `方向转向：${dirMov}｜问题：${t('problem_type', ticket?.problem_type)}`,
        ticket?.constraints?.[0] && `关键约束：${ticket.constraints[0]}`,
      ),
      reveal: 'ticket',
      scene: { kind: 'city', pitch: 20, zoom: 11 },
    },
    {
      index: 1,
      id: 'act2_locate',
      pipelineNode: '拓扑定位',
      processTitle: '空间定位',
      narration: lines(
        `将自然语言落到真实路网…`,
        ...(intent?.spatial_scene?.recognition_steps ?? []).map(
          (s) => `${s.status === 'done' ? '✓' : '…'} ${s.label}`,
        ),
        intent?.spatial_scene?.available === false && '拓扑数据不足，转文本兜底展示',
      ),
      reveal: null,
      scene: { kind: 'intersection', pitch: 15, zoom: 16 },
    },
    {
      index: 2,
      id: 'act3_overflow',
      pipelineNode: '溢出验证',
      processTitle: '指标加载与溢出验证',
      narration: lines(
        `拉取关键指标，排队比 = 排队长度 ÷ 进口道可容纳长度…`,
        `排队比 ${ratio(diag?.metrics?.queue_ratio)}｜饱和度 ${pct(diag?.metrics?.saturation)}｜绿灯利用率 ${pct(diag?.metrics?.green_utilization)}`,
        diag?.overflow_verification?.message,
      ),
      reveal: 'metrics',
      scene: { kind: 'lane', pitch: 0, zoom: 17 },
    },
    {
      index: 3,
      id: 'act4_bottleneck',
      pipelineNode: '瓶颈判断',
      processTitle: '本路口放不出去 vs 下游接不住',
      narration: lines(
        `加绿之前，先判断车有没有地方去…`,
        diag?.downstream_diagnosis?.narrative,
        diag?.downstream_diagnosis?.release_answer && `核心判断：${diag.downstream_diagnosis.release_answer}`,
      ),
      reveal: 'bottleneck',
      scene: { kind: 'lane', pitch: 10, zoom: 16 },
    },
    {
      index: 4,
      id: 'act5_corridor',
      pipelineNode: '干线溯源',
      processTitle: '流量溯源',
      narration: lines(
        `把诊断范围从单路口扩大到干线…`,
        `上游到达 ${meters(diag?.arterial_analysis?.upstream_arrival_flow_vph)}／放行强度分析中`,
        diag?.arterial_analysis?.summary,
      ),
      reveal: 'corridor',
      scene: { kind: 'trace', pitch: 50, zoom: 15 },
    },
    {
      index: 5,
      id: 'act6_cause',
      pipelineNode: '成因/案例',
      processTitle: '成因判断与相似检索',
      narration: lines(
        `把实时指标与历史案例放在一起判断…`,
        cause?.cause_analysis?.primary_cause && `主因：${cause.cause_analysis.primary_cause}`,
        cause?.case_cards?.matched_count != null &&
          `匹配同类案例 ${cause.case_cards.matched_count} 个，高度相似 ${cause.case_cards.high_similarity_count ?? 0} 个`,
      ),
      reveal: 'cause',
      scene: { kind: 'trace', pitch: 50, zoom: 15 },
    },
    {
      index: 6,
      id: 'act7_strategy',
      pipelineNode: '策略生成',
      processTitle: '策略推荐',
      narration: lines(
        `从「单点加绿」升级为「干线联控」…`,
        strategy?.strategy?.principles?.[0] && `原则：${strategy.strategy.principles[0]}`,
        strategy?.strategy?.not_recommended?.[0] && `不推荐：${strategy.strategy.not_recommended[0]}`,
      ),
      reveal: 'strategy',
      scene: { kind: 'control', pitch: 45, zoom: 15 },
    },
    {
      index: 7,
      id: 'act8_plan',
      pipelineNode: '方案生成',
      processTitle: '方案决策',
      narration: lines(
        `把策略转成可执行方案，逐项过护栏…`,
        plan?.recommendation?.recommended_plan_id &&
          `推荐：${t('plan_id', plan.recommendation.recommended_plan_id.split('_').slice(0, 2).join('_'))}`,
        plan?.all_guardrails_passed != null && `护栏校验：${plan.all_guardrails_passed ? '全部通过' : '存在告警'}`,
      ),
      reveal: 'plan',
      scene: { kind: 'lane', pitch: 20, zoom: 16 },
    },
    {
      index: 8,
      id: 'act9_feedback',
      pipelineNode: '反馈下发',
      processTitle: '等待方案下发确认',
      narration: lines(
        `一次处置不是结束，而是下一次判断的经验…`,
        `请专家接受 / 拒绝 / 修改后再生成。`,
      ),
      reveal: 'feedback',
      scene: { kind: 'corridor', pitch: 50, zoom: 14 },
    },
  ]
}

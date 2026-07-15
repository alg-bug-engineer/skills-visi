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
import { compactTimingSummary } from '@/utils/planPresentation'

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
  | 'attribution'
  | 'cause'
  | 'strategy'
  | 'plan'
  | 'verification'
  | 'governance'
  | 'healthy'
  | 'overflow_chain'

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
  { index: 2, id: 'act3_overflow', phase: 'diagnosis', pipelineNode: '证据核验', processTitle: '证据核验', reveal: 'metrics', scene: { kind: 'lane', pitch: 0, zoom: 18, evidence: 'overflow_validation' } },
  // 证据核验后立刻给出归因分析（门控 cause phase）
  { index: 3, id: 'act4_attribution', phase: 'cause', pipelineNode: '归因分析', processTitle: '归因分析', reveal: 'attribution', scene: { kind: 'lane', pitch: 10, zoom: 18, evidence: 'cause_annotation' } },
  { index: 4, id: 'act5_bottleneck', phase: 'diagnosis', pipelineNode: '下游承接', processTitle: '下游承接能力判别', reveal: 'bottleneck', extraCards: ['overflow_chain'], scene: { kind: 'lane', pitch: 10, zoom: 18, evidence: 'downstream_topology' } },
  // 干线溯源：从 18 平滑抬升到 17（干线级）
  { index: 5, id: 'act6_corridor', phase: 'diagnosis', pipelineNode: '流向溯源', processTitle: '上下游流向溯源', reveal: 'corridor', scene: { kind: 'trace', pitch: 50, zoom: 15.5, evidence: 'flow_trace' } },
  { index: 6, id: 'act7_cases', phase: 'cause', pipelineNode: '案例校验', processTitle: '案例校验', reveal: 'cause', scene: { kind: 'lane', pitch: 10, zoom: 18, evidence: 'cause_annotation' } },
  // 治理策略：在干线级(17)基础上 +1 放大（需求21-R3），聚焦控制范围
  { index: 7, id: 'act8_strategy', phase: 'strategy', pipelineNode: '策略约束', processTitle: '治理策略与边界约束', reveal: 'governance', extraCards: ['overflow_chain'], scene: { kind: 'control', pitch: 45, zoom: 18, evidence: 'control_scope' } },
  { index: 8, id: 'act9_plan', phase: 'plan', pipelineNode: '方案交付', processTitle: '配时方案生成', reveal: 'plan', scene: { kind: 'lane', pitch: 20, zoom: 18, evidence: 'plan_output' } },
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
        `指标研判：排队比 ${ratio(diag?.metrics?.queue_ratio)}｜饱和度 ${ratio(saturationOf(diag?.metrics))}｜绿灯利用率 ${ratio(diag?.metrics?.green_utilization)}`,
        diag?.healthy
          ? '结论：各项指标均在正常区间，路口运行平稳、无溢出风险，无需干预'
          : diag?.overflow_verification?.risk_level === 'warning'
            ? '结论：排队接近进口道空间边界，处于溢出预警'
            : diag?.overflow_verification?.message && `结论：${diag.overflow_verification.message}`,
      )
    case 'act4_attribution': {
      const mech = (diag as { overflow_mechanism?: { primary?: string } } | undefined)?.overflow_mechanism
        ?.primary
      const mechLabel: Record<string, string> = {
        discharge_anomaly: '本路口放行过程异常',
        local_release_insufficient: '本路口放行不足',
        downstream_blocked: '下游回堵',
        upstream_arrival_shock: '上游冲击',
        evidence_insufficient: '证据不足',
      }
      const primary = cause?.cause_analysis?.primary_cause
      if (mech) {
        if (mech === 'discharge_anomaly') {
          return lines(
            `判断：${mechLabel[mech]}`,
            `依据：排队比 ${ratio(diag?.metrics?.queue_ratio)}，绿灯有效利用率 ${ratio(diag?.metrics?.green_utilization)}，直接下游仍有余量`,
            '处置：用小步增绿试运行验证效果，系统同步监测出口通行、检测数据和下游排队',
          )
        }
        return lines(
          `溢出机制：${mechLabel[mech] ?? mech}`,
          primary &&
            primary !== (mechLabel[mech] ?? mech) &&
            `次因线索：${productCopy(primary)}`,
        )
      }
      return lines(
        primary && `主因：${productCopy(primary)}`,
      )
    }
    case 'act5_bottleneck': {
      const ds = (diag as { downstream_state?: { decision?: string; direct_downstream_inter_name?: string; confidence?: number } } | undefined)
        ?.downstream_state
      const dd = diag?.downstream_diagnosis
      const pd = dd?.primary_downstream
      const dm = pd?.metrics
      const tm = diag?.metrics
      const storage = typeof pd?.remaining_storage_m === 'number' && pd.remaining_storage_m > 0
        ? `｜剩余蓄车 ${meters(pd.remaining_storage_m)}`
        : ''
      const slackLine =
        ds?.decision === 'slack'
          ? `下游判断：${ds.direct_downstream_inter_name || pd?.inter_name || '直接下游'} 当前有承接余量`
          : ds?.decision === 'blocked'
            ? `下游判断：${ds.direct_downstream_inter_name || pd?.inter_name || '直接下游'} 承接受限`
            : ds?.decision === 'unknown'
              ? '下游判断：关键指标不足，暂不判定承接能力'
              : null
      return lines(
        ...domainIntroFor('act5_bottleneck'),
        tm &&
          `本路口：饱和度 ${ratio(tm.saturation)}｜绿灯利用率 ${ratio(tm.green_utilization)}｜服务水平 ${tm.los ?? '—'}`,
        pd?.inter_name &&
          `下游 ${pd.inter_name}：饱和度 ${ratio(dm?.saturation_rate ?? dm?.saturation)}｜服务水平 ${dm?.level_of_service ?? '—'}${storage}`,
        slackLine,
        !slackLine && `结论：${downstreamConclusion(dd)}`,
        ds?.decision === 'slack' &&
          '绿灯调节路径：下游有余量 → 可试运行小步增绿，并同步监测下游排队',
        ds?.decision === 'blocked' &&
          '绿灯调节路径：下游承接收紧 → 优先下游保护，不宜本路口直接拉长绿灯',
      )
    }
    case 'act6_corridor':
      return lines(
        diag?.arterial_analysis?.upstream_arrival_flow_vph != null &&
          `上游到达流量 ${meters(diag.arterial_analysis.upstream_arrival_flow_vph)}，正在比对放行强度与干线瓶颈位置`,
        diag?.arterial_analysis?.summary && `结论：${diag.arterial_analysis.summary}`,
      )
    case 'act7_cases':
      return lines(
        cause?.case_cards?.matched_count != null &&
          `案例校验：匹配同类案例 ${cause.case_cards.matched_count} 个，高度相似 ${cause.case_cards.high_similarity_count ?? 0} 个`,
      )
    case 'act8_strategy': {
      const decision = (strategy as { decision?: { decision_mode?: string; reason?: string } } | undefined)
        ?.decision
      return lines(
        ...domainIntroFor('act8_strategy'),
        decision?.decision_mode === 'verify_then_adjust' &&
          '治理决策：先验后调｜绿灯路径 = 核验通过 → 目标有效绿小步增加（周期尽量不变）',
        decision?.decision_mode === 'incremental_release_trial' &&
          '治理决策：立即试运行｜目标有效绿小步增加，相位内借绿，周期保持不变',
        decision?.decision_mode === 'protect_downstream' &&
          '治理决策：下游保护｜绿灯路径 = 本路口保守放行或不增绿',
        decision?.decision_mode &&
          !['verify_then_adjust', 'incremental_release_trial', 'protect_downstream'].includes(decision.decision_mode) &&
          `治理决策：${productCopy(decision.decision_mode)}`,
        !decision?.decision_mode && strategy?.strategy?.principles?.[0] &&
          `治理路径：${productCopy(strategy.strategy.principles[0])}`,
        decision?.reason && `说明：${productCopy(decision.reason)}`,
        strategy?.strategy?.hard_constraints?.[0] &&
          `红线：${productCopy(String(strategy.strategy.hard_constraints[0]))}`,
      )
    }
    case 'act9_plan': {
      const planId = plan?.recommendation?.recommended_plan_id
      const timingSummary = compactTimingSummary(plan?.recommended)
      const pkg = (plan as { action_package?: { schemes?: { signal_control?: Array<{ action?: string }> } } } | undefined)
        ?.action_package
      const phaseLines = (pkg?.schemes?.signal_control || [])
        .map((x) => x?.action)
        .filter((t): t is string => Boolean(t && /绿灯|[+\-±]\d+s|周期/.test(t)))
        .slice(0, 3)
      return lines(
        planId && `推荐：${translatePlanId(planId)}`,
        timingSummary && `配时：${timingSummary}`,
        !timingSummary && phaseLines.length > 0 && `信控：${phaseLines.join('；')}`,
        !timingSummary && !phaseLines.length &&
          planId === 'verification_plan' &&
          '信控：当前数据不足，尚未形成可下发配时',
        plan?.plan_status === 'trial_ready' &&
          `执行：下发后试运行 ${plan?.trial_loop?.observation_cycles ?? 5} 个周期，异常自动回滚`,
        plan?.executable === false && '状态：数据不足，暂不生成可下发配时',
      )
    }
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
    case 'act4_attribution': {
      const mech = (cause as { overflow_mechanism?: { primary?: string } } | undefined)?.overflow_mechanism
        ?.primary
      if (mech === 'discharge_anomaly') {
        return `高排队、低绿灯利用，下游仍有余量；判断为本路口放行过程异常`
      }
      return productCopy(cause?.cause_analysis?.primary_cause ?? '归因分析完成')
    }
    case 'act5_bottleneck': {
      const ds = (diag as { downstream_state?: { decision?: string; direct_downstream_inter_name?: string } } | undefined)
        ?.downstream_state
      if (ds?.decision === 'slack') {
        return productCopy(`${ds.direct_downstream_inter_name || '直接下游'}有承接余量，可开展小步增绿试运行`)
      }
      if (ds?.decision === 'blocked') {
        return productCopy(`${ds.direct_downstream_inter_name || '直接下游'}承接受限，优先下游保护`)
      }
      return productCopy(downstreamConclusion(diag?.downstream_diagnosis))
    }
    case 'act6_corridor':
      return productCopy(diag?.arterial_analysis?.summary ?? '干线溯源完成')
    case 'act7_cases':
      return cause?.case_cards?.matched_count != null
        ? `匹配案例 ${cause.case_cards.matched_count} 个`
        : '案例校验完成'
    case 'act8_strategy': {
      const decision = (strategy as { decision?: { decision_mode?: string; reason?: string } } | undefined)?.decision
      if (decision?.decision_mode === 'verify_then_adjust') {
        return productCopy(decision.reason || '先验后调：核验通过后再小步增绿')
      }
      if (decision?.decision_mode === 'incremental_release_trial') {
        return productCopy(decision.reason || '立即开展小步增绿试运行，系统监测并自动回滚')
      }
      return productCopy(strategy?.strategy?.principles?.[0] ?? '策略推荐完成')
    }
    case 'act9_plan': {
      const planId = plan?.recommendation?.recommended_plan_id
      if (plan?.plan_status === 'trial_ready') return `试运行方案就绪：${compactTimingSummary(plan.recommended)}`
      if (planId === 'verification_plan') return '当前数据不足，尚未形成可下发配时'
      return planId ? `推荐方案 ${translatePlanId(planId)}` : '方案生成完成'
    }
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

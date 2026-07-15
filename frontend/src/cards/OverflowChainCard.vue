<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'
import { meters, ratio } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()

const MECHANISM_LABEL: Record<string, string> = {
  downstream_blocked: '下游回堵',
  local_release_insufficient: '本路口放行不足',
  discharge_anomaly: '放行效率异常，待核验',
  upstream_arrival_shock: '上游冲击',
  evidence_insufficient: '证据不足',
}

const DECISION_LABEL: Record<string, string> = {
  verify_then_adjust: '先验后调',
  incremental_release: '小步增绿',
  incremental_release_trial: '小步增绿试验',
  downstream_protection: '下游保护',
  upstream_coordination: '上下游联控',
  verification_required: '补证核验',
}

const STATUS_LABEL: Record<string, string> = {
  completed_conditional: '条件性方案（不可直接执行）',
  completed_requires_verification: '需补证后决策',
  completed_with_trial_plan: '试运行方案',
  completed_no_action: '无需干预',
  failed: '流程未完成',
}

const diag = computed(() => store.diagnosis)
const strategy = computed(() => store.strategy)
const plan = computed(() => store.plan)
const ticket = computed(() => store.response?.diagnosis_ticket)

const overflowLine = computed(() => {
  const ov = diag.value?.overflow_verification
  const metrics = diag.value?.metrics
  const remain =
    typeof metrics?.storage_length_m === 'number' && typeof metrics?.queue_length_m === 'number'
      ? Math.max(0, metrics.storage_length_m - metrics.queue_length_m)
      : null
  const dir = `${ticket.value?.direction ?? ''}${ticket.value?.movement ?? ''}`.trim() || '目标转向'
  if (diag.value?.healthy) return `${dir}：运行平稳，无溢出风险`
  const risk = ov?.risk_level === 'warning' ? '溢出预警' : ov?.risk_level === 'high' ? '明确溢出风险' : '溢出状态待确认'
  const remainText = remain != null ? `，剩余蓄车约 ${meters(remain)}` : ''
  const qr = metrics?.queue_ratio != null ? `（排队比 ${ratio(metrics.queue_ratio)}）` : ''
  return `${dir}处于${risk}${qr}${remainText}`
})

const downstreamLine = computed(() => {
  const ds = (diag.value as { downstream_state?: Record<string, unknown> } | undefined)?.downstream_state
  const name =
    (ds?.direct_downstream_inter_name as string | undefined) ||
    diag.value?.downstream_diagnosis?.primary_downstream?.inter_name ||
    '直接下游'
  const decision = ds?.decision as string | undefined
  const conf = typeof ds?.confidence === 'number' ? ds.confidence : null
  const missing = Array.isArray(ds?.missing_metrics) ? (ds?.missing_metrics as string[]) : []
  const judgment =
    decision === 'slack'
      ? '初步有承接余量'
      : decision === 'blocked'
        ? '承接受限'
        : decision === 'unknown'
          ? '指标不足，暂不判定'
          : null
  if (!judgment) return null
  const confText = conf != null ? `，置信度 ${conf >= 0.8 ? '高' : conf >= 0.55 ? '中' : '低'}` : ''
  const missText = missing.length ? `；缺失：${missing.join('、')}` : ''
  return `直接下游：${name}｜${judgment}${confText}${missText}`
})

const mechanismLine = computed(() => {
  const primary = (diag.value as { overflow_mechanism?: { primary?: string } } | undefined)
    ?.overflow_mechanism?.primary
  if (!primary) return null
  const label = MECHANISM_LABEL[primary] ?? primary
  const parts = [`当前机制：${label}`]
  if (primary !== 'downstream_blocked') parts.push('不支持：下游整体承接不足')
  if (primary === 'discharge_anomaly') parts.push('尚未确认：信号有效绿不足')
  return parts.join('｜')
})

const decisionLine = computed(() => {
  const decision = (strategy.value as { decision?: Record<string, unknown> } | undefined)?.decision
  const mode = (decision?.decision_mode as string | undefined) || (strategy.value?.strategy as { decision_mode?: string } | undefined)?.decision_mode
  if (!mode) return null
  const label = DECISION_LABEL[mode] ?? mode
  const reason = (decision?.reason as string | undefined) || ''
  return reason ? `${label}：${productCopy(reason)}` : label
})

const planLine = computed(() => {
  const status = store.response?.completion_status
  const trial = (plan.value as { trial_loop?: Record<string, unknown> } | undefined)?.trial_loop
  const rec = plan.value?.recommended
  const executable = rec?.executable ?? plan.value?.executable
  const planStatus = rec?.plan_status ?? plan.value?.plan_status
  if (status && STATUS_LABEL[status]) {
    const bits = [STATUS_LABEL[status]]
    if (executable === false) bits.push('当前不可直接执行')
    const delta = trial?.target_effective_green_delta_s
    if (typeof delta === 'number' && planStatus !== 'conditional') {
      bits.push(`目标有效绿 ${delta >= 0 ? '+' : ''}${delta}s`)
    }
    if (typeof trial?.observation_cycles === 'number') {
      bits.push(`观察 ${trial.observation_cycles} 个周期`)
    }
    return bits.join('｜')
  }
  if (planStatus === 'conditional' || executable === false) {
    return '条件性方案｜当前不可直接执行'
  }
  return null
})

const hasAny = computed(
  () =>
    !!overflowLine.value ||
    !!downstreamLine.value ||
    !!mechanismLine.value ||
    !!decisionLine.value ||
    !!planLine.value,
)
</script>

<template>
  <BaseCard v-if="hasAny" title="诊断治理主链" tone="evidence" data-testid="overflow-chain-card">
    <ul class="chain">
      <li v-if="overflowLine">{{ overflowLine }}</li>
      <li v-if="downstreamLine">{{ downstreamLine }}</li>
      <li v-if="mechanismLine">{{ mechanismLine }}</li>
      <li v-if="decisionLine">{{ decisionLine }}</li>
      <li v-if="planLine" class="chain__plan">{{ planLine }}</li>
    </ul>
  </BaseCard>
</template>

<style scoped>
.chain {
  margin: 0;
  padding-left: 1.1em;
  display: grid;
  gap: 6px;
  color: var(--text);
  line-height: 1.45;
}
.chain__plan {
  color: var(--accent, #7eb6ff);
  font-weight: 600;
}
</style>

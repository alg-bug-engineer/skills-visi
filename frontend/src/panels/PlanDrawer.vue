<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import type { PlanCandidate } from '@/api/types'
import { translatePlanId } from '@/labels/enums'
import CoordinationDiagram from '@/panels/CoordinationDiagram.vue'
import { productCopy } from '@/utils/productCopy'
import PlanEvidencePanel from '@/panels/PlanEvidencePanel.vue'
import { meters, ratio } from '@/utils/format'
import {
  compactTimingSummary,
  hasCoreTimingEvidence,
  isLegacyVerificationPlan,
  timingActionLines,
  trialTimingOf,
} from '@/utils/planPresentation'

const store = usePresentationStore()
const { planMinimized } = storeToRefs(store)

const coordination = computed(() => store.diagnosis?.coordination ?? null)

const candidates = computed<PlanCandidate[]>(() => store.plan?.candidates ?? [])
const recommendedId = computed(
  () =>
    (store.plan as { recommended_plan_id?: string } | null)?.recommended_plan_id ??
    store.plan?.recommendation?.recommended_plan_id ??
    store.plan?.recommended?.plan_id ??
    null,
)
const selected = computed<PlanCandidate | null>(() => {
  const id = recommendedId.value
  // recommended 可能在候选生成后又补充 proposed_timing/action_package 等证据，
  // 同一 plan_id 时优先使用这份最终快照，避免误读 candidates 中的中间态。
  const recommended = store.plan?.recommended as PlanCandidate | null
  const base = recommended && (!id || recommended.plan_id === id)
    ? recommended
    : candidates.value.find((c) => c.plan_id === id) ?? recommended ?? candidates.value[0] ?? null
  const trial = trialTimingOf(base)
  if (base && isLegacyVerificationPlan(base) && trial?.phase_stage_timing_list?.some((s) => (s.green_delta_s ?? 0) !== 0)) {
    return {
      ...base,
      plan_id: 'conditional_incremental_release',
      name: '小步增绿试运行方案',
      timing: trial,
      executable: true,
      plan_status: 'trial_ready',
      expected_effect: '用 5 个周期验证并缓解目标进口排队，不加重下游拥堵',
      risk: '目标排队未改善或下游排队增长时自动回滚',
    }
  }
  return base
})
const hasTiming = computed(() => hasCoreTimingEvidence(trialTimingOf(selected.value)))

type SchemeItem = { action?: string; where?: string; kind?: string; target?: string }
type ActionPackage = {
  schemes?: {
    signal_control?: SchemeItem[]
    organization?: SchemeItem[]
    management?: SchemeItem[]
  }
  execution_order?: string[]
}

function strategyItemText(item: unknown): string {
  if (item && typeof item === 'object') {
    const row = item as Record<string, unknown>
    const action = String(row.action ?? row.title ?? row.name ?? '').trim()
    const target = String(row.target_node ?? row.target ?? row.where ?? '').trim()
    return [action, target && !action.includes(target) ? `位置：${target}` : ''].filter(Boolean).join('；')
  }
  const raw = String(item ?? '').trim()
  if (!raw.startsWith('{')) return productCopy(raw)
  const action = raw.match(/["']action["']\s*:\s*["']([^"']+)["']/)?.[1] ?? ''
  const target = raw.match(/["'](?:target_node|where)["']\s*:\s*["']([^"']+)["']/)?.[1] ?? ''
  if (action || target) return [action, target ? `位置：${target}` : ''].filter(Boolean).join('；')
  return '按方案要求执行并持续监测关键指标'
}

function schemeActions(items: SchemeItem[] | undefined): string[] {
  return (items ?? [])
    .map((item) => productCopy(strategyItemText(item)))
    .filter(Boolean)
    .slice(0, 6)
}

const actionPackage = computed(
  () =>
    (store.plan as { action_package?: ActionPackage } | null)?.action_package ??
    (store.strategy as { action_package?: ActionPackage } | null)?.action_package ??
    null,
)
const signalControlItems = computed(() => {
  const actual = timingActionLines(selected.value)
  return actual.length ? actual : schemeActions(actionPackage.value?.schemes?.signal_control)
})
const organizationItems = computed(() => schemeActions(actionPackage.value?.schemes?.organization))
const managementItems = computed(() => schemeActions(actionPackage.value?.schemes?.management))
const strategyItems = computed(() => {
  if (actionPackage.value?.schemes) return []
  return (selected.value?.execution_order ?? [])
    .map((item) => productCopy(strategyItemText(item)))
    .filter(Boolean)
    .slice(0, 6)
})
const redLines = computed(() => {
  const constraints = store.strategy?.strategy?.hard_constraints ?? []
  const risks = selected.value?.downstream_risk?.reasons ?? []
  const validation = selected.value?.validation_errors ?? []
  return [...constraints, ...risks, ...validation].filter(Boolean).slice(0, 5)
})
const strategyTarget = computed(() => store.strategy?.strategy?.target_intersection ?? null)
const targetTitle = computed(() => {
  const target = strategyTarget.value
  if (!target) return store.response?.diagnosis_ticket?.intersection_name ?? ''
  return [target.inter_name, `${target.direction ?? ''}${target.movement ?? ''}`].filter(Boolean).join(' · ')
})
const rejecting = ref(false)
const rejectReason = ref('')
const busy = ref(false)

const planExecutable = computed(() => {
  const rec = selected.value
  if (rec?.executable === true && rec?.plan_status === 'trial_ready' && rec.guardrail_pass !== false) {
    return true
  }
  if (rec?.executable === false) return false
  if (store.plan?.executable === false) return false
  if ((rec?.plan_status as string | undefined) === 'conditional') return false
  if (store.plan?.plan_status === 'conditional') return false
  if (store.response?.completion_status === 'completed_conditional') return false
  if (store.response?.completion_status === 'completed_requires_verification') return false
  return true
})

const trialLoop = computed(() => store.plan?.trial_loop ?? null)
const isTrialPlan = computed(
  () =>
    selected.value?.plan_status === 'trial_ready' ||
    store.plan?.plan_status === 'trial_ready' ||
    store.response?.completion_status === 'completed_with_trial_plan',
)
const trialCycles = computed(() => trialLoop.value?.observation_cycles ?? 5)
const timingSummary = computed(() => compactTimingSummary(selected.value))

const decisionBasis = computed(() => {
  const metrics = store.diagnosis?.metrics
  const downstream = store.diagnosis?.downstream_diagnosis?.primary_downstream
  const downstreamMetrics = downstream?.metrics
  const rows: string[] = []
  if (metrics?.queue_ratio != null) rows.push(`目标进口排队已占蓄车空间 ${ratio(metrics.queue_ratio)}`)
  if (metrics?.green_utilization != null) rows.push(`当前绿灯有效利用率 ${ratio(metrics.green_utilization)}`)
  if (downstream?.remaining_storage_m != null) {
    rows.push(`${downstream.inter_name || '直接下游'}剩余蓄车 ${meters(downstream.remaining_storage_m)}`)
  } else if (downstreamMetrics?.queue_storage_ratio_max != null) {
    rows.push(`${downstream?.inter_name || '直接下游'}排队比 ${ratio(downstreamMetrics.queue_storage_ratio_max)}`)
  }
  return rows.slice(0, 3)
})

async function onAccept() {
  if (!selected.value || !planExecutable.value) return
  busy.value = true
  await store.accept(selected.value.plan_id, selected.value)
  busy.value = false
}
async function onReject() {
  if (!selected.value || !rejectReason.value.trim()) return
  busy.value = true
  await store.reject(selected.value.plan_id, rejectReason.value.trim())
  rejecting.value = false
  rejectReason.value = ''
  busy.value = false
}

</script>

<template>
  <section class="drawer us-panel" :class="{ 'drawer--min': planMinimized }" data-testid="plan-drawer">
    <header class="drawer__hd" @click="planMinimized && store.togglePlanMinimized()">
      <div>
        <h3>治理建议</h3>
        <p>
          {{
            !planExecutable
              ? '当前数据不足以安全生成配时，请退回补充数据'
              : isTrialPlan
                ? `可下发试运行 ${trialCycles} 个周期，系统持续监测并支持自动回滚`
                : hasTiming
                  ? '配时明细来自后端真实方案数据'
                : '后端未返回可绘制配时明细'
          }}
        </p>
      </div>
      <div class="drawer__hd-right">
        <span v-if="selected?.plan_id" class="rec">建议 {{ productCopy(selected.name) || translatePlanId(selected.plan_id) }}</span>
        <span v-if="isTrialPlan" class="rec rec--trial">可试运行</span>
        <span v-else-if="!planExecutable" class="rec rec--warn">数据不足</span>
        <button
          type="button"
          class="min-btn"
          data-testid="plan-min-toggle"
          :title="planMinimized ? '最大化' : '最小化'"
          @click.stop="store.togglePlanMinimized()"
        >
          {{ planMinimized ? '⤢ 最大化' : '⤡ 最小化' }}
        </button>
      </div>
    </header>

    <!-- 治理建议 -->
    <div class="pane">
      <div v-if="selected" class="stage">
        <div class="stage__left">
          <h4>{{ productCopy(selected.name) }} · 相位配时</h4>
          <template v-if="hasTiming">
            <PlanEvidencePanel :candidate="selected" />
            <h4 class="mt">干线协调关系</h4>
            <CoordinationDiagram :coordination="coordination" />
          </template>
          <div v-else class="data-missing">
            <strong>需要后端补齐配时明细</strong>
            <span>请返回 cycle_s 与 phase_stage_timing_list；前端不使用静态图或模拟阶段数据。</span>
          </div>
        </div>
        <div class="stage__right">
          <div v-if="targetTitle" class="scope-box">
            <span class="kpi__k">本次优化对象</span>
            <strong>{{ targetTitle }}</strong>
            <small v-if="strategyTarget?.inter_id">路口编号 {{ strategyTarget.inter_id }}</small>
          </div>
          <div class="kpi">
            <span class="kpi__k">预期效果</span>
            <span class="kpi__v ok">{{ productCopy(selected.expected_effect) || '—' }}</span>
          </div>
          <div class="kpi">
            <span class="kpi__k">风险</span>
            <span class="kpi__v warn">{{ productCopy(selected.risk) || '—' }}</span>
          </div>
          <div v-if="decisionBasis.length" class="list-box decision-box" data-testid="decision-basis">
            <span class="kpi__k">为什么这样调</span>
            <ul>
              <li v-for="(item, i) in decisionBasis" :key="`basis-${i}`">{{ item }}</li>
            </ul>
            <strong v-if="timingSummary">因此采用：{{ timingSummary }}</strong>
          </div>
          <div v-if="trialLoop" class="list-box">
            <span class="kpi__k">下发后的试运行闭环</span>
            <ul>
              <li>立即执行：下发后运行 {{ trialCycles }} 个周期</li>
              <li v-if="trialLoop.direct_downstream_inter_name">
                系统监测：目标进口与 {{ trialLoop.direct_downstream_inter_name }}
              </li>
              <li v-for="(r, i) in (trialLoop.rollback_rules || []).slice(0, 2)" :key="`r-${i}`">
                自动回滚：{{ productCopy(String(r)) }}
              </li>
            </ul>
          </div>
          <div v-if="signalControlItems.length" class="list-box" data-testid="scheme-signal-control">
            <span class="kpi__k">信控方案</span>
            <ul>
              <li v-for="(item, i) in signalControlItems" :key="`sc-${i}`">{{ item }}</li>
            </ul>
          </div>
          <div v-if="organizationItems.length" class="list-box" data-testid="scheme-organization">
            <span class="kpi__k">交通组织优化</span>
            <ul>
              <li v-for="(item, i) in organizationItems" :key="`org-${i}`">{{ item }}</li>
            </ul>
          </div>
          <div v-if="managementItems.length" class="list-box" data-testid="scheme-management">
            <span class="kpi__k">交通管理建议</span>
            <ul>
              <li v-for="(item, i) in managementItems" :key="`mgmt-${i}`">{{ item }}</li>
            </ul>
          </div>
          <div v-if="strategyItems.length" class="list-box">
            <span class="kpi__k">执行动作</span>
            <ul>
              <li v-for="(item, i) in strategyItems" :key="i">{{ item }}</li>
            </ul>
          </div>

          <div v-if="redLines.length" class="list-box list-box--red">
            <span class="kpi__k">红线</span>
            <ul>
              <li v-for="(item, i) in redLines" :key="i">{{ productCopy(String(item)) }}</li>
            </ul>
          </div>
        </div>
      </div>
      <p v-else class="empty">暂无治理建议数据</p>
    </div>

    <!-- 反馈决策 -->
    <footer class="drawer__ft">
      <template v-if="!rejecting">
        <button class="btn btn--ghost" :disabled="busy" @click="rejecting = true">退回修改</button>
        <button
          class="btn btn--primary"
          :disabled="busy || !selected || !planExecutable"
          :title="planExecutable ? '' : '当前数据不足以安全生成配时，请退回补充数据'"
          @click="onAccept"
        >
          {{ busy ? '下发中…' : planExecutable && isTrialPlan ? `下发并试运行 ${trialCycles} 周期` : planExecutable ? '接受并下发' : '数据不足，无法下发' }}
        </button>
      </template>
      <template v-else>
        <input v-model="rejectReason" class="reason" placeholder="填写修改意见，例如：优先保护下游、缩小调整幅度…" />
        <button class="btn btn--ghost" :disabled="busy" @click="rejecting = false">取消</button>
        <button class="btn btn--warn" :disabled="busy || !rejectReason.trim()" @click="onReject">
          {{ busy ? '生成中…' : '提交并生成' }}
        </button>
      </template>
    </footer>
  </section>
</template>

<style scoped>
.drawer {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 14px 16px;
  overflow: hidden;
  border-radius: 0;
  background: rgba(4, 13, 24, 0.94);
}
.drawer__hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.drawer--min .pane,
.drawer--min .drawer__ft {
  display: none;
}
.drawer--min .drawer__hd {
  margin-bottom: 0;
  cursor: pointer;
}
.drawer__hd-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.min-btn {
  padding: 4px 10px;
  border-radius: 0;
  border: 1px solid var(--panel-border);
  background: transparent;
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.min-btn:hover {
  color: var(--text);
  border-color: var(--primary);
}
.drawer__hd h3 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
}
.scope-box {
  display: grid;
  gap: 5px;
  padding: 10px 12px;
  border-left: 3px solid var(--primary);
  background: rgba(0, 229, 255, 0.07);
}
.scope-box strong { color: var(--text); font-size: 13px; }
.scope-box small { color: var(--text-mute); }
.list-box--constraint { border-color: rgba(0, 229, 255, 0.32); }
.drawer__hd p {
  margin: 3px 0 0;
  color: var(--text-mute);
  font-size: 12px;
}
.rec {
  font-size: 12px;
  color: var(--primary);
}
.rec--warn {
  color: #e6b35c;
  margin-left: 8px;
}
.rec--trial {
  padding: 2px 7px;
  border: 1px solid rgba(109, 255, 181, 0.38);
  color: var(--protected);
}
.pane {
  flex: 1;
  overflow: auto;
}
.stage {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 16px;
}
.stage h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text);
}
.stage h4.mt {
  margin-top: 14px;
}
.kpi {
  margin-bottom: 10px;
  padding: 10px 11px;
  border: 1px solid rgba(146, 161, 181, 0.35);
  background: rgba(255, 255, 255, 0.025);
  border-radius: 0;
}
.kpi__k {
  display: block;
  font-size: 11px;
  color: var(--text-mute);
  margin-bottom: 2px;
}
.kpi__v {
  font-size: 13px;
  color: var(--text);
}
.kpi__v.ok {
  color: var(--protected);
}
.kpi__v.warn {
  color: var(--evidence);
}
.ok {
  color: var(--protected);
}
.bad {
  color: var(--alarm);
}
.drawer__ft {
  display: flex;
  gap: 8px;
  align-items: center;
  padding-top: 10px;
  margin-top: 8px;
  border-top: 1px solid var(--panel-border);
}
.reason {
  flex: 1;
  padding: 8px 10px;
  border-radius: 0;
  border: 1px solid var(--panel-border);
  background: rgba(0, 0, 0, 0.3);
  color: var(--text);
  font-size: 13px;
}
.btn {
  padding: 8px 18px;
  border-radius: 0;
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn--primary {
  background: var(--primary);
  color: var(--bg);
}
.btn--warn {
  background: var(--evidence);
  color: var(--bg);
}
.btn--ghost {
  background: transparent;
  border-color: var(--panel-border);
  color: var(--text-dim);
}
.empty {
  color: var(--text-mute);
  font-size: 13px;
  text-align: center;
  margin-top: 30px;
}
.data-missing,
.data-note {
  border: 1px solid rgba(146, 161, 181, 0.35);
  background: rgba(255, 255, 255, 0.03);
  padding: 12px;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.5;
}
.data-missing {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.data-missing strong {
  color: var(--evidence);
}
.list-box {
  margin-bottom: 10px;
  padding: 10px 11px;
  border: 1px solid rgba(146, 161, 181, 0.35);
  background: rgba(255, 255, 255, 0.025);
}
.list-box--red {
  border-color: rgba(255, 80, 80, 0.5);
}
.decision-box {
  border-color: rgba(0, 229, 255, 0.38);
  background: rgba(0, 229, 255, 0.055);
}
.decision-box strong {
  display: block;
  margin-top: 8px;
  color: var(--protected);
  font-size: 12.5px;
  line-height: 1.45;
}
.list-box ul {
  margin: 6px 0 0;
  padding-left: 16px;
}
.list-box li {
  margin: 4px 0;
  font-size: 12.5px;
  line-height: 1.45;
  color: var(--text-dim);
}
</style>

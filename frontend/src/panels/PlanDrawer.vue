<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import type { PlanCandidate } from '@/api/types'
import { translatePlanId } from '@/labels/enums'
import CoordinationDiagram from '@/panels/CoordinationDiagram.vue'
import { productCopy } from '@/utils/productCopy'
import PlanEvidencePanel from '@/panels/PlanEvidencePanel.vue'

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
  return candidates.value.find((c) => c.plan_id === id) ?? (store.plan?.recommended as PlanCandidate) ?? candidates.value[0] ?? null
})
const hasTiming = computed(() => Boolean(selected.value?.timing?.cycle_s && selected.value?.timing?.phase_stage_timing_list?.length))
function strategyItemText(item: unknown): string {
  if (item && typeof item === 'object') {
    const row = item as Record<string, unknown>
    const action = String(row.action ?? row.title ?? row.name ?? '').trim()
    const target = String(row.target_node ?? row.target ?? '').trim()
    return [action, target ? `实施位置：${target}` : ''].filter(Boolean).join('；')
  }
  const raw = String(item ?? '').trim()
  if (!raw.startsWith('{')) return productCopy(raw)
  // 模型偶尔把结构化策略以 Python 字典字符串返回，只展示其中的业务含义。
  const action = raw.match(/["']action["']\s*:\s*["']([^"']+)["']/)?.[1] ?? ''
  const target = raw.match(/["']target_node["']\s*:\s*["']([^"']+)["']/)?.[1] ?? ''
  if (action || target) return [action, target ? `实施位置：${target}` : ''].filter(Boolean).join('；')
  return '按方案要求执行并持续监测关键指标'
}
const strategyItems = computed(() => {
  const fromStrategy = store.strategy?.strategy?.recommended ?? []
  const fromPlan = selected.value?.execution_order ?? []
  return [...fromStrategy, ...fromPlan].filter(Boolean).map((item) => productCopy(strategyItemText(item))).filter(Boolean).slice(0, 6)
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
  if (rec?.executable === false) return false
  if (store.plan?.executable === false) return false
  if ((rec?.plan_status as string | undefined) === 'conditional') return false
  if (store.plan?.plan_status === 'conditional') return false
  if (store.response?.completion_status === 'completed_conditional') return false
  if (store.response?.completion_status === 'completed_requires_verification') return false
  return true
})

const trialLoop = computed(() => store.plan?.trial_loop ?? null)

async function onAccept() {
  if (!selected.value || !planExecutable.value) return
  busy.value = true
  await store.accept(selected.value.plan_id)
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
              ? '条件性/待核验方案：不可直接下发'
              : hasTiming
                ? '配时明细来自后端真实方案数据'
                : '后端未返回可绘制配时明细'
          }}
        </p>
      </div>
      <div class="drawer__hd-right">
        <span v-if="recommendedId" class="rec">建议 {{ translatePlanId(recommendedId) }}</span>
        <span v-if="!planExecutable" class="rec rec--warn">不可直接执行</span>
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
          <div v-if="trialLoop" class="list-box">
            <span class="kpi__k">试运行闭环</span>
            <ul>
              <li v-if="trialLoop.observation_cycles != null">观察周期：{{ trialLoop.observation_cycles }}</li>
              <li v-if="trialLoop.direct_downstream_inter_name">
                监测下游：{{ trialLoop.direct_downstream_inter_name }}
              </li>
              <li v-for="(m, i) in (trialLoop.monitoring_metrics || []).slice(0, 4)" :key="`m-${i}`">
                监测：{{ m }}
              </li>
              <li v-for="(r, i) in (trialLoop.rollback_rules || []).slice(0, 3)" :key="`r-${i}`">
                回滚：{{ productCopy(String(r)) }}
              </li>
            </ul>
          </div>
          <div v-if="strategyItems.length" class="list-box">
            <span class="kpi__k">执行策略</span>
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
          :title="planExecutable ? '' : '核验未完成，方案不可直接下发'"
          @click="onAccept"
        >
          {{ busy ? '下发中…' : planExecutable ? '接受并下发' : '待核验（不可下发）' }}
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

<script setup lang="ts">
import { computed, ref } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import type { PlanCandidate } from '@/api/types'
import { t } from '@/labels/enums'
import CoordinationDiagram from '@/panels/CoordinationDiagram.vue'
import { productCopy } from '@/utils/productCopy'
import PlanEvidencePanel from '@/panels/PlanEvidencePanel.vue'

const store = usePresentationStore()

const coordination = computed(() => store.diagnosis?.coordination ?? null)

const candidates = computed<PlanCandidate[]>(() => store.plan?.candidates ?? [])
const recommendedId = computed(() => store.plan?.recommendation?.recommended_plan_id ?? null)
const selected = computed<PlanCandidate | null>(() => {
  const id = recommendedId.value
  return candidates.value.find((c) => c.plan_id === id) ?? (store.plan?.recommended as PlanCandidate) ?? candidates.value[0] ?? null
})
const hasTiming = computed(() => Boolean(selected.value?.timing?.cycle_s && selected.value?.timing?.phase_stage_timing_list?.length))
const strategyItems = computed(() => {
  const fromStrategy = store.strategy?.strategy?.recommended ?? []
  const fromPlan = selected.value?.execution_order ?? []
  return [...fromStrategy, ...fromPlan].filter(Boolean).slice(0, 6)
})
const redLines = computed(() => {
  const constraints = store.strategy?.strategy?.hard_constraints ?? []
  const risks = selected.value?.downstream_risk?.reasons ?? []
  const validation = selected.value?.validation_errors ?? []
  return [...constraints, ...risks, ...validation].filter(Boolean).slice(0, 5)
})

const rejecting = ref(false)
const rejectReason = ref('')
const busy = ref(false)

async function onAccept() {
  if (!selected.value) return
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
  <section class="drawer us-panel" data-testid="plan-drawer">
    <header class="drawer__hd">
      <div>
        <h3>治理建议</h3>
        <p>{{ hasTiming ? '配时明细来自后端真实方案数据' : '后端未返回可绘制配时明细' }}</p>
      </div>
      <span v-if="recommendedId" class="rec">建议 {{ t('plan_id', recommendedId.split('_').slice(0, 2).join('_')) }}</span>
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
          <div class="kpi">
            <span class="kpi__k">预期效果</span>
            <span class="kpi__v ok">{{ productCopy(selected.expected_effect) || '—' }}</span>
          </div>
          <div class="kpi">
            <span class="kpi__k">风险</span>
            <span class="kpi__v warn">{{ productCopy(selected.risk) || '—' }}</span>
          </div>
          <div class="kpi">
            <span class="kpi__k">回滚条件</span>
            <span class="kpi__v">{{ productCopy(selected.rollback_condition ?? store.plan?.rollback_conditions?.[0]) || '—' }}</span>
          </div>
          <div v-if="strategyItems.length" class="list-box">
            <span class="kpi__k">执行策略</span>
            <ul>
              <li v-for="(item, i) in strategyItems" :key="i">{{ productCopy(String(item)) }}</li>
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
        <button class="btn btn--primary" :disabled="busy || !selected" @click="onAccept">
          {{ busy ? '下发中…' : '接受并下发' }}
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
.drawer__hd h3 {
  margin: 0;
  color: var(--text);
  font-size: 15px;
}
.drawer__hd p {
  margin: 3px 0 0;
  color: var(--text-mute);
  font-size: 12px;
}
.rec {
  font-size: 12px;
  color: var(--primary);
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

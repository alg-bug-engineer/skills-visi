<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import type { PlanCandidate } from '@/api/types'
import { t } from '@/labels/enums'
import PhaseDiagram from '@/viz/PhaseDiagram.vue'
import TimeSpaceDiagram from '@/viz/TimeSpaceDiagram.vue'

const store = usePresentationStore()
const { planTab } = storeToRefs(store)

const candidates = computed<PlanCandidate[]>(() => store.plan?.candidates ?? [])
const recommendedId = computed(() => store.plan?.recommendation?.recommended_plan_id ?? null)
const selectedId = ref<string | null>(null)
const selected = computed<PlanCandidate | null>(() => {
  const id = selectedId.value ?? recommendedId.value
  return candidates.value.find((c) => c.plan_id === id) ?? (store.plan?.recommended as PlanCandidate) ?? candidates.value[0] ?? null
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

function statusTone(s?: string) {
  return s === 'rejected' ? 'alarm' : s === 'valid' ? 'protected' : 'evidence'
}
</script>

<template>
  <section class="drawer us-panel" data-testid="plan-drawer">
    <header class="drawer__hd">
      <div class="tabs">
        <button :class="{ on: planTab === 'stage_generation' }" @click="store.setPlanTab('stage_generation')">
          阶段方案
        </button>
        <button :class="{ on: planTab === 'plan_comparison' }" @click="store.setPlanTab('plan_comparison')">
          多方案比选
        </button>
      </div>
      <span v-if="recommendedId" class="rec">推荐 {{ t('plan_id', recommendedId.split('_').slice(0, 2).join('_')) }}</span>
    </header>

    <!-- 阶段方案 -->
    <div v-show="planTab === 'stage_generation'" class="pane">
      <div v-if="selected" class="stage">
        <div class="stage__left">
          <h4>{{ selected.name }} · 相位配时</h4>
          <PhaseDiagram
            :stages="selected.timing?.phase_stage_timing_list ?? []"
            :cycle="selected.timing?.cycle_s"
          />
          <h4 class="mt">时距图（绿波）</h4>
          <TimeSpaceDiagram :cycle="selected.timing?.cycle_s" :offset-sec="selected.phase_offset_sec" />
        </div>
        <div class="stage__right">
          <div class="kpi">
            <span class="kpi__k">预期效果</span>
            <span class="kpi__v ok">{{ selected.expected_effect ?? '—' }}</span>
          </div>
          <div class="kpi">
            <span class="kpi__k">风险</span>
            <span class="kpi__v warn">{{ selected.risk ?? '—' }}</span>
          </div>
          <div class="kpi">
            <span class="kpi__k">回滚条件</span>
            <span class="kpi__v">{{ selected.rollback_condition ?? store.plan?.rollback_conditions?.[0] ?? '—' }}</span>
          </div>
          <div class="exec" v-if="store.plan?.recommendation?.rationale">
            <span class="kpi__k">推荐理由</span>
            <p>{{ store.plan.recommendation.rationale }}</p>
          </div>
        </div>
      </div>
      <p v-else class="empty">暂无方案数据</p>
    </div>

    <!-- 多方案比选 -->
    <div v-show="planTab === 'plan_comparison'" class="pane">
      <table class="cmp" data-testid="plan-compare">
        <thead>
          <tr>
            <th>方案</th><th>周期</th><th>相位差</th><th>行人</th><th>下游风险</th><th>护栏</th><th>状态</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in candidates"
            :key="c.plan_id"
            :class="{ sel: (selectedId ?? recommendedId) === c.plan_id }"
            @click="selectedId = c.plan_id"
          >
            <td class="name">{{ c.name }}</td>
            <td>{{ c.timing?.cycle_s ?? '—' }}s</td>
            <td>{{ c.phase_offset_sec ?? '—' }}s</td>
            <td>
              <span :class="c.pedestrian_constraints?.satisfied ? 'ok' : 'bad'">
                {{ c.pedestrian_constraints?.satisfied ? '满足' : '违反' }}
              </span>
            </td>
            <td>{{ t('risk_level', c.downstream_risk?.level) }}</td>
            <td><span :class="c.guardrail_pass ? 'ok' : 'bad'">{{ c.guardrail_pass ? '通过' : '告警' }}</span></td>
            <td><span :class="`st st--${statusTone(c.status)}`">{{ t('status', c.status) }}</span></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!candidates.length" class="empty">暂无候选方案</p>
    </div>

    <!-- 幕九：决策反馈 -->
    <footer class="drawer__ft">
      <template v-if="!rejecting">
        <button class="btn btn--ghost" :disabled="busy" @click="rejecting = true">拒绝 / 修改</button>
        <button class="btn btn--primary" :disabled="busy || !selected" @click="onAccept">
          {{ busy ? '下发中…' : '接受并下发' }}
        </button>
      </template>
      <template v-else>
        <input v-model="rejectReason" class="reason" placeholder="填写修改意见，例如：优先保下游、缩小加绿幅度…" />
        <button class="btn btn--ghost" :disabled="busy" @click="rejecting = false">取消</button>
        <button class="btn btn--warn" :disabled="busy || !rejectReason.trim()" @click="onReject">
          {{ busy ? '再生成中…' : '提交并再生成' }}
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
  padding: 12px 14px;
  overflow: hidden;
}
.drawer__hd {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.tabs {
  display: flex;
  gap: 6px;
}
.tabs button {
  padding: 5px 14px;
  border-radius: 8px;
  border: 1px solid var(--panel-border);
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  cursor: pointer;
}
.tabs button.on {
  color: var(--bg);
  background: var(--primary);
  border-color: var(--primary);
  font-weight: 600;
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
.exec p {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-dim);
}
.cmp {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.cmp th,
.cmp td {
  padding: 7px 8px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.cmp th {
  color: var(--text-mute);
  font-weight: 500;
  font-size: 11px;
}
.cmp td {
  color: var(--text-dim);
}
.cmp td.name {
  color: var(--text);
}
.cmp tr {
  cursor: pointer;
}
.cmp tr.sel {
  background: var(--primary-dim);
}
.ok {
  color: var(--protected);
}
.bad {
  color: var(--alarm);
}
.st {
  padding: 1px 8px;
  border-radius: 5px;
  font-size: 11px;
}
.st--protected {
  color: var(--protected);
  background: var(--protected-dim);
}
.st--alarm {
  color: var(--alarm);
  background: var(--alarm-dim);
}
.st--evidence {
  color: var(--evidence);
  background: var(--evidence-dim);
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
  border-radius: 8px;
  border: 1px solid var(--panel-border);
  background: rgba(0, 0, 0, 0.3);
  color: var(--text);
  font-size: 13px;
}
.btn {
  padding: 8px 18px;
  border-radius: 8px;
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
</style>

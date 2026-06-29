<script setup lang="ts">
import { computed } from 'vue'
import type { FlowTimingGovernance } from '../../types/evidence'

const props = defineProps<{
  governance: FlowTimingGovernance
}>()

const verdictLabel = computed(() => {
  const map: Record<string, string> = {
    strong: '匹配良好',
    weak: '匹配偏弱',
    mismatch: '明显失配',
    insufficient: '样本不足',
  }
  return map[props.governance.match_verdict] ?? props.governance.match_verdict
})

const verdictClass = computed(() => {
  const v = props.governance.match_verdict
  if (v === 'mismatch') return 'bad'
  if (v === 'weak') return 'warn'
  if (v === 'strong') return 'good'
  return 'neutral'
})

const primary = computed(() => props.governance.primary_diagnosis ?? null)

const primarySeverityClass = computed(() => {
  const sev = primary.value?.severity
  if (sev === 'high') return 'sev-high'
  if (sev === 'medium') return 'sev-medium'
  return 'sev-none'
})
</script>

<template>
  <article class="gov-card">
    <header class="gov-head">
      <span class="eyebrow">FLOW × TIMING</span>
      <h3>流量-配时匹配 · 四维诊断</h3>
      <span class="verdict" :class="verdictClass">{{ verdictLabel }}</span>
    </header>

    <section v-if="primary" class="primary" :class="primarySeverityClass">
      <p class="primary-headline">{{ primary.headline }}</p>
      <p v-if="primary.lever" class="primary-lever">{{ primary.lever }}</p>
      <ul v-if="primary.evidence?.length" class="primary-evidence">
        <li v-for="(line, i) in primary.evidence" :key="i">{{ line }}</li>
      </ul>
      <div
        v-if="primary.turn_balance?.over || primary.turn_balance?.spare"
        class="turn-balance"
        data-testid="turn-balance"
      >
        <div v-if="primary.turn_balance.over" class="tb-row over">
          <span class="tb-label">过饱和方</span>
          <span class="tb-val">{{ primary.turn_balance.over.label }}</span>
          <span v-if="primary.turn_balance.over.turn_saturation != null" class="tb-metric">
            饱和 {{ primary.turn_balance.over.turn_saturation.toFixed(2) }}
          </span>
          <span v-if="primary.turn_balance.over.green_utilization != null" class="tb-metric">
            绿利用 {{ Math.round(primary.turn_balance.over.green_utilization * 100) }}%
          </span>
        </div>
        <div v-if="primary.turn_balance.spare" class="tb-row spare">
          <span class="tb-label">绿灯富余</span>
          <span class="tb-val">{{ primary.turn_balance.spare.label }}</span>
          <span v-if="primary.turn_balance.spare.green_utilization != null" class="tb-metric">
            绿利用 {{ Math.round(primary.turn_balance.spare.green_utilization * 100) }}%
            <template v-if="primary.turn_balance.spare_util_threshold != null">
              （阈值 &lt;{{ Math.round(primary.turn_balance.spare_util_threshold * 100) }}%）
            </template>
          </span>
        </div>
      </div>
    </section>

    <section v-if="governance.action_plan?.headline" class="action-plan">
      <h4>数据推导动作</h4>
      <p class="action-headline">{{ governance.action_plan.headline }}</p>
      <p v-if="governance.action_plan.narrative_template" class="action-detail">
        {{ governance.action_plan.narrative_template }}
      </p>
    </section>

    <p
      v-if="governance.match_narrative && governance.match_verdict !== 'insufficient'"
      class="match-line"
    >
      {{ governance.match_narrative }}
    </p>
    <p v-if="!primary && governance.summary" class="summary">{{ governance.summary }}</p>

    <div class="dim-grid">
      <div
        v-for="problem in governance.problems ?? []"
        :key="problem.category"
        class="dim"
        :class="{ active: problem.detected, [`sev-${problem.severity}`]: problem.detected }"
      >
        <span class="dim-label">{{ problem.label }}</span>
        <span class="dim-status">{{ problem.detected ? '命中' : '正常' }}</span>
        <ul v-if="problem.detected && problem.governance" class="dim-governance">
          <li>{{ problem.governance }}</li>
        </ul>
        <ul v-if="problem.evidence?.length" class="dim-evidence">
          <li v-for="(line, i) in problem.evidence" :key="i">{{ line }}</li>
        </ul>
      </div>
    </div>

    <section v-if="governance.expert_rules?.length" class="expert">
      <h4>一线经验依据</h4>
      <ul>
        <li v-for="rule in governance.expert_rules" :key="rule.id">
          <strong>{{ rule.title }}</strong> — {{ rule.text }}
        </li>
      </ul>
    </section>
  </article>
</template>

<style scoped>
.gov-card {
  border: 1px solid rgba(0, 212, 240, 0.18);
  border-radius: 10px;
  padding: 12px;
  background: linear-gradient(145deg, rgba(8, 24, 40, 0.92), rgba(6, 18, 32, 0.88));
}

.gov-head {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 8px;
  align-items: center;
  margin-bottom: 8px;
}

.gov-head h3 {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: rgba(232, 244, 255, 0.95);
}

.eyebrow {
  font-size: 9px;
  letter-spacing: 1.2px;
  color: rgba(0, 229, 255, 0.7);
}

.verdict {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid transparent;
}

.verdict.good {
  color: #6ee7b7;
  border-color: rgba(110, 231, 183, 0.35);
}
.verdict.warn {
  color: #fcd34d;
  border-color: rgba(252, 211, 77, 0.35);
}
.verdict.bad {
  color: #fca5a5;
  border-color: rgba(252, 165, 165, 0.4);
}
.verdict.neutral {
  color: rgba(186, 215, 240, 0.7);
  border-color: rgba(186, 215, 240, 0.2);
}

.match-line,
.summary {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.55;
  color: rgba(200, 225, 245, 0.82);
}

.primary {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: 8px;
  border-left: 3px solid rgba(186, 215, 240, 0.4);
  background: rgba(255, 255, 255, 0.04);
}

.primary.sev-high {
  border-left-color: rgba(248, 113, 113, 0.85);
  background: rgba(127, 29, 29, 0.18);
}

.primary.sev-medium {
  border-left-color: rgba(252, 211, 77, 0.85);
  background: rgba(120, 80, 12, 0.16);
}

.primary.sev-none {
  border-left-color: rgba(110, 231, 183, 0.7);
  background: rgba(6, 78, 59, 0.14);
}

.primary-headline {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.55;
  color: rgba(236, 246, 255, 0.96);
}

.primary-lever {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(200, 225, 245, 0.85);
}

.primary-evidence {
  margin: 6px 0 0;
  padding-left: 16px;
  font-size: 10px;
  line-height: 1.5;
  color: rgba(176, 205, 230, 0.78);
}

.turn-balance {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.tb-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
  font-size: 10px;
}
.tb-label {
  color: rgba(180, 200, 220, 0.65);
  min-width: 52px;
}
.tb-val {
  font-weight: 700;
  color: #e8f6ff;
}
.tb-row.over .tb-val {
  color: #ff9f9f;
}
.tb-row.spare .tb-val {
  color: #9dffb8;
}
.tb-metric {
  font-family: ui-monospace, monospace;
  color: rgba(200, 225, 245, 0.85);
}

.action-plan {
  margin: 10px 0;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid rgba(52, 211, 153, 0.35);
  background: rgba(6, 78, 59, 0.18);
}

.action-plan h4 {
  margin: 0 0 6px;
  font-size: 11px;
  color: rgba(167, 243, 208, 0.9);
}

.action-headline {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: rgba(236, 253, 245, 0.95);
}

.action-detail {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(209, 250, 229, 0.88);
}

.dim-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.dim {
  border-radius: 8px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  opacity: 0.72;
}

.dim.active {
  opacity: 1;
  border-color: rgba(56, 189, 248, 0.35);
  background: rgba(14, 116, 144, 0.12);
}

.dim.sev-high {
  border-color: rgba(248, 113, 113, 0.45);
}

.dim-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: rgba(232, 244, 255, 0.9);
}

.dim-status {
  font-size: 10px;
  color: rgba(148, 196, 230, 0.75);
}

.dim-governance {
  margin: 6px 0 0;
  padding-left: 14px;
  font-size: 10px;
  line-height: 1.45;
  color: rgba(200, 230, 255, 0.88);
  list-style: none;
}

.dim-evidence {
  margin: 6px 0 0;
  padding-left: 14px;
  font-size: 10px;
  line-height: 1.45;
  color: rgba(186, 215, 240, 0.75);
}

.expert {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(0, 212, 240, 0.15);
}

.expert h4 {
  margin: 0 0 6px;
  font-size: 11px;
  color: rgba(0, 229, 255, 0.85);
}

.expert ul {
  margin: 0;
  padding-left: 16px;
  font-size: 10px;
  line-height: 1.5;
  color: rgba(186, 215, 240, 0.78);
}

.expert li {
  margin-bottom: 4px;
}
</style>

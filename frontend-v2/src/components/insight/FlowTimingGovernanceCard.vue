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
</script>

<template>
  <article class="gov-card">
    <header class="gov-head">
      <span class="eyebrow">FLOW × TIMING</span>
      <h3>流量-配时匹配 · 四维诊断</h3>
      <span class="verdict" :class="verdictClass">{{ verdictLabel }}</span>
    </header>

    <p v-if="governance.match_narrative" class="match-line">
      {{ governance.match_narrative }}
    </p>
    <p v-if="governance.summary" class="summary">{{ governance.summary }}</p>

    <div class="dim-grid">
      <div
        v-for="problem in governance.problems ?? []"
        :key="problem.category"
        class="dim"
        :class="{ active: problem.detected, [`sev-${problem.severity}`]: problem.detected }"
      >
        <span class="dim-label">{{ problem.label }}</span>
        <span class="dim-status">{{ problem.detected ? '命中' : '正常' }}</span>
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

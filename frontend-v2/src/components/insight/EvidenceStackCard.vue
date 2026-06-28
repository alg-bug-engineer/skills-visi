<script setup lang="ts">
import { computed } from 'vue'
import type { ProblemEvidence } from '../../types/evidence'
import { sourceTierLabel } from '../../utils/evidencePresentation'

const props = defineProps<{
  evidence: ProblemEvidence
}>()

const chronicRate = computed(() => {
  const c = props.evidence.chronic
  if (!c?.window_days) return null
  return ((c.congested_days ?? 0) / c.window_days) * 100
})

const dowRate = computed(() => {
  const d = props.evidence.dow_pattern
  if (d?.hit_rate != null) return d.hit_rate * 100
  return null
})
</script>

<template>
  <article class="stack-card evidence-card">
    <header class="card-head">
      <div>
        <span class="eyebrow">问题验证</span>
        <h3>数据印证用户描述</h3>
      </div>
    </header>

    <p v-if="evidence.coverage_warning" class="warn">{{ evidence.coverage_warning }}</p>
    <p v-if="evidence.summary" class="summary">{{ evidence.summary }}</p>

    <div class="badges">
      <span v-if="evidence.chronic?.is_chronic" class="badge chronic">
        常发 {{ evidence.chronic.congested_days }}/{{ evidence.chronic.window_days }} 日
      </span>
      <span v-if="evidence.dow_pattern?.dow_label" class="badge dow">
        每逢{{ evidence.dow_pattern.dow_label }}
      </span>
      <span class="badge tier">{{ sourceTierLabel(evidence.source_tier) }}</span>
    </div>

    <div v-if="chronicRate != null" class="meter">
      <div class="meter-top">
        <span>常发命中</span>
        <span>{{ chronicRate.toFixed(0) }}%</span>
      </div>
      <div class="track"><div class="fill chronic" :style="{ width: `${chronicRate}%` }" /></div>
    </div>

    <div v-if="dowRate != null" class="meter">
      <div class="meter-top">
        <span>{{ evidence.dow_pattern?.dow_label }}命中</span>
        <span>{{ dowRate.toFixed(0) }}%</span>
      </div>
      <div class="track"><div class="fill dow" :style="{ width: `${dowRate}%` }" /></div>
    </div>

    <ul v-if="evidence.diagnosis_story?.length" class="story">
      <li v-for="(beat, i) in evidence.diagnosis_story" :key="i">
        <strong>{{ beat.title }}</strong>
        <span>{{ beat.text }}</span>
      </li>
    </ul>

    <p v-if="!evidence.diagnosis_story?.length" class="hint">
      运行饱和度、延误等量化指标见「运行数据」卡。
    </p>
  </article>
</template>

<style scoped>
.stack-card {
  border-radius: 4px;
  padding: 12px 14px;
  background: rgba(0, 12, 26, 0.96);
  color: rgba(226, 246, 255, 0.92);
}

.evidence-card {
  border: 1px solid rgba(255, 194, 102, 0.35);
  border-left: 3px solid #ffc266;
}

.card-head {
  margin-bottom: 8px;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1px;
  color: #ffc266;
}

.card-head h3 {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: #f0f8ff;
}

.warn {
  margin: 0 0 8px;
  padding: 6px 8px;
  font-size: 11px;
  color: #ffc266;
  background: rgba(255, 194, 102, 0.1);
  border: 1px solid rgba(255, 194, 102, 0.3);
}

.summary {
  margin: 0 0 10px;
  font-size: 12px;
  line-height: 1.55;
  color: rgba(220, 240, 255, 0.88);
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.badge {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 2px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(220, 240, 255, 0.8);
}

.badge.chronic {
  color: #ff9b9b;
  border-color: rgba(255, 120, 120, 0.35);
}

.badge.dow {
  color: #ffc266;
}

.meter {
  margin-bottom: 8px;
}

.meter-top {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: rgba(200, 230, 255, 0.55);
  margin-bottom: 3px;
}

.track {
  height: 5px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.fill {
  height: 100%;
}

.fill.chronic {
  background: #ff7b7b;
}

.fill.dow {
  background: #ffc266;
}

.story {
  list-style: none;
  margin: 0 0 10px;
  padding: 0;
  font-size: 11px;
  border-left: 2px solid rgba(255, 194, 102, 0.35);
  padding-left: 8px;
}

.story li {
  margin-bottom: 6px;
  line-height: 1.45;
}

.story strong {
  display: block;
  font-size: 9px;
  color: #ffc266;
  letter-spacing: 0.5px;
  margin-bottom: 2px;
}

.hint {
  margin: 8px 0 0;
  font-size: 10px;
  line-height: 1.5;
  color: rgba(200, 230, 255, 0.45);
}
</style>

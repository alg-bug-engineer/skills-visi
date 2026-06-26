<script setup lang="ts">
import type { TimingProfile } from '../../types/evidence'

defineProps<{
  profile: TimingProfile
}>()

function cycleLabel(issue?: string | null) {
  if (issue === 'too_long') return '周期偏长'
  if (issue === 'too_short') return '周期偏短'
  return '周期正常'
}
</script>

<template>
  <article class="stack-card timing-card">
    <header class="card-head">
      <div>
        <span class="eyebrow">配时画像</span>
        <h3>信号配时适配性</h3>
      </div>
    </header>

    <p v-if="profile.narrative" class="narrative">{{ profile.narrative }}</p>

    <div class="metrics">
      <div class="m-item">
        <span class="m-label">周期</span>
        <span class="m-val">{{ profile.cycle_length?.toFixed(0) ?? '—' }}s</span>
      </div>
      <div class="m-item">
        <span class="m-label">时段方案</span>
        <span class="m-val">{{ profile.period_count ?? '—' }}</span>
      </div>
      <div class="m-item">
        <span class="m-label">周期状态</span>
        <span class="m-val" :class="{ warn: profile.cycle_issue }">
          {{ cycleLabel(profile.cycle_issue) }}
        </span>
      </div>
    </div>

    <ul v-if="profile.deficit_turns?.length" class="deficit">
      <li v-for="t in profile.deficit_turns" :key="t.label">
        <span>{{ t.label }}</span>
        <span>
          计划 {{ t.green_time_plan }}s &lt; 最小 {{ t.min_green_time }}s
        </span>
      </li>
    </ul>

    <p v-if="profile.flow_green_fit?.narrative" class="fit">
      {{ profile.flow_green_fit.narrative }}
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

.timing-card {
  border: 1px solid rgba(167, 139, 250, 0.35);
  border-left: 3px solid #a78bfa;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1px;
  color: #c4b5fd;
}

.card-head h3 {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}

.narrative,
.fit {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.55;
  color: rgba(220, 240, 255, 0.85);
}

.metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 10px;
}

.m-item {
  text-align: center;
  padding: 6px 4px;
  background: rgba(0, 16, 28, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 2px;
}

.m-label {
  display: block;
  font-size: 9px;
  color: rgba(200, 230, 255, 0.5);
}

.m-val {
  font-size: 12px;
  font-weight: 700;
  font-family: 'Courier New', monospace;
  color: #c4b5fd;
}

.m-val.warn {
  color: #ffc266;
}

.deficit {
  list-style: none;
  margin: 10px 0 0;
  padding: 0;
  font-size: 10px;
}

.deficit li {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: #ffc266;
}
</style>

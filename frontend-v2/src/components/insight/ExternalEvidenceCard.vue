<script setup lang="ts">
import type { ExternalEvidence } from '../../types/evidence'

defineProps<{
  external: ExternalEvidence
}>()
</script>

<template>
  <article class="stack-card external-card">
    <header class="card-head">
      <div>
        <span class="eyebrow">外部证据</span>
        <h3>投诉 · 调研</h3>
      </div>
    </header>

    <p v-if="external.narrative" class="narrative">{{ external.narrative }}</p>

    <div v-if="external.complaints?.length" class="block">
      <h4>民意投诉</h4>
      <ul>
        <li v-for="c in external.complaints.slice(0, 4)" :key="c.type">
          <span>{{ c.type }}</span>
          <span class="cnt">{{ c.count }} 件</span>
        </li>
      </ul>
    </div>

    <div v-if="external.manual_survey?.length" class="block">
      <h4>信控调查</h4>
      <p class="desc">{{ external.manual_survey[0].desc }}</p>
    </div>

    <div v-if="external.field_survey?.length" class="block">
      <h4>交通组织调研</h4>
      <p class="desc">{{ external.field_survey[0].desc }}</p>
    </div>
  </article>
</template>

<style scoped>
.stack-card {
  border-radius: 4px;
  padding: 12px 14px;
  background: rgba(0, 12, 26, 0.96);
  color: rgba(226, 246, 255, 0.92);
}

.external-card {
  border: 1px solid rgba(251, 113, 133, 0.35);
  border-left: 3px solid #fb7185;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 1px;
  color: #fda4af;
}

.card-head h3 {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}

.narrative {
  margin: 8px 0 0;
  font-size: 11px;
  line-height: 1.55;
}

.block {
  margin-top: 10px;
}

.block h4 {
  margin: 0 0 4px;
  font-size: 10px;
  color: rgba(200, 230, 255, 0.55);
}

ul {
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 11px;
}

li {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.cnt {
  font-family: 'Courier New', monospace;
  color: #fb7185;
}

.desc {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: rgba(220, 240, 255, 0.8);
}
</style>

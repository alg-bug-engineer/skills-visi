<script setup lang="ts">
import { computed } from 'vue'
import type { ProblemEvidence } from '../../types/evidence'
import { buildEvidenceListItems } from '../../utils/channelizationCopy'

const props = defineProps<{
  evidence: ProblemEvidence
}>()

const items = computed(() => buildEvidenceListItems(props.evidence))
</script>

<template>
  <aside class="evidence-note" aria-label="问题验证摘要">
    <span class="eyebrow">问题验证</span>
    <ul class="evidence-list">
      <li v-for="(item, index) in items" :key="index">{{ item }}</li>
    </ul>
  </aside>
</template>

<style scoped>
.evidence-note {
  max-width: min(300px, 42vw);
  max-height: 100%;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(8, 12, 20, 0.9);
  border: 1px solid rgba(255, 194, 102, 0.35);
  border-left: 3px solid #ffc266;
  overflow-y: auto;
  overscroll-behavior: contain;
  pointer-events: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 194, 102, 0.35) transparent;
}

.evidence-note::-webkit-scrollbar {
  width: 4px;
}

.evidence-note::-webkit-scrollbar-thumb {
  border-radius: 2px;
  background: rgba(255, 194, 102, 0.35);
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 0.8px;
  color: #ffc266;
  margin-bottom: 4px;
}

.evidence-list {
  margin: 0;
  padding: 0 0 0 1.15em;
  list-style: disc;
}

.evidence-list li {
  font-size: 11px;
  line-height: 1.55;
  color: rgba(226, 246, 255, 0.92);
}

.evidence-list li + li {
  margin-top: 4px;
}
</style>

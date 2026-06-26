<script setup lang="ts">
import { computed } from 'vue'
import type { GovernanceSuggestionPayload } from '../../types/presentation'
import { buildSuggestionListItems } from '../../utils/channelizationCopy'

const props = defineProps<{
  suggestion?: GovernanceSuggestionPayload | null
}>()

const items = computed(() => buildSuggestionListItems(props.suggestion))
</script>

<template>
  <aside v-if="items.length" class="suggestion-note" aria-label="治理建议">
    <span class="eyebrow">治理建议</span>
    <ul class="suggestion-list">
      <li v-for="(item, index) in items" :key="index">{{ item }}</li>
    </ul>
  </aside>
</template>

<style scoped>
.suggestion-note {
  max-width: min(360px, 48vw);
  min-height: 90px;
  padding: 12px 14px;
  border-radius: 6px;
  background: rgba(8, 12, 20, 0.9);
  border: 1px solid rgba(0, 212, 240, 0.35);
  border-right: 3px solid #00e5ff;
  pointer-events: none;
}

.eyebrow {
  display: block;
  font-size: 9px;
  letter-spacing: 0.8px;
  color: #00e5ff;
  margin-bottom: 8px;
}

.suggestion-list {
  margin: 0;
  padding: 0 0 0 1.15em;
  list-style: disc;
}

.suggestion-list li {
  font-size: 11px;
  line-height: 2.3;
  letter-spacing: 0.06em;
  color: rgba(226, 246, 255, 0.92);
}

.suggestion-list li + li {
  margin-top: 2px;
}
</style>

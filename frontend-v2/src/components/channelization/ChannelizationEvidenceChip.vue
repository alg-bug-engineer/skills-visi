<script setup lang="ts">
import type { ProblemEvidence } from '../../types/evidence'
import { sourceTierLabel } from '../../utils/evidencePresentation'

defineProps<{
  evidence: ProblemEvidence
}>()
</script>

<template>
  <article class="ev-chip">
    <header>
      <span class="eyebrow">问题验证</span>
      <h4>数据印证用户描述</h4>
    </header>
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
  </article>
</template>

<style scoped>
.ev-chip {
  flex: 0 0 auto;
  min-width: 200px;
  max-width: 280px;
  padding: 8px 10px;
  border-radius: 6px;
  background: rgba(0, 12, 26, 0.92);
  border: 1px solid rgba(255, 194, 102, 0.35);
  border-left: 3px solid #ffc266;
}

header h4 {
  margin: 2px 0 0;
  font-size: 11px;
  font-weight: 600;
  color: #f0f8ff;
}

.eyebrow {
  font-size: 8px;
  letter-spacing: 0.8px;
  color: #ffc266;
}

.summary {
  margin: 6px 0 0;
  font-size: 10px;
  line-height: 1.45;
  color: rgba(220, 240, 255, 0.82);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.badge {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 2px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(220, 240, 255, 0.75);
}

.badge.chronic {
  color: #ff9b9b;
  border-color: rgba(255, 120, 120, 0.35);
}

.badge.dow {
  color: #ffc266;
}
</style>

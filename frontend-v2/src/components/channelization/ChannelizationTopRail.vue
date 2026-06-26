<script setup lang="ts">
import type { FlowTimingGovernance, ProblemEvidence } from '../../types/evidence'
import ChannelizationEvidenceChip from './ChannelizationEvidenceChip.vue'
import GovernanceDimChips from './GovernanceDimChips.vue'

defineProps<{
  evidence?: ProblemEvidence | null
  showEvidence?: boolean
  governance?: FlowTimingGovernance | null
  showGovernance?: boolean
}>()
</script>

<template>
  <div v-if="showEvidence || showGovernance" class="top-rail">
    <ChannelizationEvidenceChip v-if="showEvidence && evidence" :evidence="evidence" />
    <GovernanceDimChips
      v-if="showGovernance && governance"
      :governance="governance"
    />
  </div>
</template>

<style scoped>
.top-rail {
  display: flex;
  flex-wrap: nowrap;
  align-items: stretch;
  gap: 10px;
  padding: 8px 12px;
  overflow-x: auto;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.22);
  flex-shrink: 0;
}

.top-rail::-webkit-scrollbar {
  height: 4px;
}

.top-rail::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
}
</style>

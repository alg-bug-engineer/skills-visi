<script setup lang="ts">
import type { PlanTimingEvidence } from '@/api/types'

defineProps<{ timing?: PlanTimingEvidence | null }>()
</script>

<template>
  <section class="audit">
    <h4>优化审计</h4>
    <dl>
      <div>
        <dt>求解器</dt>
        <dd>{{ timing?.meta?.solver || '—' }}</dd>
      </div>
      <div>
        <dt>总流量</dt>
        <dd>{{ timing?.meta?.total_turn_flow_vph ?? '—' }} vph</dd>
      </div>
      <div>
        <dt>最大相位饱和度</dt>
        <dd>{{ timing?.meta?.max_phase_saturation != null ? (timing.meta.max_phase_saturation * 100).toFixed(1) + '%' : '—' }}</dd>
      </div>
    </dl>
    <p v-if="timing?.reason" class="reason">{{ timing.reason }}</p>
    <ul v-if="timing?.missing_fields?.length" class="missing">
      <li v-for="field in timing.missing_fields" :key="field">{{ field }}</li>
    </ul>
    <ul v-if="timing?.meta?.notes?.length" class="notes">
      <li v-for="note in timing.meta.notes.slice(0, 5)" :key="note">{{ note }}</li>
    </ul>
  </section>
</template>

<style scoped>
.audit {
  padding-top: 10px;
  border-top: 1px solid rgba(138, 160, 180, 0.22);
}
h4 {
  margin: 0 0 8px;
  color: var(--text);
  font-size: 13px;
}
dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}
dt {
  color: var(--text-mute);
  font-size: 11px;
}
dd {
  margin: 2px 0 0;
  color: var(--text);
  font-size: 12px;
  word-break: break-word;
}
.reason {
  color: var(--evidence);
}
.missing,
.notes {
  margin: 8px 0 0;
  padding-left: 18px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.45;
}
</style>

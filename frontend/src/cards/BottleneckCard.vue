<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const dd = computed(() => store.diagnosis?.downstream_diagnosis ?? null)
const canAddGreen = computed(() => dd.value?.can_simple_add_green)
</script>

<template>
  <BaseCard v-if="dd" title="瓶颈判断：能不能加绿" :act="4" tone="evidence">
    <div class="answer" :class="canAddGreen === false ? 'no' : canAddGreen === true ? 'yes' : 'unknown'">
      <span class="answer__k">能否直接加绿放行？</span>
      <span class="answer__v">
        {{ canAddGreen === false ? '否 · 下游接不住' : canAddGreen === true ? '是 · 本地可释放' : '需进一步判断' }}
      </span>
    </div>

    <p v-if="dd.release_answer" class="lead">{{ dd.release_answer }}</p>
    <p v-if="dd.narrative" class="narr">{{ dd.narrative }}</p>

    <ul v-if="dd.judgment_criteria?.length" class="crit">
      <li v-for="(c, i) in dd.judgment_criteria" :key="i">{{ c }}</li>
    </ul>

    <p v-if="dd.expert_question" class="q">思考：{{ dd.expert_question }}</p>
  </BaseCard>
</template>

<style scoped>
.answer {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  margin-bottom: 10px;
  border: 1px solid var(--evidence);
  background: var(--evidence-dim);
}
.answer.no {
  border-color: var(--alarm);
  background: var(--alarm-dim);
}
.answer.yes {
  border-color: var(--protected);
  background: var(--protected-dim);
}
.answer__k {
  font-size: 11px;
  color: var(--text-mute);
}
.answer__v {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}
.lead {
  margin: 0 0 8px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.55;
}
.narr {
  margin: 0 0 8px;
  color: var(--text-dim);
  font-size: 12.5px;
  line-height: 1.55;
}
.crit {
  margin: 8px 0;
  padding-left: 18px;
}
.crit li {
  margin: 3px 0;
  font-size: 12.5px;
  color: var(--text-dim);
}
.q {
  margin: 8px 0 0;
  padding: 8px 10px;
  border-left: 2px solid var(--primary);
  background: var(--primary-dim);
  font-size: 12.5px;
  color: var(--text);
  border-radius: 0 6px 6px 0;
}
</style>

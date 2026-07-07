<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()
const dd = computed(() => store.diagnosis?.downstream_diagnosis ?? null)
const canAddGreen = computed(() => dd.value?.can_simple_add_green)
const expertCheck = computed(() => productCopy(dd.value?.expert_question).replace(/^核验项：?/, ''))
</script>

<template>
  <BaseCard v-if="dd" title="放行策略判别" :act="4" tone="evidence">
    <div class="answer" :class="canAddGreen === false ? 'no' : canAddGreen === true ? 'yes' : 'unknown'">
      <span class="answer__k">目标方向放行策略</span>
      <span class="answer__v">
        {{ canAddGreen === false ? '需联控 · 下游承接不足' : canAddGreen === true ? '可小步释放' : '需继续核验' }}
      </span>
    </div>

    <p v-if="dd.release_answer" class="lead">{{ productCopy(dd.release_answer) }}</p>
    <p v-if="dd.narrative" class="narr">{{ productCopy(dd.narrative) }}</p>

    <ul v-if="dd.judgment_criteria?.length" class="crit">
      <li v-for="(c, i) in dd.judgment_criteria" :key="i">{{ productCopy(String(c)) }}</li>
    </ul>

    <p v-if="expertCheck" class="q">核验项：{{ expertCheck }}</p>
  </BaseCard>
</template>

<style scoped>
.answer {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 0;
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
  border: 1px solid rgba(146, 161, 181, 0.4);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12.5px;
  color: var(--text);
  border-radius: 0;
}
</style>

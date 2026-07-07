<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()
const s = computed(() => store.strategy?.strategy ?? null)
const pkg = computed(() => store.strategy?.strategy_package ?? null)
const rollback = computed(() => {
  const rr = s.value?.trigger_exit_rules as { rollback_condition?: string } | undefined
  return rr?.rollback_condition ?? null
})
</script>

<template>
  <BaseCard v-if="s" title="策略包" :act="7" tone="protected">
    <p v-if="pkg" class="pkg">策略包：{{ productCopy(pkg) }}</p>

    <ul class="strategy-list">
      <li v-for="(x, i) in s.recommended ?? []" :key="i">{{ productCopy(x) }}</li>
    </ul>

    <div v-if="s.hard_constraints?.length" class="hard">
      <span class="hard__hd">红线</span>
      <div class="hard__tags">
        <span v-for="(c, i) in s.hard_constraints" :key="i" class="tag">{{ productCopy(c) }}</span>
      </div>
    </div>

    <p v-if="rollback" class="rollback">回滚触发：{{ productCopy(rollback) }}</p>
  </BaseCard>
</template>

<style scoped>
.pkg {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--protected);
  font-weight: 600;
}
.strategy-list {
  margin: 0;
  padding-left: 16px;
}
.strategy-list li {
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-dim);
  margin: 4px 0;
}
.hard {
  margin-top: 10px;
}
.hard__hd {
  font-size: 11px;
  color: var(--alarm);
  font-weight: 700;
}
.hard__tags {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.tag {
  padding: 2px 8px;
  border-radius: 0;
  font-size: 11.5px;
  color: var(--alarm);
  background: var(--alarm-dim);
  border: 1px solid rgba(255, 80, 80, 0.4);
}
.rollback {
  margin: 10px 0 0;
  font-size: 11.5px;
  color: var(--evidence);
  padding: 6px 8px;
  border-left: 2px solid var(--evidence);
  background: var(--evidence-dim);
  border-radius: 0;
}
</style>

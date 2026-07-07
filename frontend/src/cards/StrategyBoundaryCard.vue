<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const s = computed(() => store.strategy?.strategy ?? null)
const pkg = computed(() => store.strategy?.strategy_package ?? null)
const rollback = computed(() => {
  const rr = s.value?.trigger_exit_rules as { rollback_condition?: string } | undefined
  return rr?.rollback_condition ?? null
})
</script>

<template>
  <BaseCard v-if="s" title="策略边界（可做 / 不可做）" :act="7" tone="protected">
    <p v-if="pkg" class="pkg">策略包：{{ pkg }}</p>

    <div class="cols">
      <div class="col ok">
        <span class="col__hd">推荐</span>
        <ul>
          <li v-for="(x, i) in s.recommended ?? []" :key="i">{{ x }}</li>
        </ul>
      </div>
      <div class="col no">
        <span class="col__hd">不推荐</span>
        <ul>
          <li v-for="(x, i) in s.not_recommended ?? []" :key="i">{{ x }}</li>
        </ul>
      </div>
    </div>

    <div v-if="s.hard_constraints?.length" class="hard">
      <span class="hard__hd">硬约束（红线）</span>
      <div class="hard__tags">
        <span v-for="(c, i) in s.hard_constraints" :key="i" class="tag">{{ c }}</span>
      </div>
    </div>

    <p v-if="rollback" class="rollback">回滚触发：{{ rollback }}</p>
  </BaseCard>
</template>

<style scoped>
.pkg {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--protected);
  font-weight: 600;
}
.cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.col {
  padding: 8px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
}
.col__hd {
  font-size: 11px;
  font-weight: 700;
  display: block;
  margin-bottom: 6px;
}
.col.ok .col__hd {
  color: var(--protected);
}
.col.no .col__hd {
  color: var(--alarm);
}
.col ul {
  margin: 0;
  padding-left: 16px;
}
.col li {
  font-size: 11.5px;
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
  border-radius: 6px;
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
  border-radius: 0 6px 6px 0;
}
</style>

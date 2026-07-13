<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { t, directionMovement } from '@/labels/enums'
import { productCopy } from '@/utils/productCopy'
import { ticketTimeLabel, ticketConstraintList } from '@/utils/ticketCopy'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const tk = computed(() => store.ticket)

const constraintList = computed(() => ticketConstraintList(tk.value))
</script>

<template>
  <BaseCard v-if="tk" title="诊断任务工单" :act="1">
    <ul class="nlu-list">
      <li><span class="k">原始问题</span><span class="v raw">{{ store.userInput || '—' }}</span></li>
      <li><span class="k">对象</span><span class="v">{{ t('object_type', tk.object_type) }}</span></li>
      <li>
        <span class="k">路口</span>
        <span class="v">
          {{ productCopy(tk.intersection_name) || '—' }}
          <span v-if="tk.inter_id" class="id">{{ tk.inter_id }}</span>
        </span>
      </li>
      <li><span class="k">时间</span><span class="v">{{ ticketTimeLabel(tk) }}</span></li>
      <li><span class="k">方向转向</span><span class="v">{{ directionMovement(tk.direction, tk.movement) }}</span></li>
      <li><span class="k">问题</span><span class="v"><span class="tag tag--alarm">{{ t('problem_type', tk.problem_type) }}</span></span></li>
      <li><span class="k">治理目标</span><span class="v">{{ t('governance_goal', tk.governance_goal) }}</span></li>
    </ul>

    <div v-if="constraintList.length" class="constraints">
      <span class="lbl">约束</span>
      <span v-for="c in constraintList" :key="c" class="tag tag--evidence">{{ productCopy(t('constraint', c)) }}</span>
    </div>
  </BaseCard>
</template>

<style scoped>
.nlu-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.nlu-list li {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 2px 0;
  min-width: 0;
}
.nlu-list li + li {
  border-top: 1px solid rgba(146, 161, 181, 0.12);
}
.nlu-list .k {
  flex: 0 0 60px;
  font-size: 11px;
  color: var(--text-mute);
}
.nlu-list .v {
  flex: 1 1 auto;
  min-width: 0;
  color: var(--text);
  font-size: 13px;
  word-break: break-word;
}
.nlu-list .v.raw {
  color: var(--text-dim);
  line-height: 1.4;
}
.nlu-list .v .id {
  margin-left: 4px;
  font-size: 11px;
  color: var(--text-mute);
}
.tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.6;
}
.tag--alarm {
  color: var(--alarm);
  background: var(--alarm-dim);
  border: 1px solid var(--alarm);
}
.tag--evidence {
  color: var(--evidence);
  background: var(--evidence-dim);
  border: 1px solid rgba(245, 166, 35, 0.4);
  margin: 2px 4px 2px 0;
}
.constraints {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.constraints .lbl {
  font-size: 11px;
  color: var(--text-mute);
  margin-right: 4px;
}
</style>

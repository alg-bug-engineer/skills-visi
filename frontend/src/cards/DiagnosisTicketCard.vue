<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { t, directionMovement } from '@/labels/enums'
import { pct } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const tk = computed(() => store.ticket)
</script>

<template>
  <BaseCard v-if="tk" title="诊断任务工单" :act="1">
    <dl class="kv">
      <div><dt>对象</dt><dd>{{ t('object_type', tk.object_type) }}</dd></div>
      <div><dt>路口</dt><dd>{{ productCopy(tk.intersection_name) || '—' }}</dd></div>
      <div><dt>时间</dt><dd>{{ tk.time_range ?? '—' }}（{{ t('period', tk.period) }}）</dd></div>
      <div><dt>方向转向</dt><dd>{{ directionMovement(tk.direction, tk.movement) }}</dd></div>
      <div>
        <dt>问题</dt>
        <dd><span class="tag tag--alarm">{{ t('problem_type', tk.problem_type) }}</span></dd>
      </div>
      <div><dt>治理目标</dt><dd>{{ t('governance_goal', tk.governance_goal) }}</dd></div>
    </dl>

    <div v-if="tk.constraints?.length" class="constraints">
      <span class="lbl">约束</span>
      <span v-for="c in tk.constraints" :key="c" class="tag tag--evidence">{{ productCopy(t('constraint', c)) }}</span>
    </div>

    <div class="conf">
      <span>解析置信度 {{ pct(tk.match_confidence) }}</span>
      <span class="mute">· {{ t('match_method', tk.match_method) }}</span>
    </div>
  </BaseCard>
</template>

<style scoped>
.kv {
  margin: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 12px;
}
.kv > div {
  min-width: 0;
}
.kv dt {
  font-size: 11px;
  color: var(--text-mute);
  margin-bottom: 2px;
}
.kv dd {
  margin: 0;
  color: var(--text);
  font-size: 13px;
  word-break: break-word;
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
  margin-top: 12px;
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
.conf {
  margin-top: 10px;
  font-size: 12px;
  color: var(--primary);
}
.conf .mute {
  color: var(--text-mute);
}
</style>

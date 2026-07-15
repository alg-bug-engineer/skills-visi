<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { num, meters } from '@/utils/format'
import BaseCard from './BaseCard.vue'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()
const a = computed(() => store.diagnosis?.arterial_analysis ?? null)
</script>

<template>
  <BaseCard v-if="a" title="干线溯源扫描" :act="6" tone="evidence">
    <p class="hint" data-testid="corridor-metric-hint">
      地图路段百分比 = 该路段车辆经目标进口的占比；路口标签为转向分担与排队/饱和/绿灯指标。
    </p>

    <div class="flow">
      <div class="flow__node up">
        <span class="v us-mono">{{ num(a.upstream_arrival_flow_vph) }}</span>
        <span class="k">上游到达</span>
        <span class="u">辆/小时，进入目标方向的上游来车量</span>
      </div>
      <div class="flow__arrow">➜</div>
      <div class="flow__node target">
        <span class="v us-mono">{{ meters(a.target_remaining_storage_m) }}</span>
        <span class="k">目标剩余蓄车</span>
        <span class="u">目标进口道还能再容纳的排队长度</span>
      </div>
      <div class="flow__arrow">➜</div>
      <div class="flow__node down">
        <span class="v us-mono">{{ num(a.upstream_release_intensity_vph) }}</span>
        <span class="k">放行强度</span>
        <span class="u">辆/小时，上游信号实际放出的车流强度</span>
      </div>
    </div>

    <ul class="judge">
      <li :class="a.need_upstream_metering ? 'on' : ''">
        <span class="mark" />上游控流 {{ a.need_upstream_metering ? '需要' : '不需要' }}
      </li>
      <li :class="a.need_downstream_dissipation_first ? 'on' : ''">
        <span class="mark" />下游先消散 {{ a.need_downstream_dissipation_first ? '需要' : '不需要' }}
      </li>
      <li v-if="a.phase_offset_match">
        <span class="mark" />协调数据：{{ productCopy(a.phase_offset_match) }}
      </li>
    </ul>

    <p v-if="a.summary" class="summary">{{ productCopy(a.summary) }}</p>
  </BaseCard>
</template>

<style scoped>
.hint {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-left: 2px solid var(--evidence);
  background: rgba(255, 255, 255, 0.03);
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--text-dim);
}
.flow {
  display: flex;
  align-items: stretch;
  gap: 6px;
  margin-bottom: 12px;
}
.flow__node {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 4px;
  border-radius: 0;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
}
.flow__node.up {
  border-color: rgba(245, 166, 35, 0.4);
}
.flow__node.target {
  border-color: var(--primary);
}
.flow__node .v {
  font-size: 15px;
  color: var(--text);
}
.flow__node .k {
  font-size: 10px;
  color: var(--text-mute);
  text-align: center;
}
.flow__node .u {
  font-size: 10px;
  line-height: 1.35;
  color: var(--text-mute);
  text-align: center;
  opacity: 0.9;
}
.flow__arrow {
  align-self: center;
  color: var(--evidence);
}
.judge {
  list-style: none;
  margin: 0 0 10px;
  padding: 0;
}
.judge li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--text-dim);
  padding: 3px 0;
}
.judge .mark {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-mute);
}
.judge li.on {
  color: var(--alarm);
}
.judge li.on .mark {
  background: var(--alarm);
  box-shadow: var(--glow-alarm);
}
.summary {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text);
  padding: 8px 10px;
  background: var(--evidence-dim);
  border-radius: 0;
}
</style>

<script setup lang="ts">
import type { ScanRecord } from '../types/scan'

defineProps<{ pilots: ScanRecord[]; selectedId?: string | null }>()
const emit = defineEmits<{ (e: 'locate', record: ScanRecord): void }>()
</script>

<template>
  <div class="rank">
    <div class="rank-head">
      <span>试点推荐榜</span>
      <small>配时可解 · 按潜力排序</small>
    </div>
    <div v-if="!pilots.length" class="empty">暂无配时可解候选</div>
    <ol class="list">
      <li
        v-for="(p, i) in pilots"
        :key="p.inter_id + p.period"
        :class="{ active: selectedId === p.inter_id }"
        @click="emit('locate', p)"
      >
        <span class="idx">{{ i + 1 }}</span>
        <span class="name">{{ p.inter_name }}</span>
        <span class="meta">{{ p.period }} · 饱和{{ p.metrics.saturation_max?.toFixed(2) ?? '—' }}</span>
        <span class="score">{{ p.pilot_score?.toFixed(0) ?? '—' }}</span>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.rank {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.rank-head {
  padding: 12px 14px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
.rank-head span {
  font-weight: 700;
}
.rank-head small {
  color: #8b97a7;
}
.empty {
  padding: 20px;
  color: #8b97a7;
  text-align: center;
}
.list {
  margin: 0;
  padding: 0;
  list-style: none;
  overflow-y: auto;
}
.list li {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  grid-template-rows: auto auto;
  gap: 2px 8px;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
}
.list li:hover,
.list li.active {
  background: rgba(47, 155, 255, 0.12);
}
.idx {
  grid-row: 1 / 3;
  font-size: 16px;
  font-weight: 700;
  color: #2f9bff;
  text-align: center;
}
.name {
  font-size: 13px;
}
.meta {
  grid-column: 2;
  color: #8b97a7;
  font-size: 11px;
}
.score {
  grid-row: 1 / 3;
  font-size: 18px;
  font-weight: 700;
  color: #2f9bff;
}
</style>

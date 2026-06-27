<script setup lang="ts">
import { computed } from 'vue'
import type { CorridorScanState } from '../../types/corridor'
import { findCorridorIntersection, sortCorridorIntersections } from '../../types/corridor'

const props = defineProps<{
  corridor: CorridorScanState
}>()

const emit = defineEmits<{
  select: [interId: string]
}>()

const sorted = computed(() => sortCorridorIntersections(props.corridor.intersections))

const selected = computed(() =>
  findCorridorIntersection(props.corridor, props.corridor.selectedInterId ?? ''),
)

function severityClass(sev?: string): string {
  if (sev === 'high') return 'sev-high'
  if (sev === 'medium') return 'sev-medium'
  if (sev === 'low') return 'sev-low'
  return 'sev-unknown'
}

function formatSat(item: (typeof sorted.value)[number]): string {
  const sat = item.metrics?.saturation_max
  if (!item.has_data || sat == null) return '—'
  return Number(sat).toFixed(2)
}

function shortName(name: string): string {
  return name.length > 18 ? `${name.slice(0, 17)}…` : name
}
</script>

<template>
  <aside class="corridor-sidebar">
    <header class="sidebar-head">
      <p class="road-name">{{ corridor.lineName }}</p>
      <p class="time-label">{{ corridor.timePeriodLabel || '时段' }}</p>
    </header>

    <div class="list-head">
      <span>路口</span>
      <span>饱和度</span>
    </div>

    <ul class="inter-list">
      <li
        v-for="item in sorted"
        :key="item.inter_id"
        class="inter-row"
        :class="[
          severityClass(item.severity),
          { selected: item.inter_id === corridor.selectedInterId, 'no-data': !item.has_data },
        ]"
        @click="emit('select', item.inter_id)"
      >
        <span class="rank">{{ item.rank != null ? `#${item.rank}` : '·' }}</span>
        <span class="name" :title="item.inter_name">{{ shortName(item.inter_name) }}</span>
        <span class="sat">{{ formatSat(item) }}</span>
      </li>
    </ul>

    <section v-if="selected" class="detail-panel">
      <h3>{{ selected.inter_name }}</h3>
      <dl>
        <div>
          <dt>饱和度</dt>
          <dd>{{ formatSat(selected) }}</dd>
        </div>
        <div>
          <dt>运行水平</dt>
          <dd>{{ selected.metrics?.level_label || selected.annotation || '暂无数据' }}</dd>
        </div>
        <div v-if="selected.metrics?.unbalance_index != null">
          <dt>失衡指数</dt>
          <dd>{{ Number(selected.metrics.unbalance_index).toFixed(2) }}</dd>
        </div>
        <div v-if="selected.rank != null">
          <dt>拥堵排名</dt>
          <dd>第 {{ selected.rank }} 名</dd>
        </div>
      </dl>
      <p v-if="!selected.has_data" class="hint">该路口当前时段暂无运行数据</p>
    </section>
  </aside>
</template>

<style scoped>
.corridor-sidebar {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  background: rgba(0, 10, 18, 0.96);
  border-right: 1px solid rgba(0, 212, 240, 0.14);
}

.sidebar-head {
  padding: 14px 14px 10px;
  border-bottom: 1px solid rgba(0, 212, 240, 0.1);
}

.road-name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #e8f4ff;
}

.time-label {
  margin: 4px 0 0;
  font-size: 11px;
  color: rgba(0, 229, 255, 0.65);
}

.list-head {
  display: grid;
  grid-template-columns: 28px 1fr 52px;
  gap: 6px;
  padding: 8px 14px 6px;
  font-size: 10px;
  letter-spacing: 0.4px;
  color: rgba(180, 210, 235, 0.45);
  text-transform: uppercase;
}

.inter-list {
  list-style: none;
  margin: 0;
  padding: 0 8px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.inter-row {
  display: grid;
  grid-template-columns: 28px 1fr 52px;
  gap: 6px;
  align-items: center;
  padding: 8px 6px;
  margin-bottom: 4px;
  border-radius: 4px;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.inter-row:hover {
  background: rgba(0, 212, 240, 0.06);
}

.inter-row.selected {
  background: rgba(0, 212, 240, 0.12);
  border-color: rgba(0, 229, 255, 0.35);
}

.inter-row.sev-high .sat {
  color: #ff8a80;
}

.inter-row.sev-medium .sat {
  color: #ffb74d;
}

.inter-row.sev-low .sat {
  color: #81c784;
}

.inter-row.no-data {
  opacity: 0.65;
}

.rank {
  font-size: 11px;
  color: rgba(0, 229, 255, 0.7);
  font-variant-numeric: tabular-nums;
}

.name {
  font-size: 12px;
  color: rgba(220, 235, 255, 0.88);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.sat {
  font-size: 12px;
  font-weight: 600;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: rgba(200, 220, 240, 0.75);
}

.detail-panel {
  padding: 12px 14px 16px;
  border-top: 1px solid rgba(0, 212, 240, 0.12);
  background: rgba(0, 6, 12, 0.55);
}

.detail-panel h3 {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: #e8f4ff;
  line-height: 1.35;
}

.detail-panel dl {
  margin: 0;
  display: grid;
  gap: 6px;
}

.detail-panel dl div {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
}

.detail-panel dt {
  color: rgba(180, 210, 235, 0.55);
}

.detail-panel dd {
  margin: 0;
  color: rgba(230, 245, 255, 0.92);
  font-variant-numeric: tabular-nums;
}

.hint {
  margin: 10px 0 0;
  font-size: 11px;
  color: rgba(255, 180, 120, 0.75);
}
</style>

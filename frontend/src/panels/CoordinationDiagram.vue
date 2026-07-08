<script setup lang="ts">
import { computed } from 'vue'
import type { Coordination, CoordinationNode } from '@/api/types'

const props = defineProps<{ coordination?: Coordination | null }>()

const available = computed(() => Boolean(props.coordination?.available))
const nodes = computed<CoordinationNode[]>(() => props.coordination?.nodes ?? [])
const displayNodes = computed(() => {
  const byRole = new Map<CoordinationNode['role'], CoordinationNode>()
  for (const node of nodes.value) {
    if (!byRole.has(node.role)) byRole.set(node.role, node)
  }
  return (['upstream', 'target', 'downstream'] as const)
    .map((role) => byRole.get(role))
    .filter((node): node is CoordinationNode => Boolean(node))
})

function roleLabel(role: string): string {
  return role === 'upstream' ? '上游' : role === 'downstream' ? '下游' : '目标'
}

function nodeFields(n: CoordinationNode): string[] {
  const fields: string[] = []
  if (n.spacing_m) fields.push(`间距 ${Math.round(n.spacing_m)}m`)
  if (n.offset_abs_s !== null) fields.push(`相位 ${n.offset_abs_s}s`)
  if (n.phase_diff_s !== null) fields.push(`相位差 ${n.phase_diff_s > 0 ? '+' : ''}${n.phase_diff_s}s`)
  if (n.travel_time_s !== null) fields.push(`行程 ${n.travel_time_s}s`)
  if (n.travel_speed_kmh !== null) fields.push(`${n.travel_speed_kmh}km/h`)
  return fields
}
</script>

<template>
  <div class="coord" data-testid="coordination-diagram">
    <template v-if="available">
      <ul class="coord__nodes">
        <li
          v-for="n in displayNodes"
          :key="'n' + n.role + n.inter_id"
          :class="{ target: n.role === 'target' }"
          data-testid="coordination-node-row"
        >
          <span class="nm">{{ roleLabel(n.role) }} · {{ n.inter_name ?? n.inter_id ?? '—' }}</span>
          <span class="fields">
            <b v-for="field in nodeFields(n)" :key="field">{{ field }}</b>
          </span>
        </li>
      </ul>
    </template>

    <p v-else class="coord__note">
      {{ coordination?.reason ? `暂不绘制协调图：${coordination.reason}` : '后端未返回协调数据，暂不绘制协调图。' }}
    </p>
  </div>
</template>

<style scoped>
.coord {
  min-height: 64px;
}
.coord__nodes {
  margin: 0;
  padding: 0;
  list-style: none;
}
.coord__nodes li {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 0;
  border-bottom: 1px solid rgba(146, 161, 181, 0.12);
}
.coord__nodes li:last-child {
  border-bottom: 0;
}
.coord__nodes li.target .nm {
  color: var(--primary);
}
.nm {
  min-width: 104px;
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}
.fields {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  color: var(--text-mute);
  font-size: 11px;
  text-align: right;
}
.fields b {
  font-weight: 500;
}
.coord__note {
  margin: 0;
  font-size: 12px;
  color: var(--text-mute);
}
</style>

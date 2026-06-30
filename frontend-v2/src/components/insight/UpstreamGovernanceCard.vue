<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { UpstreamTreeView, UpstreamTreeNode } from '../../types/map'
import { severityColor } from '../../utils/ringSeverity'

const props = withDefaults(
  defineProps<{
    trees: UpstreamTreeView[]
    activeTree?: string | null
    showHop2?: boolean
  }>(),
  { activeTree: null, showHop2: true },
)

const emit = defineEmits<{
  'focus-node': [interId: string]
  'select-tree': [treeId: string]
}>()

const selected = ref<string | null>(null)

const activeTreeId = computed(
  () => selected.value ?? props.activeTree ?? props.trees[0]?.tree_id ?? null,
)

watch(
  () => props.activeTree,
  (t) => {
    if (t) selected.value = t
  },
)

const activeTreeView = computed(
  () => props.trees.find((t) => t.tree_id === activeTreeId.value) ?? null,
)

interface RowNode extends UpstreamTreeNode {
  isGovernance: boolean
  worstSat: number | null
}

const rows = computed<RowNode[]>(() => {
  const view = activeTreeView.value
  if (!view) return []
  return view.nodes
    .filter((n) => n.role !== 'target')
    .filter((n) => props.showHop2 || (n.hop ?? 1) < 2)
    .map((n) => ({
      ...n,
      isGovernance: n.role === 'governance' || n.decision === '治理落点',
      worstSat: (n.approach_profiles ?? []).reduce<number | null>(
        (m, p) => Math.max(m ?? 0, Number(p.turn_saturation_max ?? 0)),
        null,
      ),
    }))
    .sort((a, b) => (a.hop ?? 1) - (b.hop ?? 1))
})

function pickTree(treeId: string) {
  selected.value = treeId
  emit('select-tree', treeId)
}

function pickNode(node: RowNode) {
  const id = node.inter_id ?? node.id
  if (id) emit('focus-node', id)
}
</script>

<template>
  <section v-if="trees.length" data-testid="upstream-governance-card" class="upstream-card">
    <header class="upstream-card__head">
      <span class="upstream-card__title">上游治理落点</span>
    </header>

    <div class="upstream-card__tabs" role="tablist">
      <button
        v-for="tree in trees"
        :key="tree.tree_id"
        class="upstream-tab"
        :class="{ 'is-active': tree.tree_id === activeTreeId }"
        :data-tree="tree.tree_id"
        data-testid="upstream-tab"
        role="tab"
        @click="pickTree(tree.tree_id)"
      >
        {{ tree.approach }}
      </button>
    </div>

    <ul class="upstream-card__list">
      <li
        v-for="node in rows"
        :key="node.id ?? node.inter_id"
        class="upstream-node"
        :class="{ 'is-governance': node.isGovernance, 'is-hop2': (node.hop ?? 1) >= 2 }"
        :data-hop="node.hop ?? 1"
        :data-governance="node.isGovernance ? '1' : '0'"
        data-testid="upstream-node"
        @click="pickNode(node)"
      >
        <span class="upstream-node__dot" :style="{ background: severityColor(node.worstSat) }" />
        <span class="upstream-node__name">
          <span v-if="node.isGovernance" class="upstream-node__star" data-testid="governance-star">★</span>
          {{ node.name ?? node.inter_id }}
        </span>
        <span class="upstream-node__hop">{{ (node.hop ?? 1) }}跳</span>
        <span v-if="node.isGovernance" class="upstream-node__advice">可借调绿信比</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.upstream-card {
  width: 248px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(8, 12, 20, 0.92);
  border: 1px solid rgba(126, 200, 255, 0.35);
  color: #d6e6ff;
  font-family: 'Inter', system-ui, sans-serif;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.45);
}
.upstream-card__head {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.upstream-card__title {
  font-size: 13px;
  font-weight: 700;
  color: #7ec8ff;
}
.upstream-card__tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.upstream-tab {
  padding: 3px 9px;
  border-radius: 12px;
  border: 1px solid rgba(126, 200, 255, 0.3);
  background: transparent;
  color: #9fb6d6;
  font-size: 11px;
  cursor: pointer;
}
.upstream-tab.is-active {
  background: rgba(126, 200, 255, 0.18);
  color: #cfe6ff;
  border-color: #7ec8ff;
}
.upstream-card__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.upstream-node {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 6px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 12px;
}
.upstream-node:hover {
  background: rgba(126, 200, 255, 0.12);
}
.upstream-node.is-hop2 {
  padding-left: 16px;
  opacity: 0.92;
}
.upstream-node.is-governance {
  background: rgba(109, 255, 181, 0.1);
}
.upstream-node__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: 0 0 auto;
}
.upstream-node__name {
  flex: 1 1 auto;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.upstream-node__star {
  color: #6dffb5;
}
.upstream-node__hop {
  font-size: 10px;
  color: #7f93b3;
}
.upstream-node__advice {
  font-size: 10px;
  color: #6dffb5;
}
</style>

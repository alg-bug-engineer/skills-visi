<script setup lang="ts">
import type { SkillBuildFileNode } from '@/types/skillBuild'

defineProps<{
  nodes: SkillBuildFileNode[]
  activeFilePath?: string
}>()

const emit = defineEmits<{
  select: [path: string]
}>()

const STATUS_LABEL: Record<SkillBuildFileNode['status'], string> = {
  pending: '待写',
  writing: '写入中',
  completed: '完成',
}
</script>

<template>
  <ul class="file-tree">
    <li v-for="node in nodes" :key="node.path" class="file-tree__item">
      <button
        v-if="node.type === 'file'"
        type="button"
        class="file-node"
        :class="[`status-${node.status}`, { active: activeFilePath === node.path }]"
        :title="node.path"
        @click="emit('select', node.path)"
      >
        <span class="file-node__icon" aria-hidden="true">▤</span>
        <span class="file-node__name">{{ node.name }}</span>
        <small class="file-node__status">{{ STATUS_LABEL[node.status] }}</small>
      </button>
      <div v-else class="dir-node">
        <span class="dir-node__label"><span class="dir-node__icon" aria-hidden="true">▸</span>{{ node.name }}</span>
        <SkillFileTree
          v-if="node.children?.length"
          :nodes="node.children"
          :active-file-path="activeFilePath"
          @select="emit('select', $event)"
        />
      </div>
    </li>
  </ul>
</template>

<style scoped>
.file-tree {
  list-style: none;
  margin: 0;
  padding-left: 12px;
}
.file-tree :deep(.file-tree) {
  padding-left: 12px;
}
.dir-node__label {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
}
.dir-node__icon {
  color: var(--text-mute);
  font-size: 10px;
}
.file-node {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 6px;
  border: 1px solid transparent;
  background: transparent;
  border-radius: var(--radius-sm);
  padding: 5px 8px;
  cursor: pointer;
  color: var(--text-dim);
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  text-align: left;
}
.file-node__icon {
  color: var(--text-mute);
  font-size: 11px;
}
.file-node__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-node__status {
  font-size: 10px;
  color: var(--text-mute);
}
.file-node:hover {
  border-color: rgba(0, 229, 255, 0.2);
  color: var(--text);
}
.file-node.active {
  background: rgba(0, 229, 255, 0.1);
  border-color: rgba(0, 229, 255, 0.28);
  color: var(--text);
}
.file-node.status-writing .file-node__status {
  color: var(--primary);
}
.file-node.status-completed .file-node__status {
  color: var(--protected);
}
.file-node.status-writing .file-node__icon {
  color: var(--primary);
}
.file-node.status-completed .file-node__icon {
  color: var(--protected);
}
</style>

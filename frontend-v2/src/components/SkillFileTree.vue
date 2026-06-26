<script setup lang="ts">
import type { SkillBuildFileNode } from '../types/skillBuild'

defineProps<{
  nodes: SkillBuildFileNode[]
  activePath?: string
}>()

const emit = defineEmits<{
  open: [path: string]
}>()
</script>

<template>
  <ul>
    <li v-for="node in nodes" :key="node.path">
      <button
        v-if="node.type === 'file'"
        type="button"
        :class="[
          'file-node',
          { active: activePath === node.path, updated: node.isUpdate },
        ]"
        :title="node.path"
        @click="emit('open', node.path)"
      >
        <span>{{ node.name }}</span>
        <small>{{ node.status }}</small>
      </button>
      <div v-else class="directory-node">
        <span>{{ node.name }}</span>
        <SkillFileTree
          v-if="node.children?.length"
          :nodes="node.children"
          :active-path="activePath"
          @open="emit('open', $event)"
        />
      </div>
    </li>
  </ul>
</template>

<style scoped>
ul {
  list-style: none;
  margin: 0;
  padding-left: 10px;
}

:deep(> ul) {
  padding-left: 0;
}

.directory-node > span {
  display: block;
  padding: 5px 0;
  font-size: 12px;
  font-weight: 600;
  color: rgba(220, 240, 255, 0.7);
}

.file-node {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  border: 0;
  background: transparent;
  border-radius: 3px;
  padding: 6px 8px;
  cursor: pointer;
  color: rgba(220, 240, 255, 0.82);
  font-size: 12px;
  font-family: 'Courier New', Courier, monospace;
}

.file-node:hover,
.file-node.active {
  background: rgba(0, 212, 240, 0.12);
}

.file-node.updated {
  border-left: 2px solid #ffc266;
}

.file-node small {
  color: rgba(220, 240, 255, 0.4);
  font-size: 10px;
}
</style>

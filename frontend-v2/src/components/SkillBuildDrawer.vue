<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { lineDiffKind, removedDiffLines } from '../composables/useSkillBuildProcess'
import type { SkillBuildState } from '../types/skillBuild'
import SkillFileTree from './SkillFileTree.vue'

const props = defineProps<{
  state: SkillBuildState
}>()

const emit = defineEmits<{
  selectFile: [path: string]
  finish: []
}>()

const codeOutputRef = ref<HTMLElement | null>(null)

const activeContent = computed(() => {
  if (!props.state.activeFilePath) {
    return '等待技能文件开始生成…'
  }
  return props.state.fileContents[props.state.activeFilePath] ?? ''
})

const activeDiff = computed(() => {
  if (!props.state.activeFilePath) return undefined
  return props.state.fileDiffs[props.state.activeFilePath]
})

const removedLines = computed(() => removedDiffLines(activeDiff.value))
const displayedLines = computed(() => activeContent.value.split('\n'))

const downloadHref = computed(() => {
  if (!props.state.downloadUrl) return ''
  const base = import.meta.env.VITE_API_BASE ?? ''
  return `${base}${props.state.downloadUrl}`
})

const statusLabel = computed(() => {
  if (props.state.status === 'completed') return '已完成'
  if (props.state.status === 'running') return '写入中'
  return '待命'
})

watch(
  () => activeContent.value,
  () => {
    const el = codeOutputRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

function onDownloadClick() {
  if (!downloadHref.value) return
  const anchor = document.createElement('a')
  anchor.href = downloadHref.value
  anchor.download = `${props.state.skillDir ?? 'skill'}.zip`
  anchor.click()
}
</script>

<template>
  <Transition name="drawer-slide">
    <aside
      v-if="state.visible"
      :class="['skill-drawer', { exiting: state.exiting, completed: state.status === 'completed' }]"
      role="complementary"
      aria-label="技能写入终端"
    >
      <header class="drawer-header">
        <div class="header-main">
          <span class="prompt">skill@intersection</span>
          <h2>{{ state.title }}</h2>
          <p v-if="state.timePeriodLabel" class="meta">
            {{ state.timePeriodLabel }}
            <span v-if="state.isUpdate" class="tag">更新</span>
          </p>
        </div>
        <div class="status-pill">
          <span class="dot" />
          {{ statusLabel }}
          <strong>{{ state.progress }}%</strong>
        </div>
      </header>

      <div v-if="state.diffChanges.length" class="diff-strip">
        <span v-for="(change, i) in state.diffChanges" :key="i">{{ change }}</span>
      </div>

      <div class="drawer-body">
        <div class="file-pane">
          <p class="pane-label">// files</p>
          <SkillFileTree
            v-if="state.files.length"
            :nodes="state.files"
            :active-path="state.activeFilePath"
            @open="emit('selectFile', $event)"
          />
          <p v-else class="muted">等待首个文件…</p>
        </div>

        <div class="code-pane">
          <div class="code-toolbar">
            <span class="path">{{ state.activeFilePath || '—' }}</span>
            <a
              v-if="state.status === 'completed' && downloadHref"
              class="download-link"
              :href="downloadHref"
              download
              @click.prevent="onDownloadClick"
            >
              下载 zip
            </a>
          </div>

          <div v-if="removedLines.length" class="diff-removed">
            <div
              v-for="line in removedLines"
              :key="`rm-${line.line_no}`"
              class="diff-line removed"
            >
              <span class="ln">{{ line.line_no }}</span>
              <span>{{ line.text }}</span>
            </div>
          </div>

          <div ref="codeOutputRef" class="code-output">
            <div
              v-for="(line, index) in displayedLines"
              :key="index"
              :class="['code-line', `kind-${lineDiffKind(activeDiff, index + 1)}`]"
            >
              <span class="ln">{{ index + 1 }}</span>
              <span class="txt">{{ line || ' ' }}</span>
            </div>
          </div>
        </div>
      </div>

      <footer v-if="state.status === 'completed'" class="drawer-footer completed-footer">
        <p>技能已真实写入并可下载。下次同类问题将自动命中该技能。</p>
        <button type="button" class="btn-finish" data-testid="skill-build-finish" @click="emit('finish')">
          完成，返回地图
        </button>
      </footer>
      <footer v-else class="drawer-footer">
        <span class="cursor-blink">{{ state.modelStatus }}</span>
      </footer>
    </aside>
  </Transition>
</template>

<style scoped>
.skill-drawer {
  position: absolute;
  top: 14px;
  left: 14px;
  bottom: 14px;
  width: min(78%, 780px);
  min-width: 420px;
  z-index: 16;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(0, 229, 255, 0.28);
  border-radius: 6px;
  background: rgba(2, 10, 20, 0.78);
  backdrop-filter: blur(10px);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.42),
    inset 0 1px 0 rgba(0, 229, 255, 0.08);
  font-family: 'Courier New', Courier, monospace;
  color: #c8e8ff;
  pointer-events: auto;
}

.skill-drawer.exiting {
  opacity: 0;
  transform: translateX(calc(-100% - 24px));
  transition:
    transform 0.55s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.45s ease;
}

.drawer-slide-enter-active {
  transition: transform 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}

.drawer-slide-enter-from {
  transform: translateX(calc(-100% - 24px));
}

.drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(0, 212, 240, 0.15);
  background: rgba(0, 12, 24, 0.55);
  flex-shrink: 0;
  border-radius: 6px 6px 0 0;
}

.prompt {
  display: block;
  font-size: 10px;
  color: rgba(0, 229, 255, 0.55);
  letter-spacing: 0.5px;
}

.drawer-header h2 {
  margin: 4px 0 0;
  font-size: 13px;
  font-weight: 600;
  color: #00e5ff;
}

.meta {
  margin: 4px 0 0;
  font-size: 11px;
  color: rgba(200, 232, 255, 0.65);
}

.tag {
  margin-left: 6px;
  padding: 0 5px;
  border: 1px solid rgba(255, 180, 60, 0.45);
  color: #ffc266;
  font-size: 9px;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border: 1px solid rgba(0, 212, 240, 0.25);
  border-radius: 2px;
  font-size: 10px;
  white-space: nowrap;
  background: rgba(0, 8, 18, 0.45);
}

.status-pill strong {
  color: #00e5ff;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #00d4f0;
  box-shadow: 0 0 6px rgba(0, 212, 240, 0.7);
  animation: pulse 1.2s ease infinite;
}

.skill-drawer.completed .dot {
  background: #69f0ae;
  box-shadow: 0 0 6px rgba(105, 240, 174, 0.6);
  animation: none;
}

@keyframes pulse {
  50% {
    opacity: 0.35;
  }
}

.diff-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 180, 60, 0.15);
  background: rgba(255, 180, 60, 0.05);
  font-size: 10px;
  color: rgba(255, 200, 140, 0.9);
}

.drawer-body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 150px minmax(0, 1fr);
}

.file-pane,
.code-pane {
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.file-pane {
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  padding: 8px;
  overflow-y: auto;
}

.pane-label {
  margin: 0 0 6px;
  font-size: 10px;
  color: rgba(0, 229, 255, 0.45);
}

.code-pane {
  min-width: 0;
}

.code-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  font-size: 10px;
}

.path {
  color: #00e5ff;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-link {
  color: #69f0ae;
  text-decoration: none;
  font-size: 10px;
  flex-shrink: 0;
}

.download-link:hover {
  text-decoration: underline;
}

.diff-removed {
  max-height: 72px;
  overflow: auto;
  padding: 4px 8px;
  background: rgba(255, 107, 107, 0.08);
  border-bottom: 1px solid rgba(255, 107, 107, 0.2);
}

.diff-line {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 6px;
  font-size: 10px;
  line-height: 1.4;
}

.diff-line.removed {
  color: #ff8f8f;
  text-decoration: line-through;
}

.code-output {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 6px 0;
  background: rgba(1, 6, 12, 0.72);
  font-size: 11px;
  line-height: 1.45;
}

.code-line {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: 6px;
  padding: 0 8px;
}

.code-line .ln {
  color: rgba(200, 232, 255, 0.25);
  text-align: right;
  user-select: none;
}

.code-line.kind-added {
  background: rgba(0, 229, 255, 0.08);
}

.code-line.kind-added .txt {
  color: #9ff7ff;
}

.muted {
  margin: 0;
  font-size: 10px;
  color: rgba(200, 232, 255, 0.4);
}

.drawer-footer {
  flex-shrink: 0;
  padding: 6px 10px;
  border-top: 1px solid rgba(0, 212, 240, 0.12);
  background: rgba(0, 8, 18, 0.55);
  font-size: 10px;
  color: rgba(200, 232, 255, 0.6);
  border-radius: 0 0 6px 6px;
}

.completed-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 12px;
}

.completed-footer p {
  margin: 0;
  font-size: 10px;
  line-height: 1.5;
  color: rgba(200, 232, 255, 0.72);
  flex: 1;
}

.btn-finish {
  flex-shrink: 0;
  padding: 8px 14px;
  border-radius: 2px;
  border: 1px solid rgba(0, 229, 255, 0.4);
  background: rgba(0, 212, 240, 0.18);
  color: #00e5ff;
  font-size: 11px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 600;
}

.btn-finish:hover {
  background: rgba(0, 212, 240, 0.28);
}

.cursor-blink::after {
  content: '▋';
  margin-left: 2px;
  color: #00d4f0;
  animation: blink 0.9s steps(2, start) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

@media (max-width: 900px) {
  .skill-drawer {
    width: min(88%, 680px);
    min-width: 300px;
    top: 10px;
    left: 10px;
    bottom: 10px;
  }

  .drawer-body {
    grid-template-columns: 120px minmax(0, 1fr);
  }

  .completed-footer {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

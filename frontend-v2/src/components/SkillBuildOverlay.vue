<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  lineDiffKind,
  removedDiffLines,
} from '../composables/useSkillBuildProcess'
import type { SkillBuildState } from '../types/skillBuild'
import SkillFileTree from './SkillFileTree.vue'
import { SKILL_BUILD_STAGES, STAGE_PROGRESS } from '../types/skillBuild'

const props = defineProps<{
  state: SkillBuildState
}>()

const emit = defineEmits<{
  selectFile: [path: string]
  finish: []
}>()

const codeOutputRef = ref<HTMLElement | null>(null)
const logListRef = ref<HTMLElement | null>(null)

const activeContent = computed(() => {
  if (!props.state.activeFilePath) {
    return '等待技能文件开始生成……'
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
  if (props.state.status === 'running') return '沉淀中'
  if (props.state.status === 'failed') return '失败'
  return '待开始'
})

watch(
  () => activeContent.value,
  () => {
    const el = codeOutputRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

watch(
  () => props.state.logs.length,
  () => {
    const el = logListRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

function stageClass(stage: string) {
  const progress = props.state.progress
  if (props.state.currentStage === stage && props.state.status === 'running') {
    return 'timeline-item running'
  }
  if (progress >= (STAGE_PROGRESS[stage] ?? 0)) {
    return 'timeline-item success'
  }
  return 'timeline-item waiting'
}

function onDownloadClick() {
  if (!downloadHref.value) return
  const anchor = document.createElement('a')
  anchor.href = downloadHref.value
  anchor.download = `${props.state.skillDir ?? 'skill'}.zip`
  anchor.click()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="state.visible"
      :class="['skill-build-overlay', { exiting: state.exiting }]"
      role="dialog"
      aria-label="技能沉淀工作台"
    >
      <a
        v-if="state.status === 'completed' && downloadHref"
        class="download-fab"
        :href="downloadHref"
        download
        @click.prevent="onDownloadClick"
      >
        <span class="fab-icon">↓</span>
        <span>下载技能包</span>
      </a>

      <div class="overlay-panel">
        <header class="build-header">
          <div>
            <p class="eyebrow">SKILL BUILD</p>
            <h1>{{ state.title }}</h1>
            <p v-if="state.timePeriodLabel" class="subtitle">
              {{ state.timePeriodLabel }}
              <span v-if="state.isUpdate" class="update-tag">更新</span>
            </p>
          </div>
          <div class="progress-card">
            <span>{{ statusLabel }}</span>
            <strong>{{ state.progress }}%</strong>
          </div>
        </header>

        <section v-if="state.diffChanges.length" class="diff-banner">
          <p class="diff-title">本次变更</p>
          <ul>
            <li v-for="(change, i) in state.diffChanges" :key="i">{{ change }}</li>
          </ul>
        </section>

        <section class="workbench">
          <aside class="timeline" aria-label="阶段时间线">
            <h2>阶段</h2>
            <div
              v-for="stage in SKILL_BUILD_STAGES"
              :key="stage.key"
              :class="stageClass(stage.key)"
            >
              <span />
              <p>{{ stage.label }}</p>
            </div>
          </aside>

          <section class="main-stage">
            <div class="thinking-panel">
              <div class="thinking-header">
                <div>
                  <p class="eyebrow">沉淀思路</p>
                  <h2>{{ state.modelStatus }}</h2>
                </div>
              </div>
              <p :class="state.status === 'running' ? 'thinking-text typing' : 'thinking-text'">
                {{ state.thoughtText || '等待开始整理本次诊断结论……' }}
              </p>
            </div>

            <div class="stage-toolbar">
              <div>
                <p class="eyebrow">当前文件</p>
                <h2>{{ state.activeFilePath || '等待生成' }}</h2>
              </div>
            </div>

            <div v-if="removedLines.length" class="diff-removed-block">
              <p class="diff-removed-title">已移除内容</p>
              <div
                v-for="line in removedLines"
                :key="`rm-${line.line_no}`"
                class="diff-line removed"
              >
                <span class="ln">{{ line.line_no }}</span>
                <span class="txt">{{ line.text }}</span>
              </div>
            </div>

            <div ref="codeOutputRef" class="code-output" aria-label="文件内容">
              <div
                v-for="(line, index) in displayedLines"
                :key="index"
                :class="['code-line', `kind-${lineDiffKind(activeDiff, index + 1)}`]"
              >
                <span class="ln">{{ index + 1 }}</span>
                <span class="txt">{{ line || ' ' }}</span>
              </div>
            </div>
          </section>

          <aside class="file-tree" aria-label="文件树">
            <h2>技能包文件</h2>
            <SkillFileTree
              v-if="state.files.length"
              :nodes="state.files"
              :active-path="state.activeFilePath"
              @open="emit('selectFile', $event)"
            />
            <p v-else class="muted">文件将逐个出现并开始编写。</p>
          </aside>
        </section>

        <section class="console">
          <div class="console-header">
            <h2>过程日志</h2>
          </div>
          <div ref="logListRef" class="log-list">
            <p v-for="log in state.logs" :key="log.seq">{{ log.message }}</p>
          </div>
        </section>

        <footer v-if="state.status === 'completed'" class="build-footer">
          <p>技能已真实写入并可下载使用。下次同类问题将自动命中该技能。</p>
          <button type="button" class="btn-finish" @click="emit('finish')">完成，返回地图</button>
        </footer>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.skill-build-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: rgba(2, 8, 16, 0.72);
  backdrop-filter: blur(6px);
  animation: overlay-in 0.45s ease;
}

.skill-build-overlay.exiting {
  animation: overlay-out 0.65s ease forwards;
}

@keyframes overlay-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

@keyframes overlay-out {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
  }
}

.overlay-panel {
  width: min(1440px, 100%);
  max-height: 96vh;
  margin: 0 12px 12px;
  padding: 18px 20px 16px;
  border-radius: 6px;
  border: 1px solid rgba(0, 212, 240, 0.35);
  background: rgba(6, 14, 26, 0.96);
  box-shadow: 0 -12px 48px rgba(0, 0, 0, 0.55);
  color: #eef6ff;
  overflow: auto;
  animation: panel-rise 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}

.skill-build-overlay.exiting .overlay-panel {
  animation: panel-exit 0.65s ease forwards;
}

@keyframes panel-rise {
  from {
    transform: translateY(100%);
    opacity: 0.2;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

@keyframes panel-exit {
  from {
    transform: translateY(0);
    opacity: 1;
  }
  to {
    transform: translateY(110%);
    opacity: 0;
  }
}

.download-fab {
  position: fixed;
  left: 20px;
  bottom: 28px;
  z-index: 110;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 4px;
  border: 1px solid rgba(0, 229, 255, 0.45);
  background: rgba(0, 212, 240, 0.14);
  color: #00e5ff;
  text-decoration: none;
  font-size: 13px;
  letter-spacing: 0.5px;
  box-shadow: 0 8px 28px rgba(0, 212, 240, 0.18);
}

.fab-icon {
  font-size: 16px;
  font-weight: 700;
}

.build-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.build-header h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.eyebrow {
  margin: 0 0 6px;
  color: rgba(220, 240, 255, 0.45);
  font-size: 11px;
  letter-spacing: 1.5px;
}

.subtitle {
  margin: 6px 0 0;
  color: rgba(220, 240, 255, 0.7);
  font-size: 13px;
}

.update-tag {
  margin-left: 8px;
  padding: 1px 6px;
  border: 1px solid rgba(255, 180, 60, 0.45);
  color: #ffc266;
  font-size: 10px;
}

.progress-card {
  min-width: 140px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid rgba(0, 212, 240, 0.28);
  border-radius: 4px;
  background: rgba(0, 212, 240, 0.06);
}

.progress-card strong {
  color: #00e5ff;
}

.diff-banner {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-left: 2px solid #ffc266;
  background: rgba(255, 180, 60, 0.08);
  border-radius: 2px;
}

.diff-title {
  margin: 0 0 6px;
  font-size: 11px;
  color: #ffc266;
  letter-spacing: 1px;
}

.diff-banner ul {
  margin: 0;
  padding-left: 18px;
  color: rgba(220, 240, 255, 0.85);
  font-size: 12px;
  line-height: 1.55;
}

.workbench {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr) 260px;
  gap: 12px;
  min-height: 420px;
}

.timeline,
.file-tree,
.main-stage,
.console {
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 4px;
  background: rgba(0, 8, 18, 0.55);
}

.timeline,
.file-tree {
  padding: 14px;
}

.timeline h2,
.file-tree h2,
.console h2 {
  margin: 0 0 12px;
  font-size: 14px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 8px;
  align-items: center;
  padding: 7px 0;
  color: rgba(220, 240, 255, 0.45);
  font-size: 12px;
}

.timeline-item p {
  margin: 0;
}

.timeline-item span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(220, 240, 255, 0.2);
}

.timeline-item.running {
  color: #00e5ff;
  font-weight: 600;
}

.timeline-item.running span {
  background: #00d4f0;
  box-shadow: 0 0 8px rgba(0, 212, 240, 0.65);
}

.timeline-item.success {
  color: rgba(220, 240, 255, 0.82);
}

.timeline-item.success span {
  background: #00e5ff;
}

.main-stage {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.thinking-panel {
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.thinking-header {
  padding: 12px 14px 6px;
}

.thinking-header h2 {
  margin: 0;
  font-size: 14px;
}

.thinking-text {
  min-height: 64px;
  max-height: 110px;
  margin: 0;
  padding: 0 14px 12px;
  overflow: auto;
  color: rgba(220, 240, 255, 0.82);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.thinking-text.typing::after {
  content: '';
  display: inline-block;
  width: 6px;
  height: 1em;
  margin-left: 2px;
  vertical-align: -2px;
  background: #00d4f0;
  animation: blink 0.9s steps(2, start) infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.stage-toolbar {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.stage-toolbar h2 {
  margin: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
  font-family: 'Courier New', Courier, monospace;
  color: #00e5ff;
}

.diff-removed-block {
  max-height: 120px;
  overflow: auto;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 107, 107, 0.25);
  background: rgba(255, 107, 107, 0.06);
}

.diff-removed-title {
  margin: 0 0 6px;
  font-size: 11px;
  color: #ff8f8f;
}

.diff-line {
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 8px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 12px;
  line-height: 1.45;
}

.diff-line.removed .txt {
  text-decoration: line-through;
  color: #ff8f8f;
}

.code-output {
  flex: 1;
  min-height: 280px;
  max-height: 360px;
  overflow: auto;
  padding: 10px 0;
  background: #020810;
  font-family: 'Courier New', Courier, monospace;
  font-size: 12px;
  line-height: 1.5;
}

.code-line {
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 8px;
  padding: 0 12px;
}

.code-line .ln {
  color: rgba(220, 240, 255, 0.28);
  text-align: right;
  user-select: none;
}

.code-line.kind-added {
  background: rgba(0, 229, 255, 0.1);
}

.code-line.kind-added .txt {
  color: #9ff7ff;
}

.muted {
  color: rgba(220, 240, 255, 0.45);
  font-size: 12px;
}

.console {
  margin-top: 12px;
}

.console-header {
  padding: 10px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.console-header h2 {
  margin: 0;
  font-size: 13px;
}

.log-list {
  max-height: 120px;
  overflow: auto;
  padding: 10px 14px;
}

.log-list p {
  margin: 0 0 6px;
  font-size: 12px;
  color: rgba(220, 240, 255, 0.72);
}

.build-footer {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.build-footer p {
  margin: 0;
  font-size: 12px;
  color: rgba(220, 240, 255, 0.75);
}

.btn-finish {
  padding: 8px 16px;
  border-radius: 2px;
  border: 1px solid rgba(0, 229, 255, 0.35);
  background: rgba(0, 212, 240, 0.18);
  color: #00e5ff;
  font-size: 12px;
  cursor: pointer;
  font-family: inherit;
}

@media (max-width: 980px) {
  .workbench {
    grid-template-columns: 1fr;
  }
}
</style>

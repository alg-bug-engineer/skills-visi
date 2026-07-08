<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { SkillBuildState } from '@/types/skillBuild'
import SkillFileTree from '@/components/SkillFileTree.vue'
import { productCopy } from '@/utils/productCopy'

const props = defineProps<{
  state: SkillBuildState
}>()

const emit = defineEmits<{
  select: [path: string]
  finish: []
}>()

const codeRef = ref<HTMLElement | null>(null)

const activeContent = computed(() =>
  props.state.activeFilePath ? (props.state.fileContents[props.state.activeFilePath] ?? '') : '',
)
const codeLines = computed(() => activeContent.value.split('\n'))

const ACTION_LABEL: Record<string, string> = {
  created: '新建固化',
  updated: '更新固化',
  unchanged: '已存在',
}
const actionLabel = computed(() => ACTION_LABEL[props.state.action] ?? props.state.action)

const statusLabel = computed(() => {
  if (props.state.status === 'completed') return '已完成'
  if (props.state.status === 'running') return '沉淀中'
  if (props.state.status === 'failed') return '失败'
  return '待开始'
})

watch(activeContent, () => {
  const el = codeRef.value
  if (el) el.scrollTop = el.scrollHeight
})
</script>

<template>
  <section class="build us-panel" data-testid="skill-build-panel">
    <header class="build__hd">
      <div>
        <span class="build__eyebrow">SKILL BUILD · 技能固化</span>
        <h2>{{ productCopy(state.intersection) || '技能构建' }}</h2>
        <p v-if="state.timePeriodLabel" class="build__sub">{{ state.timePeriodLabel }}</p>
      </div>
      <div class="progress-card">
        <span>{{ statusLabel }}</span>
        <strong data-testid="build-progress">{{ state.progress }}%</strong>
      </div>
    </header>

    <div class="workbench">
      <aside class="timeline" aria-label="阶段时间线">
        <h3>阶段</h3>
        <div
          v-for="stage in state.stages"
          :key="stage.key"
          class="timeline__item"
          :class="`is-${stage.status}`"
        >
          <span class="timeline__dot" aria-hidden="true" />
          <span class="timeline__label">{{ stage.label }}</span>
          <small class="timeline__pct">{{ stage.progress }}%</small>
        </div>
      </aside>

      <section class="code-pane" aria-label="技能文件内容">
        <div class="code-pane__hd">
          <span class="code-pane__path">{{ state.activeFilePath || '等待生成…' }}</span>
        </div>
        <div ref="codeRef" class="code-output">
          <div v-for="(line, i) in codeLines" :key="i" class="code-line">
            <span class="ln">{{ i + 1 }}</span>
            <span class="txt">{{ line || ' ' }}</span>
          </div>
        </div>
      </section>

      <aside class="tree-pane" aria-label="技能包文件">
        <h3>技能包文件</h3>
        <SkillFileTree
          v-if="state.files.length"
          :nodes="state.files"
          :active-file-path="state.activeFilePath"
          @select="emit('select', $event)"
        />
        <p v-else class="muted">文件将逐个出现并开始写入。</p>
      </aside>
    </div>

    <footer v-if="state.status === 'completed'" class="build__ft" data-testid="build-footer">
      <div class="skill-card">
        <div class="skill-card__row">
          <span class="skill-card__k">技能 ID</span>
          <span class="skill-card__v mono">{{ state.skillId }}</span>
        </div>
        <div class="skill-card__row">
          <span class="skill-card__k">路口</span>
          <span class="skill-card__v">{{ productCopy(state.intersection) || '—' }}</span>
        </div>
        <div class="skill-card__row">
          <span class="skill-card__k">时段</span>
          <span class="skill-card__v">{{ state.timePeriodLabel || '—' }}</span>
        </div>
        <div class="skill-card__row">
          <span class="skill-card__k">动作</span>
          <span class="skill-card__v tag">{{ actionLabel }}</span>
        </div>
      </div>
      <div class="build__actions">
        <a
          v-if="state.downloadUrl"
          class="btn btn--ghost"
          :href="state.downloadUrl"
          download
          data-testid="skill-download"
        >
          下载技能包
        </a>
        <button
          type="button"
          class="btn btn--primary"
          data-testid="solidify-finish"
          @click="emit('finish')"
        >
          返回主页
        </button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.build {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  padding: 14px 16px;
  border-radius: var(--radius);
  background: rgba(4, 13, 24, 0.94);
}
.build__hd {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
  flex: 0 0 auto;
}
.build__eyebrow {
  font-size: 10px;
  letter-spacing: 1.5px;
  color: var(--text-mute);
}
.build__hd h2 {
  margin: 4px 0 0;
  font-size: 16px;
  color: var(--text);
}
.build__sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-dim);
}
.progress-card {
  min-width: 130px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid rgba(0, 229, 255, 0.28);
  border-radius: var(--radius-sm);
  background: rgba(0, 229, 255, 0.06);
  font-size: 12px;
  color: var(--text-dim);
}
.progress-card strong {
  color: var(--primary);
}
.workbench {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr) 240px;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
.timeline,
.tree-pane,
.code-pane {
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-sm);
  background: rgba(0, 8, 18, 0.5);
  min-height: 0;
}
.timeline,
.tree-pane {
  padding: 12px;
  overflow: auto;
}
.timeline h3,
.tree-pane h3 {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--text);
}
.timeline__item {
  display: grid;
  grid-template-columns: 12px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  color: var(--text-mute);
  font-size: 12px;
}
.timeline__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(220, 240, 255, 0.2);
}
.timeline__pct {
  font-size: 10px;
  color: var(--text-mute);
}
.timeline__item.is-active {
  color: var(--primary);
  font-weight: 600;
}
.timeline__item.is-active .timeline__dot {
  background: var(--primary);
  box-shadow: var(--glow-primary);
}
.timeline__item.is-done {
  color: var(--text-dim);
}
.timeline__item.is-done .timeline__dot {
  background: var(--protected);
}
.code-pane {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.code-pane__hd {
  padding: 10px 14px;
  border-bottom: 1px solid var(--panel-border);
}
.code-pane__path {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12.5px;
  color: var(--primary);
  overflow-wrap: anywhere;
}
.code-output {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 10px 0;
  background: #020810;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.5;
}
.code-line {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 8px;
  padding: 0 12px;
}
.code-line .ln {
  color: var(--text-mute);
  text-align: right;
  user-select: none;
}
.code-line .txt {
  color: var(--text-dim);
  white-space: pre-wrap;
  word-break: break-word;
}
.muted {
  color: var(--text-mute);
  font-size: 12px;
}
.build__ft {
  flex: 0 0 auto;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--panel-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.skill-card {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 18px;
  flex: 1;
  min-width: 0;
}
.skill-card__row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  min-width: 0;
}
.skill-card__k {
  color: var(--text-mute);
  flex: 0 0 auto;
}
.skill-card__v {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.skill-card__v.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.skill-card__v.tag {
  color: var(--primary);
}
.build__actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}
.btn {
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
}
.btn--primary {
  background: var(--primary);
  color: var(--bg);
}
.btn--ghost {
  background: transparent;
  border-color: var(--panel-border);
  color: var(--text-dim);
}
.btn--ghost:hover {
  color: var(--primary);
  border-color: var(--primary);
}
</style>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { t } from '@/labels/enums'
import { pct } from '@/utils/format'
import expertKnowledge from '@/data/expertKnowledge.json'

type PanelTab = 'experience' | 'cases'
type ExpSubTab = 'cognitive' | 'diagnostic' | 'solution'
type CaseSubTab = 'industry' | 'intersection'

interface IndustryCase {
  id: string
  title: string
  snippet: string
}
interface IndustryScheme {
  name: string
  freq: number
  measures: string[]
  applicable: string
  caution: string
  cases: IndustryCase[]
}
interface IndustryProblem {
  name: string
  freq: number
  symptoms: string[]
  schemes: IndustryScheme[]
}
interface IndustryScene {
  scene: string
  sceneId: string
  caseCount: number
  desc: string
  problems: IndustryProblem[]
}

const scenes = expertKnowledge as IndustryScene[]

const store = usePresentationStore()
const { experiencesByType, existingCases, experienceReady, casesReady } = storeToRefs(store)

const activeTab = ref<PanelTab>('experience')
const expSubTab = ref<ExpSubTab>('cognitive')
const caseSubTab = ref<CaseSubTab>('industry')

const expSubTabs: Array<{ key: ExpSubTab; label: string; hint: string }> = [
  { key: 'cognitive', label: '认知经验', hint: '问题记录' },
  { key: 'diagnostic', label: '诊断经验', hint: '成因先验' },
  { key: 'solution', label: '方案经验', hint: '量化方案' },
]

const caseSubTabs: Array<{ key: CaseSubTab; label: string; hint: string }> = [
  { key: 'industry', label: '行业案例', hint: '专家经验库' },
  { key: 'intersection', label: '路口案例', hint: '相似检索' },
]

const activeExpList = computed(() => experiencesByType.value[expSubTab.value])
const expCount = computed(
  () =>
    experiencesByType.value.cognitive.length +
    experiencesByType.value.diagnostic.length +
    experiencesByType.value.solution.length,
)

// —— 行业案例：搜索 + 折叠 ——
const industryQuery = ref('')
const expandedScenes = ref<Set<string>>(new Set())

const searching = computed(() => industryQuery.value.trim().length > 0)

const filteredScenes = computed(() => {
  const q = industryQuery.value.trim().toLowerCase()
  if (!q) return scenes
  return scenes.filter((s) => {
    if (s.scene.toLowerCase().includes(q)) return true
    return s.problems.some(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.schemes.some(
          (sc) =>
            sc.name.toLowerCase().includes(q) ||
            sc.measures.some((m) => m.toLowerCase().includes(q)),
        ),
    )
  })
})

// 搜索时命中场景自动展开；否则按用户点开的集合。
function isSceneOpen(sceneId: string): boolean {
  return searching.value || expandedScenes.value.has(sceneId)
}
function toggleScene(sceneId: string) {
  const next = new Set(expandedScenes.value)
  next.has(sceneId) ? next.delete(sceneId) : next.add(sceneId)
  expandedScenes.value = next
}

function openCases() {
  activeTab.value = 'cases'
  caseSubTab.value = 'industry'
}

onMounted(() => window.addEventListener('open-case-library', openCases))
onBeforeUnmount(() => window.removeEventListener('open-case-library', openCases))
</script>

<template>
  <aside class="understanding us-panel" data-testid="understanding-panel">
    <header class="understanding__hd">
      <span class="dot" />
      <h2>理解面板</h2>
    </header>

    <div class="tab-bar" role="tablist">
      <button
        type="button"
        role="tab"
        class="tab-btn"
        :class="{ active: activeTab === 'experience' }"
        data-testid="experience-tab"
        @click="activeTab = 'experience'"
      >
        经验库
        <span v-if="expCount" class="tab-count">{{ expCount }}</span>
      </button>
      <button
        type="button"
        role="tab"
        class="tab-btn"
        :class="{ active: activeTab === 'cases' }"
        data-testid="case-library-tab"
        @click="activeTab = 'cases'"
      >
        案例库
        <span v-if="existingCases.length" class="tab-count">{{ existingCases.length }}</span>
      </button>
    </div>

    <!-- 经验库 -->
    <div v-if="activeTab === 'experience'" class="tab-body">
      <div class="sub-tabs" role="tablist">
        <button
          v-for="st in expSubTabs"
          :key="st.key"
          type="button"
          role="tab"
          class="sub-tab"
          :class="{ active: expSubTab === st.key }"
          :data-testid="`exp-subtab-${st.key}`"
          @click="expSubTab = st.key"
        >
          <span class="sub-tab-label">{{ st.label }}</span>
          <span class="sub-tab-hint">{{ st.hint }}</span>
        </button>
      </div>

      <div v-if="!experienceReady" class="hint-row">待检索…问题理解完成后展示经验</div>
      <div v-else-if="!activeExpList.length" class="hint-row">
        暂无{{ expSubTabs.find((s) => s.key === expSubTab)?.label }}记录
      </div>
      <ul v-else class="exp-list">
        <li v-for="(e, i) in activeExpList" :key="i" class="exp-item">
          <div class="exp-item-head">
            <span class="badge">{{ t('experience_type', e.experience_type) }}</span>
            <span v-if="e.source_span" class="src">{{ e.source_span }}</span>
          </div>
          <p class="exp-text">{{ e.content }}</p>
        </li>
      </ul>
    </div>

    <!-- 案例库 -->
    <div v-else class="tab-body">
      <div class="sub-tabs" role="tablist">
        <button
          v-for="st in caseSubTabs"
          :key="st.key"
          type="button"
          role="tab"
          class="sub-tab"
          :class="{ active: caseSubTab === st.key }"
          :data-testid="`case-subtab-${st.key}`"
          @click="caseSubTab = st.key"
        >
          <span class="sub-tab-label">{{ st.label }}</span>
          <span class="sub-tab-hint">{{ st.hint }}</span>
        </button>
      </div>

      <!-- 行业案例：专家经验库全量结构化展示 + 搜索 -->
      <template v-if="caseSubTab === 'industry'">
        <div class="industry-search">
          <input
            v-model="industryQuery"
            type="search"
            class="industry-search-input"
            data-testid="industry-search"
            placeholder="搜索场景 / 典型问题"
          />
        </div>
        <div v-if="!filteredScenes.length" class="hint-row">未匹配到场景，试试其他关键词</div>
        <ul v-else class="industry-list">
          <li
            v-for="s in filteredScenes"
            :key="s.sceneId"
            :id="'industry-scene-' + s.sceneId"
            class="industry-scene"
            data-testid="industry-scene"
          >
            <button
              type="button"
              class="scene-head"
              :class="{ open: isSceneOpen(s.sceneId) }"
              @click="toggleScene(s.sceneId)"
            >
              <span class="scene-caret">{{ isSceneOpen(s.sceneId) ? '▾' : '▸' }}</span>
              <span class="scene-name">{{ s.scene }}</span>
              <span class="scene-count">{{ s.caseCount }} 例</span>
            </button>

            <div v-if="isSceneOpen(s.sceneId)" class="scene-body">
              <p class="scene-desc">{{ s.desc }}</p>

              <div v-for="(p, pi) in s.problems" :key="pi" class="problem-block">
                <div class="problem-head">
                  <span class="problem-name">典型问题 · {{ p.name }}</span>
                  <span class="freq-badge">{{ p.freq }} 次</span>
                </div>
                <p v-if="p.symptoms.length" class="problem-symptoms">
                  典型表现：{{ p.symptoms.join('、') }}
                </p>

                <div v-for="(sc, si) in p.schemes" :key="si" class="scheme-block">
                  <div class="scheme-head">
                    <span class="scheme-name">治理方案 · {{ sc.name }}</span>
                    <span class="freq-badge alt">{{ sc.freq }}</span>
                  </div>
                  <p v-if="sc.measures.length" class="scheme-line">
                    关键措施：{{ sc.measures.join('、') }}
                  </p>
                  <p v-if="sc.applicable" class="scheme-line">适用条件：{{ sc.applicable }}</p>
                  <p v-if="sc.caution" class="scheme-caution">注意事项：{{ sc.caution }}</p>
                  <ul v-if="sc.cases.length" class="rep-cases">
                    <li
                      v-for="c in sc.cases"
                      :key="c.id"
                      :id="'industry-case-' + c.id"
                      class="rep-case"
                    >
                      <span class="rep-id">[#{{ c.id }}]</span>
                      <span class="rep-title">{{ c.title }}</span>
                      <span class="rep-snippet">：{{ c.snippet }}…</span>
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </li>
        </ul>
      </template>

      <!-- 路口案例：本次相似检索结果 -->
      <template v-else>
        <div v-if="!casesReady" class="hint-row">待检索…成因分析完成后展示相似案例</div>
        <div v-else-if="!existingCases.length" class="hint-row">暂无高相似历史案例</div>
        <ul v-else class="case-list">
          <li
            v-for="(c, i) in existingCases"
            :key="c.case_id ?? i"
            :id="'inter-case-' + (c.case_id ?? i)"
            class="case-item"
            data-testid="inter-case"
          >
            <header>
              <span class="case-title">{{ c.title ?? '案例' }}</span>
              <span v-if="c.similarity != null" class="case-sim">{{ pct(c.similarity, 0) }}</span>
            </header>
            <p v-if="c.case_id" class="case-id">案例编号：{{ c.case_id }}</p>
            <p v-if="c.action || c.historical_action" class="case-line">
              措施：{{ c.action ?? c.historical_action }}
            </p>
            <p v-if="c.outcome" class="case-line">结果：{{ c.outcome }}</p>
            <p v-if="c.lesson" class="case-lesson">经验：{{ c.lesson }}</p>
          </li>
        </ul>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.understanding {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}
.understanding__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  flex: 0 0 auto;
  border-bottom: 1px solid var(--panel-border);
}
.understanding__hd h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 3px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: var(--glow-primary);
}
.tab-bar {
  display: flex;
  gap: 6px;
  padding: 8px 10px 4px;
  flex: 0 0 auto;
}
.tab-btn {
  flex: 1;
  padding: 7px 10px;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-mute);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.16s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.tab-btn.active {
  border-color: var(--primary);
  background: var(--primary-dim);
  color: var(--text);
}
.tab-count {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  background: rgba(0, 229, 255, 0.2);
  color: var(--primary);
}
.tab-body {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sub-tabs {
  display: flex;
  gap: 6px;
  padding: 4px 10px 8px;
  flex: 0 0 auto;
}
.sub-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 6px 8px;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.02);
  color: var(--text-mute);
  cursor: pointer;
  transition: all 0.16s ease;
}
.sub-tab.active {
  border-color: var(--primary);
  background: var(--primary-dim);
  color: var(--text);
}
.sub-tab-label {
  font-size: 11.5px;
  font-weight: 600;
}
.sub-tab-hint {
  font-size: 10px;
  opacity: 0.65;
}
.hint-row {
  padding: 16px 14px;
  font-size: 12.5px;
  color: var(--text-mute);
  text-align: center;
  line-height: 1.5;
}
.hint-row.deposited {
  text-align: left;
  color: var(--text-dim);
}
.exp-list,
.case-list {
  list-style: none;
  margin: 0;
  padding: 0 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.exp-item,
.case-item {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--panel-border);
}
.exp-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--primary-dim);
  color: var(--primary);
  font-weight: 600;
}
.src {
  font-size: 10px;
  color: var(--text-mute);
}
.exp-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-dim);
}
.case-item header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 4px;
}
.case-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}
.case-sim {
  font-size: 11px;
  color: var(--primary);
}
.case-line {
  margin: 3px 0;
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--text-dim);
}
.case-lesson {
  margin: 3px 0 0;
  font-size: 11.5px;
  color: var(--evidence-2);
}
.case-id {
  margin: 0 0 4px;
  font-size: 10.5px;
  color: var(--text-mute);
  letter-spacing: 0.5px;
}

/* —— 行业案例 —— */
.industry-search {
  padding: 0 10px 8px;
  flex: 0 0 auto;
}
.industry-search-input {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text);
  font-size: 12px;
  outline: none;
  transition: border-color 0.16s ease;
}
.industry-search-input::placeholder {
  color: var(--text-mute);
}
.industry-search-input:focus {
  border-color: var(--primary);
}
.industry-list {
  list-style: none;
  margin: 0;
  padding: 0 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.industry-scene {
  border: 1px solid var(--panel-border);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
}
.scene-head {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 11px;
  border: 0;
  background: transparent;
  color: var(--text);
  cursor: pointer;
  text-align: left;
  transition: background 0.16s ease;
}
.scene-head:hover {
  background: rgba(255, 255, 255, 0.03);
}
.scene-head.open {
  background: var(--primary-dim);
}
.scene-caret {
  font-size: 10px;
  color: var(--primary);
  flex: 0 0 auto;
}
.scene-name {
  flex: 1;
  font-size: 12.5px;
  font-weight: 600;
}
.scene-count {
  flex: 0 0 auto;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 10px;
  background: rgba(0, 229, 255, 0.18);
  color: var(--primary);
  font-weight: 600;
}
.scene-body {
  padding: 4px 11px 11px;
  border-top: 1px solid var(--panel-border);
}
.scene-desc {
  margin: 8px 0 10px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-mute);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.problem-block {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid var(--panel-border);
}
.problem-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.problem-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
}
.freq-badge {
  flex: 0 0 auto;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 10px;
  background: var(--primary-dim);
  color: var(--primary);
  font-weight: 600;
}
.freq-badge.alt {
  background: var(--evidence-dim);
  color: var(--evidence-2);
}
.problem-symptoms {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.45;
  color: var(--text-mute);
}
.scheme-block {
  margin: 8px 0 0;
  padding-left: 9px;
  border-left: 2px solid var(--panel-border);
}
.scheme-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 3px;
}
.scheme-name {
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-dim);
}
.scheme-line {
  margin: 2px 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--text-dim);
}
.scheme-caution {
  margin: 2px 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--evidence-2);
}
.rep-cases {
  list-style: none;
  margin: 5px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.rep-case {
  font-size: 10.5px;
  line-height: 1.5;
  color: var(--text-mute);
}
.rep-id {
  color: var(--primary);
  font-weight: 600;
  margin-right: 3px;
}
.rep-title {
  color: var(--text-dim);
}
</style>

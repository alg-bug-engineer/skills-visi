<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { t } from '@/labels/enums'
import { pct } from '@/utils/format'

type PanelTab = 'experience' | 'cases'
type ExpSubTab = 'cognitive' | 'diagnostic' | 'solution'
type CaseSubTab = 'existing' | 'deposited'

const store = usePresentationStore()
const { experiencesByType, existingCases, experienceReady, casesReady } = storeToRefs(store)

const activeTab = ref<PanelTab>('experience')
const expSubTab = ref<ExpSubTab>('cognitive')
const caseSubTab = ref<CaseSubTab>('existing')

const expSubTabs: Array<{ key: ExpSubTab; label: string; hint: string }> = [
  { key: 'cognitive', label: '认知经验', hint: '问题记录' },
  { key: 'diagnostic', label: '诊断经验', hint: '成因先验' },
  { key: 'solution', label: '方案经验', hint: '量化方案' },
]

const caseSubTabs: Array<{ key: CaseSubTab; label: string; hint: string }> = [
  { key: 'existing', label: '已有案例', hint: '相似检索' },
  { key: 'deposited', label: '沉淀案例', hint: '本次固化' },
]

const activeExpList = computed(() => experiencesByType.value[expSubTab.value])
const expCount = computed(
  () =>
    experiencesByType.value.cognitive.length +
    experiencesByType.value.diagnostic.length +
    experiencesByType.value.solution.length,
)

function openCases() {
  activeTab.value = 'cases'
  caseSubTab.value = 'existing'
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

      <template v-if="caseSubTab === 'existing'">
        <div v-if="!casesReady" class="hint-row">待检索…成因分析完成后展示相似案例</div>
        <div v-else-if="!existingCases.length" class="hint-row">暂无高相似历史案例</div>
        <ul v-else class="case-list">
          <li v-for="(c, i) in existingCases" :key="c.case_id ?? i" class="case-item">
            <header>
              <span class="case-title">{{ c.title ?? '案例' }}</span>
              <span v-if="c.similarity != null" class="case-sim">{{ pct(c.similarity, 0) }}</span>
            </header>
            <p v-if="c.action || c.historical_action" class="case-line">
              措施：{{ c.action ?? c.historical_action }}
            </p>
            <p v-if="c.outcome" class="case-line">结果：{{ c.outcome }}</p>
            <p v-if="c.lesson" class="case-lesson">经验：{{ c.lesson }}</p>
          </li>
        </ul>
      </template>

      <template v-else>
        <div class="hint-row deposited">
          本次处置完成后，诊断结论与治理方案将沉淀为新案例，供后续相似场景检索复用。
        </div>
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
</style>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { fetchIndustryCases, fetchIntersectionCases } from '../api/client'
import type { IndustryCaseScenario, IntersectionCase } from '../types/experience'
import { filterIndustryCases, type CaseSubTab, type ParsedCaseRef } from '../utils/caseReference'

const subTab = ref<CaseSubTab>('industry')

const industry = ref<IndustryCaseScenario[]>([])
const industryLoading = ref(false)
const industryError = ref<string | null>(null)
let industryLoaded = false

const intersections = ref<IntersectionCase[]>([])
const interLoading = ref(false)
const interError = ref<string | null>(null)
let interLoaded = false

const query = ref('')
const expandedScenario = ref<string | null>(null)
const highlightedKey = ref<string | null>(null)

const subTabs: Array<{ key: CaseSubTab; label: string; hint: string }> = [
  { key: 'industry', label: '行业案例', hint: '专家经验库' },
  { key: 'intersection', label: '路口案例', hint: '历史诊断方案' },
]

async function loadIndustry(force = false) {
  if (industryLoaded && !force) return
  industryLoading.value = true
  industryError.value = null
  try {
    industry.value = await fetchIndustryCases()
    industryLoaded = true
  } catch (err) {
    industryError.value = err instanceof Error ? err.message : '加载行业案例失败'
  } finally {
    industryLoading.value = false
  }
}

async function loadIntersections(force = false) {
  if (interLoaded && !force) return
  interLoading.value = true
  interError.value = null
  try {
    intersections.value = await fetchIntersectionCases()
    interLoaded = true
  } catch (err) {
    interError.value = err instanceof Error ? err.message : '加载路口案例失败'
  } finally {
    interLoading.value = false
  }
}

function selectSub(tab: CaseSubTab) {
  subTab.value = tab
  if (tab === 'industry') void loadIndustry()
  else void loadIntersections()
}

function toggleScenario(id: string) {
  expandedScenario.value = expandedScenario.value === id ? null : id
}

const filteredIndustry = () => filterIndustryCases(industry.value, query.value)

/** 供外部（治理建议参考依据点击）定位案例。 */
async function openRef(ref: ParsedCaseRef) {
  selectSub(ref.subTab)
  if (ref.subTab === 'industry') {
    await loadIndustry()
    expandedScenario.value = ref.key
  } else {
    await loadIntersections()
  }
  highlightedKey.value = ref.key
  await nextTick()
  const el = document.querySelector<HTMLElement>(`[data-case-anchor="${ref.subTab}:${ref.key}"]`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  window.setTimeout(() => {
    if (highlightedKey.value === ref.key) highlightedKey.value = null
  }, 2400)
}

defineExpose({ openRef })

onMounted(() => loadIndustry())
</script>

<template>
  <div class="case-library">
    <div class="sub-tabs" role="tablist">
      <button
        v-for="t in subTabs"
        :key="t.key"
        type="button"
        role="tab"
        class="sub-tab"
        :class="{ active: subTab === t.key }"
        :aria-selected="subTab === t.key"
        :data-testid="`case-subtab-${t.key}`"
        @click="selectSub(t.key)"
      >
        <span class="sub-tab-label">{{ t.label }}</span>
        <span class="sub-tab-hint">{{ t.hint }}</span>
      </button>
    </div>

    <!-- 行业案例 -->
    <div v-if="subTab === 'industry'" class="pane">
      <div class="search-row">
        <input
          v-model="query"
          type="search"
          class="search-input"
          placeholder="搜索场景 / 典型问题，如：学校、绿波、空放"
        />
      </div>
      <div v-if="industryLoading" class="hint-row">加载中…</div>
      <div v-else-if="industryError" class="hint-row error">{{ industryError }}</div>
      <div v-else-if="!filteredIndustry().length" class="hint-row">未匹配到行业案例。</div>
      <ul v-else class="scenario-list">
        <li
          v-for="sc in filteredIndustry()"
          :key="sc.scenario_id"
          class="scenario"
          :class="{ highlighted: highlightedKey === sc.scenario_id }"
          :data-case-anchor="`industry:${sc.scenario_id}`"
        >
          <button type="button" class="scenario-head" @click="toggleScenario(sc.scenario_id)">
            <span class="caret" :class="{ open: expandedScenario === sc.scenario_id }">▸</span>
            <span class="scenario-name">{{ sc.scenario_name }}</span>
            <span class="scenario-count">{{ sc.case_count }} 例</span>
          </button>
          <div v-show="expandedScenario === sc.scenario_id" class="scenario-body">
            <p v-if="sc.description" class="scenario-desc">{{ sc.description }}</p>
            <div v-for="(p, pi) in sc.problems" :key="pi" class="problem">
              <div class="problem-head">
                <span class="problem-name">典型问题 · {{ p.problem }}</span>
                <span v-if="p.occurrence" class="freq">{{ p.occurrence }} 次</span>
              </div>
              <p v-if="p.symptoms.length" class="symptoms">表现：{{ p.symptoms.join('、') }}</p>
              <div v-for="(s, si) in p.solutions" :key="si" class="solution">
                <div class="solution-head">
                  <span class="solution-name">治理方案 · {{ s.name }}</span>
                  <span v-if="s.frequency" class="freq">{{ s.frequency }}</span>
                </div>
                <p v-if="s.measures.length" class="measures">关键措施：{{ s.measures.join('、') }}</p>
                <p v-if="s.applicability" class="meta">适用条件：{{ s.applicability }}</p>
                <p v-if="s.caution" class="meta caution">注意事项：{{ s.caution }}</p>
                <ul v-if="s.representative_cases.length" class="rep-cases">
                  <li v-for="rc in s.representative_cases" :key="rc.id" class="rep-case">
                    <span class="rep-id">#{{ rc.id }}</span>
                    <span class="rep-title">{{ rc.title }}</span>
                    <p class="rep-snippet">{{ rc.snippet }}</p>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <!-- 路口案例 -->
    <div v-else class="pane">
      <div v-if="interLoading" class="hint-row">加载中…</div>
      <div v-else-if="interError" class="hint-row error">{{ interError }}</div>
      <div v-else-if="!intersections.length" class="hint-row">
        暂无路口案例。完成诊断并固化治理方案后，将沉淀为可复用的路口案例。
      </div>
      <ul v-else class="inter-list">
        <li
          v-for="c in intersections"
          :key="c.inter_id"
          class="inter-case"
          :class="{ highlighted: highlightedKey === c.inter_id }"
          :data-case-anchor="`intersection:${c.inter_id}`"
        >
          <div class="inter-head">
            <span class="inter-name">{{ c.intersection || c.inter_id }}</span>
            <span v-if="c.time_period_label" class="inter-time">{{ c.time_period_label }}</span>
          </div>
          <div v-if="c.cognition.length" class="seg">
            <span class="seg-label">场景认知</span>
            <p v-for="(cog, i) in c.cognition" :key="i" class="seg-line">
              <span class="dot" :class="`st-${cog.status}`" />{{ cog.text }}
            </p>
          </div>
          <div v-if="c.diagnosis.length" class="seg">
            <span class="seg-label">诊断成因</span>
            <p v-for="(d, i) in c.diagnosis" :key="i" class="seg-line">
              {{ d.cause }}<span v-if="d.dimension" class="dim">（{{ d.dimension }}）</span>
            </p>
          </div>
          <div v-if="c.solutions.length" class="seg">
            <span class="seg-label">治理方案与成效</span>
            <p v-for="(s, i) in c.solutions" :key="i" class="seg-line solution-line">
              {{ s.solution_measure || s.qualitative || s.skill_id }}
              <span v-if="s.quantified" class="quant">{{ s.quantified }}</span>
              <a v-if="s.download_url" :href="s.download_url" class="dl" target="_blank">下载技能包</a>
            </p>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.case-library {
  display: flex;
  flex-direction: column;
  min-height: 0;
  color: #d6e4f0;
}

.sub-tabs {
  display: flex;
  gap: 6px;
  padding: 8px 10px 4px;
}

.sub-tab {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 7px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  color: rgba(200, 212, 224, 0.72);
  cursor: pointer;
  transition: all 0.16s ease;
}

.sub-tab:hover {
  border-color: rgba(0, 229, 255, 0.3);
  color: rgba(220, 235, 245, 0.95);
}

.sub-tab.active {
  border-color: rgba(0, 229, 255, 0.55);
  background: rgba(0, 229, 255, 0.08);
  color: #d6f5ff;
}

.sub-tab-label {
  font-size: 12px;
  font-weight: 600;
}

.sub-tab-hint {
  font-size: 9px;
  opacity: 0.6;
}

.pane {
  padding: 6px 10px 12px;
  overflow-y: auto;
}

.search-row {
  margin-bottom: 8px;
}

.search-input {
  width: 100%;
  padding: 6px 9px;
  border-radius: 6px;
  border: 1px solid rgba(94, 184, 255, 0.2);
  background: rgba(8, 16, 30, 0.5);
  color: #e0f2fe;
  font-size: 12px;
}

.hint-row {
  padding: 14px 8px;
  font-size: 12px;
  color: rgba(186, 215, 240, 0.55);
  line-height: 1.6;
}

.hint-row.error {
  color: #fca5a5;
}

.scenario-list,
.inter-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.scenario {
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
}

.scenario.highlighted,
.inter-case.highlighted {
  border-color: rgba(56, 189, 248, 0.7);
  box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.35);
}

.scenario-head {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 9px 10px;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
  font: inherit;
}

.caret {
  font-size: 10px;
  transition: transform 0.18s ease;
  color: rgba(125, 211, 252, 0.7);
}

.caret.open {
  transform: rotate(90deg);
}

.scenario-name {
  flex: 1;
  font-size: 12.5px;
  font-weight: 600;
}

.scenario-count {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  background: rgba(56, 189, 248, 0.16);
  color: #7dd3fc;
}

.scenario-body {
  padding: 0 12px 10px;
}

.scenario-desc {
  margin: 0 0 8px;
  font-size: 11px;
  line-height: 1.6;
  color: rgba(190, 215, 235, 0.78);
}

.problem {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(120, 140, 160, 0.18);
}

.problem-head,
.solution-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.problem-name {
  flex: 1;
  font-size: 12px;
  font-weight: 600;
  color: #bae6fd;
}

.solution-name {
  flex: 1;
  font-size: 11.5px;
  font-weight: 600;
  color: #e0f2fe;
}

.freq {
  font-size: 9px;
  color: #7dd3fc;
  padding: 0 5px;
  border-radius: 6px;
  background: rgba(56, 189, 248, 0.12);
}

.symptoms,
.measures,
.meta {
  margin: 4px 0 0;
  font-size: 11px;
  line-height: 1.55;
  color: rgba(200, 222, 240, 0.82);
}

.meta.caution {
  color: rgba(251, 191, 36, 0.85);
}

.solution {
  margin-top: 8px;
  padding: 8px;
  border-radius: 6px;
  background: rgba(8, 16, 30, 0.4);
}

.rep-cases {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.rep-case {
  padding: 5px 7px;
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.02);
  border-left: 2px solid rgba(56, 189, 248, 0.4);
}

.rep-id {
  font-size: 10px;
  color: #7dd3fc;
  margin-right: 6px;
}

.rep-title {
  font-size: 11px;
  font-weight: 600;
  color: rgba(224, 242, 254, 0.92);
}

.rep-snippet {
  margin: 2px 0 0;
  font-size: 10.5px;
  line-height: 1.5;
  color: rgba(180, 205, 225, 0.7);
}

.inter-case {
  padding: 10px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
}

.inter-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.inter-name {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: #e0f2fe;
}

.inter-time {
  font-size: 10px;
  color: #7dd3fc;
}

.seg {
  margin-top: 7px;
}

.seg-label {
  display: inline-block;
  margin-bottom: 3px;
  font-size: 10px;
  letter-spacing: 0.5px;
  color: rgba(125, 211, 252, 0.85);
}

.seg-line {
  margin: 2px 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: rgba(210, 228, 244, 0.9);
}

.seg-line .dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  background: rgba(148, 196, 230, 0.5);
}

.seg-line .dot.st-verified {
  background: #4ade80;
}

.seg-line .dot.st-data_doubt {
  background: #fbbf24;
}

.dim {
  font-size: 10px;
  color: rgba(160, 190, 215, 0.7);
}

.solution-line .quant {
  margin-left: 6px;
  font-size: 10.5px;
  color: #7dd3fc;
}

.dl {
  margin-left: 8px;
  font-size: 10px;
  color: #38bdf8;
}
</style>

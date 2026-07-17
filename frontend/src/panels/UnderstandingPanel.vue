<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { t, labelAny, directionMovement, translatePlanId } from '@/labels/enums'
import type { PanelExperience, PanelInterCase } from '@/stores/presentation'
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

// 代表案例 id 在多个方案/问题下会重复出现，若直接用 `industry-case-<id>` 作锚点会产生
// 重复 DOM id（无效 HTML，且破坏跳转的 getElementById 定位）。这里为每条案例
// 计算一个唯一锚点：`industry-case-<sceneId>-<caseId>`，仅赋给该场景内首次出现者。
type DecoratedCase = IndustryCase & { anchorId?: string }
type DecoratedScheme = Omit<IndustryScheme, 'cases'> & { cases: DecoratedCase[] }
type DecoratedProblem = Omit<IndustryProblem, 'schemes'> & { schemes: DecoratedScheme[] }
type DecoratedScene = Omit<IndustryScene, 'problems'> & { problems: DecoratedProblem[] }

const decoratedScenes: DecoratedScene[] = scenes.map((s) => {
  const seen = new Set<string>()
  return {
    ...s,
    problems: s.problems.map((p) => ({
      ...p,
      schemes: p.schemes.map((sc) => ({
        ...sc,
        cases: sc.cases.map((c) => {
          if (seen.has(c.id)) return { ...c }
          seen.add(c.id)
          return { ...c, anchorId: `industry-case-${s.sceneId}-${c.id}` }
        }),
      })),
    })),
  }
})

const store = usePresentationStore()
const { precipExperiencesByType, precipInterCases, precipIndustryCases, precipLoading } = storeToRefs(store)

const activeTab = ref<PanelTab>('experience')
const expSubTab = ref<ExpSubTab>('cognitive')
const caseSubTab = ref<CaseSubTab>('industry')

const expSubTabs: Array<{ key: ExpSubTab; label: string; hint: string }> = [
  { key: 'cognitive', label: '认知经验', hint: '吸收·画像' },
  { key: 'diagnostic', label: '诊断经验', hint: '理解·成因' },
  { key: 'solution', label: '方案经验', hint: '使用·处置' },
]

const caseSubTabs: Array<{ key: CaseSubTab; label: string; hint: string }> = [
  { key: 'industry', label: '行业案例', hint: '专家先验' },
  { key: 'intersection', label: '路口案例', hint: '沉淀·确认' },
]

const activeExpList = computed(() => precipExperiencesByType.value[expSubTab.value])

const totalExperiences = computed(
  () =>
    precipExperiencesByType.value.cognitive.length +
    precipExperiencesByType.value.diagnostic.length +
    precipExperiencesByType.value.solution.length,
)

// —— 结构化标签 chips ——
function chipText(v: unknown): string {
  if (v == null) return ''
  if (Array.isArray(v)) return v.map((x) => String(x)).filter(Boolean).join('/')
  return String(v)
}

function dedupChips(chips: string[]): string[] {
  return [...new Set(chips.filter((c) => c && c !== '—'))]
}

/** 修复历史数据中 diagnosis_scope 被逐字 join 的脏标签。 */
function normalizeSpatialStructure(v: unknown): string {
  const raw = chipText(v).trim()
  if (!raw) return ''
  const parts = raw.split(/,\s*/).filter(Boolean)
  if (parts.length > 3 && parts.every((p) => p.length <= 2)) {
    return parts.join('')
  }
  return labelAny(raw)
}

function caseDisplayTitle(c: PanelInterCase): string {
  const raw = c.title ?? c.plan_id ?? '案例'
  return translatePlanId(chipText(raw))
}

function caseDisplayId(c: PanelInterCase): string {
  if (c.plan_id) return translatePlanId(chipText(c.plan_id))
  if (!c.case_id) return ''
  const id = String(c.case_id)
  if (!/^(recommended|risk)_/i.test(id)) return id
  const tail = id.split('_').pop() ?? id
  return translatePlanId(tail)
}

function expChips(e: PanelExperience): string[] {
  const tags = (e.tags ?? {}) as Record<string, unknown>
  const chips: string[] = []
  const inter = e.intersection_name ?? tags.intersection_name
  if (inter) chips.push(chipText(inter))
  if (tags.problem_type) chips.push(t('problem_type', chipText(tags.problem_type)))
  if (tags.time_period) chips.push(t('period', chipText(tags.time_period)))
  const dm = directionMovement(chipText(tags.direction) || null, chipText(tags.movement) || null)
  if (dm && dm !== '—') chips.push(dm)
  if (tags.cause_dimension) chips.push(labelAny(chipText(tags.cause_dimension)))
  if (tags.strategy_action) chips.push(labelAny(chipText(tags.strategy_action)))
  if (Array.isArray(tags.related_poi) && tags.related_poi.length) chips.push(chipText(tags.related_poi))
  const structured = e.structured_tags ?? {}
  for (const values of Object.values(structured)) {
    for (const v of values ?? []) chips.push(String(v))
  }
  return dedupChips(chips)
}

function structuredTagChips(tags?: Record<string, string[]> | null): string[] {
  if (!tags) return []
  const chips: string[] = []
  for (const [group, values] of Object.entries(tags)) {
    for (const v of values ?? []) {
      chips.push(`${group}·${v}`)
    }
  }
  return dedupChips(chips)
}

function caseChips(c: PanelInterCase): string[] {
  const tags = (c.tags ?? {}) as Record<string, unknown>
  const chips: string[] = []
  if (c.intersection_name) chips.push(chipText(c.intersection_name))
  if (c.time_period) chips.push(t('period', chipText(c.time_period)))
  if (tags.problem_type) chips.push(t('problem_type', chipText(tags.problem_type)))
  if (tags.strategy_applied) chips.push(labelAny(chipText(tags.strategy_applied)))
  const spatial = normalizeSpatialStructure(tags.spatial_structure)
  if (spatial) chips.push(spatial)
  for (const chip of structuredTagChips(c.structured_tags)) chips.push(chip)
  return dedupChips(chips)
}

// —— 行业案例：优先离线结构化沉淀；无数据时回退专家场景树 ——
const industryQuery = ref('')
const expandedScenes = ref<Set<string>>(new Set())

const searching = computed(() => industryQuery.value.trim().length > 0)

const filteredIndustryCases = computed(() => {
  const rows = precipIndustryCases.value ?? []
  const q = industryQuery.value.trim().toLowerCase()
  if (!q) return rows
  return rows.filter((c) => {
    const blob = [
      c.title,
      c.scene,
      c.diagnosis,
      c.solution,
      JSON.stringify(c.structured_tags ?? {}),
    ]
      .join(' ')
      .toLowerCase()
    return blob.includes(q)
  })
})

const filteredScenes = computed(() => {
  const q = industryQuery.value.trim().toLowerCase()
  if (!q) return decoratedScenes
  return decoratedScenes.filter((s) => {
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

function isSceneOpen(sceneId: string): boolean {
  return searching.value || expandedScenes.value.has(sceneId)
}
function toggleScene(sceneId: string) {
  const next = new Set(expandedScenes.value)
  next.has(sceneId) ? next.delete(sceneId) : next.add(sceneId)
  expandedScenes.value = next
}

interface OpenCaseDetail {
  tab?: 'industry' | 'intersection'
  refId?: string | null
  sceneId?: string | null
}

/**
 * 案例库导航：右侧闭环卡片「参考依据」点击 → 切 tab → 必要时展开目标场景
 * → nextTick 后滚动定位并短暂高亮。scrollIntoView 在 jsdom 缺失，做可选调用降级。
 */
async function openCases(e?: Event) {
  const detail = (e as CustomEvent | undefined)?.detail as OpenCaseDetail | undefined
  activeTab.value = 'cases'
  caseSubTab.value = detail?.tab === 'intersection' ? 'intersection' : 'industry'

  if (caseSubTab.value === 'industry' && detail?.sceneId) {
    const next = new Set(expandedScenes.value)
    next.add(detail.sceneId)
    expandedScenes.value = next
  }

  await nextTick()
  const refId = detail?.refId
  if (!refId) return
  const el = typeof document !== 'undefined' ? document.getElementById(refId) : null
  if (!el) return
  el.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
  el.classList.add('nav-flash')
  window.setTimeout(() => el.classList.remove('nav-flash'), 1600)
}

onMounted(() => {
  window.addEventListener('open-case-library', openCases as EventListener)
  // 沉淀面板进入即呈现全量历史沉淀（不依赖本轮推演）。
  void store.loadPrecipitation()
})
onBeforeUnmount(() => window.removeEventListener('open-case-library', openCases as EventListener))
</script>

<template>
  <aside class="understanding us-panel" data-testid="understanding-panel">
    <header class="understanding__hd">
      <span class="dot" />
      <div class="hd-text">
        <h2>沉淀面板</h2>
        <span class="hd-sub">吸收 · 理解 · 使用 · 沉淀</span>
      </div>
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
        <span v-if="totalExperiences" class="tab-count">{{ totalExperiences }}</span>
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
      </button>
    </div>

    <!-- 经验库：全量历史沉淀 -->
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

      <div v-if="precipLoading && !activeExpList.length" class="hint-row">加载沉淀经验…</div>
      <div v-else-if="!activeExpList.length" class="hint-row">
        暂无{{ expSubTabs.find((s) => s.key === expSubTab)?.label }}沉淀
      </div>
      <ul v-else class="exp-list">
        <li
          v-for="(e, i) in activeExpList"
          :key="e.record_id ?? i"
          class="exp-item"
          :class="{ fresh: e.fresh }"
          data-testid="exp-item"
        >
          <div class="exp-item-head">
            <span class="badge">{{ t('experience_type', e.experience_type) }}</span>
            <span v-if="e.fresh" class="fresh-badge" data-testid="exp-fresh">本轮新吸收</span>
            <span v-if="e.source_span" class="src">{{ e.source_span }}</span>
          </div>
          <p class="exp-text">{{ e.content }}</p>
          <div v-if="expChips(e).length" class="chip-row">
            <span v-for="(chip, ci) in expChips(e)" :key="ci" class="chip">{{ chip }}</span>
          </div>
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

      <!-- 行业案例：离线结构化沉淀优先；无沉淀时回退专家场景树 -->
      <template v-if="caseSubTab === 'industry'">
        <div class="industry-search">
          <input
            v-model="industryQuery"
            type="search"
            class="industry-search-input"
            data-testid="industry-search"
            placeholder="浏览场景 / 标签 / 措施"
          />
        </div>

        <template v-if="(precipIndustryCases?.length ?? 0) > 0">
          <div v-if="precipLoading && !filteredIndustryCases.length" class="hint-row">加载行业结构化案例…</div>
          <div v-else-if="!filteredIndustryCases.length" class="hint-row">未匹配到行业案例</div>
          <ul v-else class="case-list" data-testid="industry-structured-list">
            <li
              v-for="(c, i) in filteredIndustryCases"
              :key="c.case_id ?? i"
              :id="'industry-struct-' + (c.case_id ?? i)"
              class="case-item"
              data-testid="industry-structured-case"
            >
              <header>
                <span class="case-title">{{ c.title || c.scene || '行业案例' }}</span>
                <span class="case-cat cat-textbook">行业</span>
              </header>
              <div v-if="structuredTagChips(c.structured_tags).length" class="chip-row">
                <span
                  v-for="(chip, ci) in structuredTagChips(c.structured_tags)"
                  :key="ci"
                  class="chip"
                  >{{ chip }}</span
                >
              </div>
              <p v-if="c.diagnosis" class="case-line">诊断：{{ String(c.diagnosis).slice(0, 120) }}</p>
              <p v-if="c.solution" class="case-line">措施：{{ String(c.solution).slice(0, 120) }}</p>
              <p v-if="c.effect" class="case-lesson">效果：{{ String(c.effect).slice(0, 100) }}</p>
            </li>
          </ul>
        </template>

        <template v-else>
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
                :aria-expanded="isSceneOpen(s.sceneId)"
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
                        v-for="(c, ci) in sc.cases"
                        :key="ci"
                        :id="c.anchorId"
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
      </template>

      <!-- 路口案例：全量确认/风险沉淀方案 + 本轮检索到的相似案例（置顶） -->
      <template v-else>
        <div v-if="precipLoading && !precipInterCases.length" class="hint-row">加载路口沉淀案例…</div>
        <div v-else-if="!precipInterCases.length" class="hint-row">暂无路口沉淀案例</div>
        <ul v-else class="case-list">
          <li
            v-for="(c, i) in precipInterCases"
            :key="c.case_id ?? i"
            :id="'inter-case-' + (c.case_id ?? i)"
            class="case-item"
            :class="{ fresh: c.fresh }"
            data-testid="inter-case"
          >
            <header>
              <span class="case-title">{{ caseDisplayTitle(c) }}</span>
              <span
                v-if="c.category"
                class="case-cat"
                :class="'cat-' + c.category"
                >{{ t('category', c.category) }}</span
              >
            </header>
            <div v-if="c.fresh" class="fresh-badge" data-testid="case-fresh">本轮检索/新确认</div>
            <p v-if="c.case_id" class="case-id">案例编号：{{ caseDisplayId(c) }}</p>
            <div v-if="caseChips(c).length" class="chip-row">
              <span v-for="(chip, ci) in caseChips(c)" :key="ci" class="chip">{{ chip }}</span>
            </div>
            <p v-if="c.action || c.historical_action" class="case-line">
              措施：{{ c.action ?? c.historical_action }}
            </p>
            <p v-if="c.outcome" class="case-line">结果：{{ c.outcome }}</p>
            <p v-if="c.lesson" class="case-lesson">经验：{{ c.lesson }}</p>
            <a
              v-if="c.skill && c.skill.download_url"
              class="skill-dl"
              :href="c.skill.download_url"
              data-testid="skill-download"
              download
            >
              ⤓ 下载技能包
            </a>
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
  gap: 10px;
  padding: 12px 14px;
  flex: 0 0 auto;
  border-bottom: 1px solid var(--panel-border);
}
.hd-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.understanding__hd h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 3px;
}
.hd-sub {
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--text-mute);
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
  border-radius: var(--radius-sm);
  background: rgba(26, 127, 255, 0.2);
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
.exp-item.fresh,
.case-item.fresh {
  border-color: var(--primary);
  background: var(--primary-dim);
}
.exp-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--primary-dim);
  color: var(--primary);
  font-weight: 600;
}
.fresh-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: rgba(26, 127, 255, 0.22);
  color: var(--primary);
  font-weight: 600;
  margin: 2px 0;
  align-self: flex-start;
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
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 7px;
}
.chip {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--panel-border);
  color: var(--text-mute);
  line-height: 1.4;
}
.case-item header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}
.case-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
}
.case-cat {
  flex: 0 0 auto;
  font-size: 10px;
  padding: 1px 7px;
  border-radius: var(--radius-sm);
  font-weight: 600;
  background: var(--primary-dim);
  color: var(--primary);
}
.case-cat.cat-risk {
  background: var(--evidence-dim);
  color: var(--evidence-2);
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
.skill-dl {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  padding: 5px 10px;
  border: 1px solid var(--primary);
  border-radius: var(--radius-sm);
  background: var(--primary-dim);
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.16s ease;
}
.skill-dl:hover {
  background: rgba(26, 127, 255, 0.22);
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
  border-radius: var(--radius-sm);
  background: rgba(26, 127, 255, 0.18);
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
  border-radius: var(--radius-sm);
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
.rep-snippet {
  color: var(--text-mute);
}

/* 点击「参考依据」定位后的短暂高亮（subtle，2 次呼吸后自然褪去）。 */
.nav-flash {
  animation: nav-flash 1.6s ease-out;
}
@keyframes nav-flash {
  0%,
  100% {
    box-shadow: none;
  }
  15% {
    box-shadow: inset 0 0 0 1px var(--primary), var(--glow-primary);
    background: var(--primary-dim);
  }
}
</style>

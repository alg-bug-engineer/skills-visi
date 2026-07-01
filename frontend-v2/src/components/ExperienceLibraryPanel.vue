<script setup lang="ts">
import { ref, watch } from 'vue'
import type { SkillLeaderboardItem, SkillLeaderboardSort } from '../types/skillLeaderboard'
import SkillLeaderboardPanel from './SkillLeaderboardPanel.vue'
import { useExperienceLibrary } from '../composables/useExperienceLibrary'
import { cognitionDisplaySummary } from '../utils/textFormat'

const props = defineProps<{
  /** 方案经验：复用技能榜数据 */
  items: SkillLeaderboardItem[]
  loading: boolean
  error: string | null
  sort: SkillLeaderboardSort
  expandedId: string | null
  active: boolean
  refreshKey?: number
  /** 当前路口；空则聚合全部 */
  interId?: string | null
}>()

const emit = defineEmits<{
  setSort: [sort: SkillLeaderboardSort]
  toggle: [skillId: string]
  retry: []
}>()

type SubTab = 'cognition' | 'diagnosis' | 'solution'
const subTab = ref<SubTab>('solution')

const lib = useExperienceLibrary()

const subTabs: Array<{ key: SubTab; label: string; hint: string }> = [
  { key: 'cognition', label: '认知经验', hint: '问题记录' },
  { key: 'diagnosis', label: '诊断经验', hint: '成因先验' },
  { key: 'solution', label: '方案经验', hint: '量化方案' },
]

const statusLabel: Record<string, string> = {
  verified: '已验证',
  data_doubt: '数据存疑',
  manual: '人工录入',
}

function hasStructured(structured: {
  time_period?: string
  directions?: string[]
  movement?: string
  phenomenon?: string
}) {
  return Boolean(
    structured.time_period ||
      structured.directions?.length ||
      structured.movement ||
      structured.phenomenon,
  )
}

function loadProfileBuckets(force = false) {
  void lib.load(props.interId, force)
}

function selectSub(tab: SubTab) {
  subTab.value = tab
  if (tab !== 'solution') loadProfileBuckets()
}

watch(
  () => props.active,
  (isActive) => {
    if (isActive && subTab.value !== 'solution') loadProfileBuckets()
  },
)

watch(
  () => props.refreshKey,
  () => {
    if (props.active && subTab.value !== 'solution') loadProfileBuckets(true)
  },
)
</script>

<template>
  <div class="exp-library">
    <div class="sub-tabs" role="tablist">
      <button
        v-for="t in subTabs"
        :key="t.key"
        type="button"
        role="tab"
        class="sub-tab"
        :class="{ active: subTab === t.key }"
        :aria-selected="subTab === t.key"
        :data-testid="`exp-subtab-${t.key}`"
        @click="selectSub(t.key)"
      >
        <span class="sub-tab-label">{{ t.label }}</span>
        <span class="sub-tab-hint">{{ t.hint }}</span>
      </button>
    </div>

    <!-- 方案经验：复用技能榜 -->
    <SkillLeaderboardPanel
      v-if="subTab === 'solution'"
      :items="items"
      :loading="loading"
      :error="error"
      :sort="sort"
      :expanded-id="expandedId"
      :active="active && subTab === 'solution'"
      :refresh-key="refreshKey"
      @set-sort="emit('setSort', $event)"
      @toggle="emit('toggle', $event)"
      @retry="emit('retry')"
    />

    <!-- 认知经验 -->
    <div v-else-if="subTab === 'cognition'" class="bucket">
      <div v-if="lib.loading.value" class="hint-row">加载中…</div>
      <div v-else-if="lib.error.value" class="hint-row error">{{ lib.error.value }}</div>
      <div v-else-if="!lib.cognition.value.length" class="hint-row">
        暂无认知经验。完成问题识别后，问题记录将沉淀于此。
      </div>
      <ul v-else class="exp-list">
        <li v-for="(c, i) in lib.cognition.value" :key="i" class="exp-item">
          <div class="exp-item-head">
            <span class="badge" :class="`st-${c.status}`">{{ statusLabel[c.status] ?? c.status }}</span>
            <span class="src">{{ c.source === 'user' ? '用户' : '数据' }}</span>
          </div>
          <p v-if="c.intersection" class="exp-intersection">{{ c.intersection }}</p>
          <div v-if="c.tags?.length" class="tag-row">
            <span v-for="tag in c.tags" :key="tag" class="tag">{{ tag }}</span>
          </div>
          <p class="exp-text">{{ cognitionDisplaySummary(c) }}</p>
          <dl v-if="c.structured && hasStructured(c.structured)" class="exp-structured">
            <template v-if="c.structured.time_period">
              <dt>时段</dt>
              <dd>{{ c.structured.time_period }}</dd>
            </template>
            <template v-if="c.structured.directions?.length">
              <dt>方向</dt>
              <dd>{{ c.structured.directions.join('、') }}</dd>
            </template>
            <template v-if="c.structured.movement">
              <dt>转向</dt>
              <dd>{{ c.structured.movement }}</dd>
            </template>
            <template v-if="c.structured.phenomenon">
              <dt>现象</dt>
              <dd>{{ c.structured.phenomenon }}</dd>
            </template>
          </dl>
        </li>
      </ul>
    </div>

    <!-- 诊断经验 -->
    <div v-else class="bucket">
      <div v-if="lib.loading.value" class="hint-row">加载中…</div>
      <div v-else-if="lib.error.value" class="hint-row error">{{ lib.error.value }}</div>
      <div v-else-if="!lib.diagnosis.value.length" class="hint-row">
        暂无诊断经验。完成归因后，成因先验将沉淀于此。
      </div>
      <ul v-else class="exp-list">
        <li v-for="(d, i) in lib.diagnosis.value" :key="i" class="exp-item">
          <div class="exp-item-head">
            <span class="badge dim">{{ d.dimension }}</span>
            <span v-if="d.confidence" class="conf">置信 {{ Math.round(d.confidence * 100) }}%</span>
            <span class="src">{{ d.source === 'user' ? '用户' : '数据' }}</span>
          </div>
          <p class="exp-text">{{ d.cause }}</p>
          <p v-if="d.scope" class="exp-scope">范围：{{ d.scope }}</p>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.exp-library {
  display: flex;
  flex-direction: column;
  min-height: 0;
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
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.3px;
}

.sub-tab-hint {
  font-size: 9.5px;
  letter-spacing: 0.6px;
  opacity: 0.6;
}

.bucket {
  padding: 6px 12px 12px;
  overflow-y: auto;
}

.hint-row {
  padding: 18px 8px;
  font-size: 12px;
  color: rgba(180, 195, 210, 0.6);
  text-align: center;
}

.hint-row.error {
  color: #ff8a7a;
}

.exp-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.exp-item {
  padding: 9px 11px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-left: 2px solid rgba(0, 229, 255, 0.45);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.025);
}

.exp-item-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  color: #cfe;
}

.badge.st-verified {
  background: rgba(60, 220, 130, 0.16);
  color: #6dffb5;
}

.badge.st-data_doubt {
  background: rgba(255, 180, 60, 0.16);
  color: #ffce6d;
}

.badge.st-manual {
  background: rgba(120, 170, 255, 0.16);
  color: #9dc3ff;
}

.badge.dim {
  background: rgba(0, 229, 255, 0.14);
  color: #7fe7ff;
}

.conf,
.src {
  font-size: 10px;
  color: rgba(180, 195, 210, 0.6);
}

.exp-intersection {
  margin: 0 0 4px;
  font-size: 11.5px;
  font-weight: 600;
  color: rgba(224, 236, 245, 0.95);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 5px;
}

.tag {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgba(0, 229, 255, 0.12);
  color: #7fe7ff;
}

.exp-text {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: rgba(224, 236, 245, 0.92);
}

.exp-structured {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 2px 8px;
  margin: 6px 0 0;
  font-size: 10.5px;
}

.exp-structured dt {
  margin: 0;
  color: rgba(160, 190, 215, 0.65);
}

.exp-structured dd {
  margin: 0;
  color: rgba(210, 228, 244, 0.88);
}

.exp-scope {
  margin: 3px 0 0;
  font-size: 11px;
  color: rgba(180, 195, 210, 0.6);
}
</style>

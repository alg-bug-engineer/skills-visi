<script setup lang="ts">
import { onMounted, watch } from 'vue'
import type { SkillLeaderboardItem, SkillLeaderboardSort } from '../types/skillLeaderboard'
import {
  contributorLabel,
  experienceSourceLabel,
  formatLeaderboardTime,
  problemTypeLabel,
  skillChips,
} from '../utils/skillLeaderboardFormat'

const props = defineProps<{
  items: SkillLeaderboardItem[]
  loading: boolean
  error: string | null
  sort: SkillLeaderboardSort
  expandedId: string | null
  active: boolean
  refreshKey?: number
}>()

const emit = defineEmits<{
  setSort: [sort: SkillLeaderboardSort]
  toggle: [skillId: string]
  retry: []
}>()

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

const sortOptions: Array<{ key: SkillLeaderboardSort; label: string }> = [
  { key: 'hits', label: '利用率' },
  { key: 'created', label: '最新' },
  { key: 'updated', label: '更新' },
]

onMounted(() => {
  if (props.active) emit('retry')
})

watch(
  () => props.active,
  (isActive) => {
    if (isActive) emit('retry')
  },
)

watch(
  () => props.refreshKey,
  () => {
    if (props.active) emit('retry')
  },
)

function downloadUrl(item: SkillLeaderboardItem): string {
  return `${API_BASE}${item.download_url}`
}

async function copySkillId(skillId: string) {
  try {
    await navigator.clipboard.writeText(skillId)
  } catch {
    /* ignore clipboard failures */
  }
}

function hitBadgeClass(count: number): string {
  if (count >= 10) return 'hit-high'
  if (count >= 1) return 'hit-mid'
  return 'hit-zero'
}
</script>

<template>
  <section class="leaderboard">
    <div class="sort-bar">
      <span class="sort-label">排序</span>
      <button
        v-for="opt in sortOptions"
        :key="opt.key"
        type="button"
        class="sort-btn"
        :class="{ active: sort === opt.key }"
        @click="emit('setSort', opt.key)"
      >
        {{ opt.label }}
      </button>
      <span v-if="items.length" class="count-badge">{{ items.length }} 条</span>
    </div>

    <div v-if="loading" class="skeleton-list">
      <div v-for="n in 3" :key="n" class="skeleton-row" />
    </div>

    <div v-else-if="error" class="state-box error">
      <p>{{ error }}</p>
      <button type="button" class="retry-btn" @click="emit('retry')">重试</button>
    </div>

    <p v-else-if="!items.length" class="state-box empty">
      暂无沉淀技能。完成诊断并确认固化后，经验将出现在此。
    </p>

    <ol v-else class="skill-list">
      <li
        v-for="(item, index) in items"
        :key="item.skill_id"
        :class="['skill-item', { expanded: expandedId === item.skill_id }]"
      >
        <button type="button" class="skill-head" @click="emit('toggle', item.skill_id)">
          <span class="caret" :class="{ open: expandedId === item.skill_id }" aria-hidden="true" />
          <span class="rank">#{{ index + 1 }}</span>
          <span class="title">{{ item.intersection }}</span>
          <span class="hit-badge" :class="hitBadgeClass(item.hit_count)">
            命中 {{ item.hit_count }}
          </span>
        </button>

        <div class="chip-row">
          <span v-for="chip in skillChips(item)" :key="chip" class="chip">{{ chip }}</span>
        </div>

        <div v-if="expandedId === item.skill_id" class="skill-body">
          <section class="detail-block">
            <h4>沉淀信息</h4>
            <dl>
              <div><dt>创建时间</dt><dd>{{ formatLeaderboardTime(item.created_at) }}</dd></div>
              <div><dt>更新时间</dt><dd>{{ formatLeaderboardTime(item.updated_at) }}</dd></div>
              <div><dt>贡献角色</dt><dd>{{ contributorLabel(item) }}</dd></div>
              <div><dt>经验来源</dt><dd>{{ experienceSourceLabel(item) }}</dd></div>
              <div v-if="item.tags.meta?.source_utterance_summary">
                <dt>来源摘要</dt>
                <dd>{{ item.tags.meta.source_utterance_summary }}</dd>
              </div>
              <div v-if="item.last_hit_at">
                <dt>最近命中</dt>
                <dd>{{ formatLeaderboardTime(item.last_hit_at) }}</dd>
              </div>
            </dl>
          </section>

          <section class="detail-block">
            <h4>匹配标签</h4>
            <dl>
              <div><dt>路口 ID</dt><dd>{{ item.inter_id }}</dd></div>
              <div><dt>时段</dt><dd>{{ item.time_period_label }}</dd></div>
              <div><dt>问题类型</dt><dd>{{ problemTypeLabel(item.problem_type) }}</dd></div>
              <div v-if="item.tags.match?.directions?.length">
                <dt>方向</dt>
                <dd>{{ item.tags.match.directions.join('、') }}</dd>
              </div>
              <div v-if="item.tags.match?.match_keywords?.length">
                <dt>关键词</dt>
                <dd>{{ item.tags.match.match_keywords.join('、') }}</dd>
              </div>
            </dl>
          </section>

          <section class="detail-block">
            <h4>诊断经验</h4>
            <dl>
              <div v-if="item.rule_ids.length">
                <dt>命中规则</dt>
                <dd>{{ item.rule_ids.join('、') }}</dd>
              </div>
              <div v-if="item.tags.content?.issue_codes?.length">
                <dt>问题类型码</dt>
                <dd>{{ item.tags.content.issue_codes.join('、') }}</dd>
              </div>
              <div v-if="item.tags.content?.constraint_intent">
                <dt>约束意图</dt>
                <dd>{{ item.tags.content.constraint_intent }}</dd>
              </div>
              <div v-if="item.user_constraints">
                <dt>用户约束</dt>
                <dd>{{ item.user_constraints }}</dd>
              </div>
              <div v-if="item.suggestion_formula">
                <dt>治理公式</dt>
                <dd class="mono">{{ item.suggestion_formula }}</dd>
              </div>
            </dl>
          </section>

          <div class="actions">
            <a
              class="download-btn"
              :href="downloadUrl(item)"
              target="_blank"
              rel="noopener noreferrer"
            >
              下载 Skill 包
            </a>
            <button type="button" class="copy-btn" @click="copySkillId(item.skill_id)">
              复制 ID
            </button>
          </div>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.leaderboard {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}

.sort-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.sort-label {
  font-size: 11px;
  color: rgba(186, 215, 240, 0.55);
}

.sort-btn {
  padding: 3px 8px;
  border-radius: 2px;
  border: 1px solid rgba(94, 184, 255, 0.25);
  background: transparent;
  color: rgba(186, 230, 253, 0.75);
  font-size: 11px;
  cursor: pointer;
}

.sort-btn.active {
  border-color: rgba(56, 189, 248, 0.55);
  background: rgba(14, 165, 233, 0.12);
  color: #e0f2fe;
}

.count-badge {
  margin-left: auto;
  font-size: 10px;
  color: rgba(125, 211, 252, 0.7);
}

.skeleton-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skeleton-row {
  height: 52px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    rgba(14, 165, 233, 0.06) 0%,
    rgba(56, 189, 248, 0.12) 50%,
    rgba(14, 165, 233, 0.06) 100%
  );
  animation: shimmer 1.4s ease-in-out infinite;
}

@keyframes shimmer {
  0%,
  100% {
    opacity: 0.55;
  }
  50% {
    opacity: 1;
  }
}

.state-box {
  margin: 0;
  padding: 12px;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.6;
  color: rgba(186, 215, 240, 0.55);
  border: 1px dashed rgba(94, 184, 255, 0.18);
}

.state-box.error {
  color: #ffb4b4;
  border-color: rgba(255, 100, 80, 0.25);
}

.retry-btn {
  margin-top: 8px;
  padding: 4px 10px;
  border: 1px solid rgba(94, 184, 255, 0.35);
  border-radius: 2px;
  background: rgba(14, 165, 233, 0.08);
  color: rgba(186, 230, 253, 0.9);
  font-size: 11px;
  cursor: pointer;
}

.skill-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skill-item {
  border-radius: 4px;
  border: 1px solid rgba(94, 184, 255, 0.12);
  background: rgba(8, 16, 30, 0.45);
}

.skill-item.expanded {
  border-color: rgba(56, 189, 248, 0.28);
  background: rgba(8, 20, 36, 0.65);
}

.skill-head {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 8px 10px 4px;
  border: none;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  font: inherit;
}

.caret {
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 5px solid rgba(148, 196, 230, 0.45);
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.caret.open {
  transform: rotate(90deg);
}

.rank {
  flex-shrink: 0;
  font-size: 10px;
  color: rgba(125, 211, 252, 0.75);
  min-width: 1.4em;
}

.title {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-weight: 500;
  color: rgba(224, 242, 254, 0.95);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hit-badge {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 2px;
  font-size: 10px;
  font-weight: 600;
}

.hit-zero {
  color: rgba(186, 215, 240, 0.55);
  background: rgba(148, 196, 230, 0.08);
}

.hit-mid {
  color: #7dd3fc;
  background: rgba(14, 165, 233, 0.12);
}

.hit-high {
  color: #6dffb5;
  background: rgba(109, 255, 181, 0.1);
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 0 10px 8px 26px;
}

.chip {
  padding: 1px 6px;
  border-radius: 2px;
  font-size: 10px;
  color: rgba(186, 230, 253, 0.85);
  background: rgba(14, 165, 233, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.16);
}

.skill-body {
  padding: 0 10px 10px 26px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.detail-block h4 {
  margin: 0 0 6px;
  font-size: 10px;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: rgba(125, 211, 252, 0.75);
}

.detail-block dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-block dl > div {
  display: grid;
  grid-template-columns: 4.5em 1fr;
  gap: 6px;
  font-size: 11px;
  line-height: 1.5;
}

.detail-block dt {
  color: rgba(186, 215, 240, 0.5);
}

.detail-block dd {
  margin: 0;
  color: rgba(224, 242, 254, 0.9);
  word-break: break-word;
}

.detail-block dd.mono {
  font-family: ui-monospace, 'Courier New', monospace;
  font-size: 10px;
}

.actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.download-btn,
.copy-btn {
  padding: 4px 10px;
  border-radius: 2px;
  font-size: 11px;
  cursor: pointer;
  text-decoration: none;
}

.download-btn {
  border: 1px solid rgba(56, 189, 248, 0.35);
  background: rgba(14, 165, 233, 0.12);
  color: #7dd3fc;
}

.copy-btn {
  border: 1px solid rgba(94, 184, 255, 0.25);
  background: transparent;
  color: rgba(186, 230, 253, 0.8);
}
</style>

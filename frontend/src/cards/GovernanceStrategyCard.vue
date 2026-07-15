<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { productCopy } from '@/utils/productCopy'
import BaseCard from './BaseCard.vue'
import expertKnowledge from '@/data/expertKnowledge.json'

interface SceneEntry {
  scene: string
  sceneId: string
}

const store = usePresentationStore()
const strategy = computed(() => store.strategy?.strategy ?? null)
const refBasis = computed(() => store.strategy?.reference_basis ?? null)
const experienceContrast = computed(() => store.strategy?.experience_contrast ?? null)

/** 治理建议要点：原则优先，回落到推荐项，去重后取前 3 条；过滤演示性分析文案。 */
const points = computed<string[]>(() => {
  const blocked = /分析亮点|道路等级画像|本例价值|眼前一亮|三叉诊断/
  const src = [...(strategy.value?.principles ?? []), ...(strategy.value?.recommended ?? [])]
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of src) {
    const s = productCopy(raw)
    if (!s || seen.has(s) || blocked.test(s)) continue
    seen.add(s)
    out.push(s)
    if (out.length >= 3) break
  }
  return out
})

const hardConstraints = computed<string[]>(() => {
  const c = strategy.value?.hard_constraints as unknown
  if (Array.isArray(c)) return c.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
  if (typeof c === 'string' && c.trim()) return [c.trim()]
  return []
})

/** 场景名 → sceneId（构建期专家库匹配；无匹配返回 null，仍渲染 chip）。 */
const industrySceneId = computed<string | null>(() => {
  const name = refBasis.value?.industry_scene
  if (!name) return null
  const entry = (expertKnowledge as SceneEntry[]).find((e) => e.scene === name)
  return entry?.sceneId ?? null
})

const intersectionIds = computed<string[]>(() => refBasis.value?.intersection_case_ids ?? [])

const hasRefChips = computed(
  () => !!refBasis.value?.industry_scene || intersectionIds.value.length > 0,
)

/** 仅当策略或参考依据任一存在才渲染整卡（缺失不显示）。 */
const hasAny = computed(
  () =>
    points.value.length > 0 ||
    hardConstraints.value.length > 0 ||
    hasRefChips.value ||
    (experienceContrast.value?.available && (experienceContrast.value.items?.length ?? 0) > 0),
)

function openIndustry() {
  const sceneId = industrySceneId.value
  window.dispatchEvent(
    new CustomEvent('open-case-library', {
      detail: {
        tab: 'industry',
        refId: sceneId ? `industry-scene-${sceneId}` : null,
        sceneId: sceneId ?? null,
      },
    }),
  )
}

function openIntersection(caseId: string) {
  window.dispatchEvent(
    new CustomEvent('open-case-library', {
      detail: { tab: 'intersection', refId: `inter-case-${caseId}` },
    }),
  )
}
</script>

<template>
  <BaseCard v-if="hasAny" title="治理策略" :act="8" tone="protected">
    <ul v-if="points.length" class="pts">
      <li v-for="(p, i) in points" :key="i">{{ p }}</li>
    </ul>

    <div v-if="hardConstraints.length" class="hard">
      <span class="hard__hd">红线</span>
      <div class="hard__tags">
        <span v-for="(c, i) in hardConstraints" :key="i" class="tag">{{ productCopy(c) }}</span>
      </div>
    </div>

    <div v-if="experienceContrast?.available && experienceContrast.items?.length" class="contrast" data-testid="strategy-experience-contrast">
      <span class="refs__hd">经验对照</span>
      <article v-for="(item, i) in experienceContrast.items.slice(0, 2)" :key="i" class="contrast-row">
        <strong>{{ item.dimension }}</strong>
        <p class="contrast-muted">无经验：{{ productCopy(item.without_experience?.summary) }}</p>
        <p>有经验：{{ productCopy(item.with_experience?.summary) }}</p>
      </article>
    </div>

    <div v-if="hasRefChips" class="refs">
      <span class="refs__hd">参考依据</span>
      <div class="refs__chips">
        <button
          v-if="refBasis?.industry_scene"
          type="button"
          class="chip"
          data-testid="ref-chip"
          @click="openIndustry"
        >
          行业·{{ refBasis.industry_scene }}
        </button>
        <button
          v-for="id in intersectionIds"
          :key="id"
          type="button"
          class="chip"
          data-testid="ref-chip"
          @click="openIntersection(id)"
        >
          路口·{{ id }}
        </button>
      </div>
    </div>
  </BaseCard>
</template>

<style scoped>
.pts {
  margin: 0;
  padding-left: 1.15em;
}
.pts li {
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-dim);
  margin: 3px 0;
}
.hard {
  margin-top: 8px;
}
.hard__hd {
  font-size: 11px;
  color: var(--alarm);
  font-weight: 700;
}
.hard__tags {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.tag {
  padding: 2px 8px;
  font-size: 11.5px;
  color: var(--alarm);
  background: var(--alarm-dim);
  border: 1px solid rgba(255, 80, 80, 0.4);
}
.refs {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(146, 161, 181, 0.25);
}
.refs__hd {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-mute);
}
.refs__chips {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  padding: 3px 10px;
  border-radius: 12px;
  border: 1px solid var(--primary);
  background: var(--primary-dim);
  color: var(--primary);
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.16s ease;
}
.chip:hover {
  background: var(--primary);
  color: var(--bg, #04101c);
}
.contrast {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed rgba(146, 161, 181, 0.25);
}
.contrast-row {
  margin: 6px 0 0;
  font-size: 11px;
  line-height: 1.45;
  color: var(--text-dim);
}
.contrast-row strong {
  display: block;
  font-size: 11px;
  color: var(--text);
  margin-bottom: 2px;
}
.contrast-muted {
  margin: 0;
  color: var(--text-mute);
}
</style>

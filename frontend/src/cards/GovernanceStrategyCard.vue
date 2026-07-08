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

/** 治理建议要点：原则优先，回落到推荐项，去重后取前 3 条。 */
const points = computed<string[]>(() => {
  const src = [...(strategy.value?.principles ?? []), ...(strategy.value?.recommended ?? [])]
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of src) {
    const s = productCopy(raw)
    if (!s || seen.has(s)) continue
    seen.add(s)
    out.push(s)
    if (out.length >= 3) break
  }
  return out
})

const hardConstraints = computed<string[]>(() => strategy.value?.hard_constraints ?? [])

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
  () => points.value.length > 0 || hardConstraints.value.length > 0 || hasRefChips.value,
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
  <BaseCard v-if="hasAny" title="治理策略" :act="7" tone="protected">
    <ul v-if="points.length" class="pts">
      <li v-for="(p, i) in points" :key="i">{{ p }}</li>
    </ul>

    <div v-if="hardConstraints.length" class="hard">
      <span class="hard__hd">红线</span>
      <div class="hard__tags">
        <span v-for="(c, i) in hardConstraints" :key="i" class="tag">{{ productCopy(c) }}</span>
      </div>
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
  padding-left: 16px;
}
.pts li {
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-dim);
  margin: 4px 0;
}
.hard {
  margin-top: 10px;
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
  margin-top: 12px;
  padding-top: 10px;
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
</style>

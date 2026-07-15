<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { ratio, meters } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'
import { downstreamConclusion, downstreamCriteria } from '@/utils/downstream'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const dd = computed(() => store.diagnosis?.downstream_diagnosis ?? null)
const canAddGreen = computed(() => dd.value?.can_simple_add_green)

/** 承接结论：专业化推导（禁用口语表达）。 */
const conclusion = computed(() => productCopy(downstreamConclusion(dd.value)))

/** 结论语义色：可加绿=protected，受限=alarm，未定=evidence。 */
const tone = computed(() => {
  const c = dd.value?.judgment_criteria ?? {}
  const tight = Boolean(c.downstream_queue_high || c.downstream_near_saturation || c.add_green_spillback_risk)
  const capacity = dd.value?.primary_downstream?.capacity
  if (tight || capacity?.blocked) return 'no'
  if (capacity?.can_release) return 'yes'
  return 'unknown'
})

// —— 本路口（目标进口）侧指标：为「绿灯利用不足」结论提供可见依据 ——
const targetMetrics = computed(() => store.diagnosis?.metrics ?? null)
const targetSaturation = computed(() => targetMetrics.value?.saturation ?? null)
const targetGreenUtil = computed(() => targetMetrics.value?.green_utilization ?? null)
const targetLos = computed(() => targetMetrics.value?.los ?? null)

const primary = computed(() => dd.value?.primary_downstream ?? null)
const downMetrics = computed(() => primary.value?.metrics ?? null)
const downSaturation = computed(
  () => downMetrics.value?.saturation_rate ?? downMetrics.value?.saturation ?? null,
)
const capacity = computed(() => primary.value?.capacity ?? null)
const capacityText = computed(() => {
  const c = capacity.value
  if (!c) return null
  if (c.blocked) return '已阻塞'
  if (c.can_release) return downstreamIdle.value ? '空闲·有承接余量' : '有承接余量'
  return '承接受限'
})
const byTurn = computed(() => primary.value?.by_turn ?? [])

// 下游是否处于空闲/畅通：饱和度极低且服务水平良好，且无任何吃紧判据。
const downstreamIdle = computed(() => {
  const sat = downSaturation.value
  const los = downMetrics.value?.level_of_service
  const c = dd.value?.judgment_criteria ?? {}
  const tight = Boolean(
    c.downstream_queue_high || c.downstream_near_saturation || c.add_green_spillback_risk,
  )
  return !tight && (sat == null || sat < 0.6) && (!los || ['A', 'B', 'C'].includes(los))
})

const downQueueM = computed(() => {
  const m = downMetrics.value
  if (!m) return null
  const v = m.max_queue_m ?? m.avg_queue_m
  return typeof v === 'number' && Number.isFinite(v) ? v : null
})

// 剩余蓄车：仅在取到有效正值时展示（0/空多为下游空闲或数据缺口，展示 0m 会与「有承接余量」矛盾）。
const remainingStorage = computed(() => {
  const v = primary.value?.remaining_storage_m
  return typeof v === 'number' && v > 0 ? v : null
})

// 结论溯源：把「本路口 vs 下游」两侧证据拼成一句可核对的说明，消除「指标为零却说利用不足」的错觉。
const reconcile = computed(() => {
  const localLow = targetSaturation.value != null && targetSaturation.value >= 0.9 &&
    targetGreenUtil.value != null && targetGreenUtil.value < 0.85
  if (localLow && downstreamIdle.value) {
    return '下游空闲、具备承接空间；但本路口整体绿灯利用未饱和（关键流向已过饱、其余相位仍有余绿），瓶颈在本地相位配比与出口/渠化，简单加绿难以见效。'
  }
  if (downstreamIdle.value && canAddGreen.value === true) {
    return '下游空闲、具备承接空间，可小步增加关键流向有效绿并观察回溯。'
  }
  return ''
})

const criteria = computed(() => downstreamCriteria(dd.value))
const expertCheck = computed(() => productCopy(dd.value?.expert_question).replace(/^核验项：?/, ''))
</script>

<template>
  <BaseCard v-if="dd" title="下游承接能力判别" :act="5" tone="evidence">
    <p class="hint" data-testid="downstream-metric-hint">
      地图路口标签：转向占比为该流向车辆分担；饱和度越高越拥挤；绿灯利用率反映有效绿是否被占满；排队比为排队长度相对进口道蓄车空间。
    </p>
    <div class="answer" :class="tone">
      <span class="answer__k">承接判断</span>
      <span class="answer__v">{{ conclusion }}</span>
    </div>

    <!-- 本路口（目标进口）指标：为结论提供可见依据 -->
    <div v-if="targetMetrics" class="down down--target" data-testid="target-metrics">
      <div class="down__hd">本路口 · 目标进口</div>
      <ul class="down__grid">
        <li><span>饱和度</span><b :class="{ warn: (targetSaturation ?? 0) >= 0.9 }">{{ ratio(targetSaturation) }}</b></li>
        <li><span>绿灯利用率</span><b :class="{ warn: (targetGreenUtil ?? 1) < 0.85 }">{{ ratio(targetGreenUtil) }}</b></li>
        <li><span>服务水平</span><b :class="{ warn: targetLos === 'F' }">{{ targetLos ?? '—' }}</b></li>
      </ul>
    </div>

    <!-- 下游路口分析指标 -->
    <div v-if="primary?.inter_name" class="down" data-testid="downstream-metrics">
      <div class="down__hd">下游路口 · {{ productCopy(primary.inter_name) }}</div>
      <ul class="down__grid">
        <li><span>饱和度</span><b :class="{ warn: (downSaturation ?? 0) >= 0.8 }">{{ ratio(downSaturation) }}</b></li>
        <li><span>服务水平</span><b :class="{ warn: downMetrics?.level_of_service === 'F' }">{{ downMetrics?.level_of_service ?? '—' }}</b></li>
        <li v-if="downQueueM != null"><span>排队长度</span><b>{{ meters(downQueueM) }}</b></li>
        <li v-if="downMetrics?.queue_storage_ratio_max != null"><span>排队比</span><b>{{ ratio(downMetrics.queue_storage_ratio_max) }}</b></li>
        <li v-if="remainingStorage != null"><span>剩余蓄车</span><b>{{ meters(remainingStorage) }}</b></li>
        <li v-if="capacityText"><span>承接能力</span><b :class="{ ok: capacity?.can_release && !capacity?.blocked, warn: capacity?.blocked }">{{ capacityText }}</b></li>
      </ul>
      <div v-if="byTurn.length" class="down__turns">
        <span v-for="(tt, i) in byTurn" :key="i" class="turn">
          {{ productCopy(tt.label ?? '转向') }} 饱和 {{ ratio(tt.turn_saturation) }}
        </span>
      </div>
    </div>

    <!-- 结论溯源：两侧证据如何得出结论 -->
    <p v-if="reconcile" class="reconcile" data-testid="downstream-reconcile">{{ reconcile }}</p>

    <!-- 评判依据：展示结论如何得出 -->
    <div v-if="criteria.length" class="crit">
      <div class="crit__hd">评判依据</div>
      <ul>
        <li v-for="c in criteria" :key="c.key" :class="{ hit: c.hit }">
          <span class="crit__mark">{{ c.hit ? '✓' : '·' }}</span>{{ c.label }}
        </li>
      </ul>
    </div>

    <p v-if="expertCheck" class="q">核验项：{{ expertCheck }}</p>
  </BaseCard>
</template>

<style scoped>
.hint {
  margin: 0 0 10px;
  padding: 8px 10px;
  border-left: 2px solid var(--evidence);
  background: rgba(255, 255, 255, 0.03);
  font-size: 11.5px;
  line-height: 1.55;
  color: var(--text-dim);
}
.answer {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 0;
  margin-bottom: 10px;
  border: 1px solid var(--evidence);
  background: var(--evidence-dim);
}
.answer.no {
  border-color: var(--alarm);
  background: var(--alarm-dim);
}
.answer.yes {
  border-color: var(--protected);
  background: var(--protected-dim);
}
.answer__k {
  font-size: 11px;
  color: var(--text-mute);
}
.answer__v {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  line-height: 1.4;
}
.down {
  margin-bottom: 10px;
  padding: 10px 11px;
  border: 1px solid rgba(146, 161, 181, 0.35);
  background: rgba(255, 255, 255, 0.025);
}
.down--target {
  border-color: rgba(233, 176, 92, 0.45);
  background: rgba(233, 176, 92, 0.06);
}
.reconcile {
  margin: 0 0 10px;
  padding: 9px 11px;
  border-left: 2px solid var(--evidence);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-dim);
}
.down__hd {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}
.down__grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px 12px;
}
.down__grid li {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
  padding-bottom: 3px;
}
.down__grid span {
  font-size: 11.5px;
  color: var(--text-dim);
}
.down__grid b {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.down__grid b.warn {
  color: var(--alarm);
}
.down__grid b.ok {
  color: var(--protected);
}
.down__turns {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.turn {
  font-size: 11px;
  padding: 2px 8px;
  border: 1px solid rgba(146, 161, 181, 0.4);
  color: var(--text-dim);
}
.crit {
  margin-bottom: 10px;
}
.crit__hd {
  font-size: 11px;
  color: var(--text-mute);
  margin-bottom: 6px;
}
.crit ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.crit li {
  font-size: 12px;
  color: var(--text-mute);
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.crit li.hit {
  color: var(--text);
}
.crit__mark {
  color: var(--text-mute);
  font-weight: 700;
}
.crit li.hit .crit__mark {
  color: var(--evidence);
}
.q {
  margin: 8px 0 0;
  padding: 8px 10px;
  border: 1px solid rgba(146, 161, 181, 0.4);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12.5px;
  color: var(--text);
  border-radius: 0;
}
</style>

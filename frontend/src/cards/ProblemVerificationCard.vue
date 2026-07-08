<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { num, ratioTone } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'
import { t } from '@/labels/enums'
import BaseCard from './BaseCard.vue'

const store = usePresentationStore()
const diag = computed(() => store.diagnosis ?? null)
const reg = computed(() => diag.value?.problem_regularity ?? null)
const timing = computed(() => diag.value?.timing_profile ?? null)
const ov = computed(() => diag.value?.overflow_verification ?? null)
const m = computed(() => diag.value?.metrics ?? null)

/** 至少一类可展示数据存在才渲染卡片（缺失即不显示，避免空卡）。 */
const hasAny = computed(
  () => !!reg.value || !!timing.value || !!ov.value || !!m.value,
)

const satTone = computed(() => ratioTone(m.value?.saturation))

function losLabel(los: string | null | undefined): string {
  if (!los) return '—'
  return los === 'F' ? 'F 阻塞' : los
}

const cardTone = computed(() => {
  const r = ov.value?.risk_level
  if (r === 'high' || r === 'critical') return 'alarm'
  if (satTone.value === 'alarm') return 'alarm'
  return 'evidence'
})
</script>

<template>
  <BaseCard v-if="hasAny" title="问题验证" :act="3" :tone="cardTone">
    <!-- 常发性 / 周期性（派生，非实测，显式标注） -->
    <div v-if="reg" class="block">
      <div class="row">
        <span class="row__k">常发性</span>
        <span class="row__v">{{ productCopy(reg.recurring) || '—' }}</span>
      </div>
      <div class="row">
        <span class="row__k">周期性</span>
        <span class="row__v">{{ productCopy(reg.periodic) || '—' }}</span>
      </div>
      <p class="foot">
        <span class="foot__tag">派生</span>{{ reg.basis }}
      </p>
    </div>

    <!-- 运行状态：饱和度 / 服务水平 -->
    <div v-if="m && (m.saturation != null || m.los)" class="block">
      <span class="block__hd">运行状态</span>
      <div v-if="m.saturation != null" class="row">
        <span class="row__k">饱和度</span>
        <span class="row__v us-mono" :class="`tone-${satTone}`">{{ num(m.saturation, 2) }}</span>
      </div>
      <div v-if="m.los" class="row">
        <span class="row__k">服务水平</span>
        <span class="row__v us-mono" :class="{ 'tone-alarm': m.los === 'F' }">{{ losLabel(m.los) }}</span>
      </div>
    </div>

    <!-- 配时画像 -->
    <div
      v-if="timing && (timing.cycle_s != null || timing.time_plan_count != null || timing.plan_name)"
      class="block"
    >
      <span class="block__hd">配时画像</span>
      <div v-if="timing.cycle_s != null" class="row">
        <span class="row__k">周期</span>
        <span class="row__v us-mono">{{ num(timing.cycle_s, 0) }} s</span>
      </div>
      <div v-if="timing.time_plan_count != null" class="row">
        <span class="row__k">时段方案数</span>
        <span class="row__v us-mono">{{ num(timing.time_plan_count, 0) }}</span>
      </div>
      <div v-if="timing.plan_name" class="row">
        <span class="row__k">方案名</span>
        <span class="row__v">{{ timing.plan_name }}</span>
      </div>
    </div>

    <!-- 溢出核验 -->
    <div v-if="ov && (ov.message || ov.risk_level)" class="verdict" :class="`tone-${cardTone}`">
      <span v-if="ov.risk_level" class="verdict__badge">溢出核验 · {{ t('risk_level', ov.risk_level) }}</span>
      <p v-if="ov.message">{{ productCopy(ov.message) }}</p>
    </div>
  </BaseCard>
</template>

<style scoped>
.block {
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.block:last-child {
  border-bottom: none;
}
.block__hd {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-mute);
  margin-bottom: 4px;
}
.row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 3px 0;
}
.row__k {
  flex: 0 0 auto;
  min-width: 64px;
  font-size: 12px;
  color: var(--text-dim);
}
.row__v {
  flex: 1;
  font-size: 12.5px;
  color: var(--text);
  line-height: 1.45;
}
.row__v.tone-alarm {
  color: var(--alarm);
}
.row__v.tone-evidence {
  color: var(--evidence);
}
.foot {
  margin: 6px 0 0;
  font-size: 10.5px;
  line-height: 1.45;
  color: var(--text-mute);
}
.foot__tag {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--text-mute);
  color: var(--text-mute);
  font-size: 10px;
}
.verdict {
  margin-top: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--evidence);
  background: var(--evidence-dim);
}
.verdict.tone-alarm {
  border-color: var(--alarm);
  background: var(--alarm-dim);
}
.verdict__badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
}
.verdict p {
  margin: 5px 0 0;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text);
}
</style>

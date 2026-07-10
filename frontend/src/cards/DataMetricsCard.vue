<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { ratio, meters, num, ratioTone } from '@/utils/format'
import { productCopy } from '@/utils/productCopy'
import { t } from '@/labels/enums'
import BaseCard from './BaseCard.vue'
import type { MovementMetric } from '@/api/types'

const props = withDefaults(
  defineProps<{
    /** detail：左下完整面板；summary：闭环内仅摘要。 */
    variant?: 'detail' | 'summary'
  }>(),
  { variant: 'detail' },
)

const store = usePresentationStore()
const m = computed(() => store.diagnosis?.metrics ?? null)
const tk = computed(() => store.ticket ?? null)
const saturation = computed(() => m.value?.saturation ?? m.value?.saturation_rate ?? null)
const ov = computed(() => store.diagnosis?.overflow_verification ?? null)

const qrTone = computed(() => ratioTone(m.value?.queue_ratio))
const guTone = computed(() => {
  const g = m.value?.green_utilization
  return typeof g === 'number' && g < 0.5 ? 'evidence' : 'primary'
})
const verdictTone = computed(() => {
  const r = ov.value?.risk_level
  return r === 'high' || r === 'critical' ? 'alarm' : r === 'medium' ? 'evidence' : 'primary'
})

const byApproach = computed(() => m.value?.by_approach ?? [])
const byMovement = computed(() => m.value?.by_movement ?? [])
const hasRich = computed(() => byApproach.value.length > 0 || byMovement.value.length > 0)
const isSummary = computed(() => props.variant === 'summary')

const imbalance = computed(() => {
  const v = m.value?.imbalance_index
  return typeof v === 'number' ? v : null
})
const imbalanceHigh = computed(() => (imbalance.value ?? 0) >= 0.3)

/** 服务水平：F 显式标注为「F-阻塞」，其余原样。 */
function losLabel(los: string | null | undefined): string {
  if (!los) return '—'
  return los === 'F' ? 'F-阻塞' : los
}

/** 饱和度阈值 → 语义色（复用 ratioTone，>=1.0 告警）。 */
function satTone(x: number | null | undefined) {
  return ratioTone(x)
}

/** 转向拥挤等级 → 语义色。 */
function movementTone(level: string | null | undefined): 'alarm' | 'evidence' | 'primary' {
  if (level === '过饱和') return 'alarm'
  if (level === '偏高') return 'evidence'
  return 'primary'
}

/** 转向绿灯利用（可 >1，不用百分比避免显示 177%）。 */
function guValue(mv: MovementMetric): string {
  return num(mv.green_utilization, 2)
}

/** 关注/保护方向：从工单方向轴诚实派生；无法判定则不展示。 */
const focusTags = computed(() => {
  const dir = tk.value?.direction?.toLowerCase() ?? ''
  if (!dir) return null
  if (/east|west|东|西/.test(dir)) return { focus: '东西向', protect: '南北向' }
  if (/north|south|南|北/.test(dir)) return { focus: '南北向', protect: '东西向' }
  return null
})

const overallLos = computed(() => m.value?.los ?? null)

/**
 * 维度说明：溢出判定看「进口道空间」（排队比），饱和度/服务水平看「需求」。
 * 当空间未溢出但需求过饱和时，两者可同时成立，避免被误读为矛盾。
 */
const dimensionNote = computed(() => {
  const risk = ov.value?.risk_level
  const spaceOk = risk === 'low' || risk === 'warning'
  const sat = saturation.value
  const demandHigh = (typeof sat === 'number' && sat >= 1) || overallLos.value === 'F'
  if (spaceOk && demandHigh) {
    return '溢出判定看进口道空间（排队比），饱和度/服务水平看需求；空间未溢出与需求过饱和可同时成立，并不矛盾。'
  }
  return null
})
</script>

<template>
  <BaseCard
    v-if="m"
    :title="isSummary ? '运行数据摘要' : ''"
    :act="3"
    :tone="qrTone === 'alarm' ? 'alarm' : 'primary'"
  >
    <!-- 头部：路口名 / inter_id / 进口·车道 / 关注·保护方向 -->
    <div v-if="hasRich || isSummary" class="head">
      <div class="head__title">
        <span class="head__name">{{ productCopy(tk?.intersection_name) || '路口' }}</span>
        <span v-if="tk?.inter_id" class="head__id us-mono">{{ tk.inter_id }}</span>
      </div>
      <div v-if="m.approach_count || m.lane_count" class="head__sub">
        进口车道
        <template v-if="m.approach_count"> · {{ m.approach_count }} 进口</template>
        <template v-if="m.lane_count"> · {{ m.lane_count }} 车道</template>
      </div>
      <div v-if="focusTags" class="tags">
        <span class="tag tag--focus">关注 {{ focusTags.focus }}</span>
        <span class="tag tag--protect">保护 {{ focusTags.protect }}</span>
      </div>
    </div>

    <!-- 摘要模式：关键指标一行 + 指向左下详情 -->
    <div v-if="isSummary" class="summary" data-testid="metrics-summary">
      <div class="summary__row">
        <span class="summary__k">排队比</span>
        <span class="summary__v us-mono" :class="`tone-${qrTone}`">{{ ratio(m.queue_ratio) }}</span>
      </div>
      <div class="summary__row">
        <span class="summary__k">饱和度</span>
        <span class="summary__v us-mono" :class="`tone-${satTone(saturation)}`">{{ ratio(saturation) }}</span>
      </div>
      <div v-if="overallLos" class="summary__row">
        <span class="summary__k">服务水平</span>
        <span class="summary__v us-mono" :class="{ 'tone-alarm': overallLos === 'F' }">{{ losLabel(overallLos) }}</span>
      </div>
      <div v-if="imbalance != null" class="summary__row">
        <span class="summary__k">方向失衡</span>
        <span class="summary__v us-mono" :class="{ 'tone-evidence': imbalanceHigh }">{{ num(imbalance, 2) }}</span>
      </div>
      <p class="summary__hint">详细逐进口/逐转向数据见左下「运行数据」面板</p>
    </div>

    <!-- 详细运行数据列表（富指标） -->
    <div v-else-if="hasRich" class="rows" data-testid="metrics-detail">
      <div v-for="ap in byApproach" :key="ap.approach" class="approach">
        <div class="approach__hd">{{ ap.approach }}</div>
        <ul class="approach__list">
          <li>
            <span class="approach__k">饱和度</span>
            <span class="approach__v us-mono" :class="`tone-${satTone(ap.saturation)}`">{{ num(ap.saturation, 2) }}</span>
          </li>
          <li v-if="ap.delay_index != null">
            <span class="approach__k">延误指数</span>
            <span class="approach__v us-mono">{{ num(ap.delay_index, 2) }}</span>
          </li>
          <li v-if="ap.los">
            <span class="approach__k">服务水平</span>
            <span class="approach__v us-mono" :class="{ 'tone-alarm': ap.los === 'F' }">{{ losLabel(ap.los) }}</span>
          </li>
        </ul>
      </div>

      <div v-if="overallLos" class="row">
        <span class="row__k">服务水平</span>
        <span class="row__v us-mono" :class="{ 'tone-alarm': overallLos === 'F' }">{{ losLabel(overallLos) }}</span>
      </div>

      <template v-for="mv in byMovement" :key="mv.movement">
        <div class="row">
          <span class="row__k">{{ mv.movement }}饱和度</span>
          <span class="row__v us-mono" :class="`tone-${movementTone(mv.level)}`">{{ num(mv.saturation, 2) }}</span>
          <span v-if="mv.level" class="lvl" :class="`lvl-${movementTone(mv.level)}`">{{ mv.level }}</span>
        </div>
        <div v-if="mv.green_utilization != null" class="row row--sub">
          <span class="row__k">{{ mv.movement }}绿灯利用</span>
          <span class="row__v us-mono">{{ guValue(mv) }}</span>
        </div>
      </template>
    </div>

    <!-- 降级兜底：hero 排队比 + 6 格网格 -->
    <template v-if="!hasRich && !isSummary">
      <div class="hero" :class="`tone-${qrTone}`">
        <span class="hero__num us-mono">{{ ratio(m.queue_ratio) }}</span>
        <span class="hero__lbl">排队比</span>
      </div>

      <div class="grid">
        <div class="cell"><span class="v us-mono">{{ meters(m.queue_length_m) }}</span><span class="k">排队长度</span></div>
        <div class="cell"><span class="v us-mono">{{ meters(m.storage_length_m) }}</span><span class="k">蓄车长度</span></div>
        <div class="cell"><span class="v us-mono">{{ ratio(saturation) }}</span><span class="k">饱和度</span></div>
        <div class="cell" :class="`tone-${guTone}`">
          <span class="v us-mono">{{ ratio(m.green_utilization) }}</span><span class="k">绿灯利用率</span>
        </div>
        <div class="cell"><span class="v us-mono">{{ num(m.stop_count, 2) }}</span><span class="k">停车次数</span></div>
        <div class="cell"><span class="v us-mono">{{ num(m.avg_delay_s, 1) }}s</span><span class="k">平均延误</span></div>
      </div>
    </template>

    <div v-if="ov" class="verdict" :class="`tone-${verdictTone}`" data-testid="overflow-verdict">
      <span class="verdict__badge">溢出判定（进口道空间）· {{ t('risk_level', ov.risk_level) }}</span>
      <p>{{ ov.message ?? '—' }}</p>
      <p v-if="dimensionNote" class="verdict__note">{{ dimensionNote }}</p>
    </div>

    <p class="src">数据来源：{{ t('data_source', store.diagnosis?.data_source) }}</p>
  </BaseCard>
</template>

<style scoped>
.head {
  margin-bottom: 12px;
}
.head__title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}
.head__name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
}
.head__id {
  font-size: 11px;
  color: var(--text-mute);
}
.head__sub {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-mute);
}
.tags {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--primary);
  color: var(--primary);
}
.tag--protect {
  border-color: var(--text-mute);
  color: var(--text-mute);
}
.rows {
  display: flex;
  flex-direction: column;
}
.approach {
  padding: 6px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.approach__hd {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}
.approach__list {
  list-style: disc;
  margin: 0;
  padding-left: 18px;
}
.approach__list li {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 2px 0;
}
.approach__k {
  flex: 1;
  font-size: 12px;
  color: var(--text-dim);
}
.approach__v {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.approach__v.tone-alarm {
  color: var(--alarm);
}
.approach__v.tone-evidence {
  color: var(--evidence);
}
.row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}
.row--sub {
  padding-top: 2px;
  border-bottom: none;
}
.row__k {
  flex: 1;
  font-size: 12px;
  color: var(--text-dim);
}
.row--sub .row__k {
  color: var(--text-mute);
}
.row__v {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.row__v.tone-alarm {
  color: var(--alarm);
}
.row__v.tone-evidence {
  color: var(--evidence);
}
.row__meta {
  flex-basis: 100%;
  font-size: 11px;
  color: var(--text-mute);
}
.lvl {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--text-mute);
  color: var(--text-mute);
}
.lvl-alarm {
  border-color: var(--alarm);
  color: var(--alarm);
}
.lvl-evidence {
  border-color: var(--evidence);
  color: var(--evidence);
}
.hero {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}
.hero__num {
  font-size: 40px;
  font-weight: 700;
  line-height: 1;
  color: var(--primary);
}
.tone-alarm .hero__num,
.hero.tone-alarm .hero__num {
  color: var(--alarm);
}
.hero.tone-evidence .hero__num {
  color: var(--evidence);
}
.hero__lbl {
  font-size: 13px;
  color: var(--text-mute);
}
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.03);
}
.cell .v {
  font-size: 15px;
  color: var(--text);
}
.cell.tone-evidence .v {
  color: var(--evidence);
}
.cell .k {
  font-size: 11px;
  color: var(--text-mute);
}
.verdict {
  margin-top: 12px;
  padding: 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--primary);
  background: var(--primary-dim);
}
.verdict.tone-alarm {
  border-color: var(--alarm);
  background: var(--alarm-dim);
}
.verdict.tone-evidence {
  border-color: var(--evidence);
  background: var(--evidence-dim);
}
.verdict__badge {
  font-size: 11px;
  color: var(--text);
  font-weight: 600;
}
.verdict p {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
}
.verdict__note {
  font-size: 11.5px !important;
  color: var(--text-mute) !important;
  border-top: 1px dashed rgba(146, 161, 181, 0.3);
  padding-top: 6px;
}
.src {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--text-mute);
}
.summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}
.summary__row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.summary__k {
  flex: 0 0 64px;
  font-size: 12px;
  color: var(--text-dim);
}
.summary__v {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.summary__v.tone-alarm {
  color: var(--alarm);
}
.summary__v.tone-evidence {
  color: var(--evidence);
}
.summary__hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--text-mute);
  line-height: 1.45;
}
</style>

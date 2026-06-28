<script setup lang="ts">
import { ref, watch } from 'vue'
import type { PipelinePhase } from '../../types/presentation'

const props = defineProps<{
  phase?: PipelinePhase
  showQueue?: boolean
  showDirectionRoles?: boolean
  /** 新一轮分析时递增，用于重置粘性图例块 */
  runKey?: number
}>()

/** 图例块只增不减，避免阶段切换时闪烁 */
const queueLegendRevealed = ref(false)
const imbalanceLegendRevealed = ref(false)

watch(
  () => props.showQueue,
  (v) => {
    if (v) queueLegendRevealed.value = true
  },
  { immediate: true },
)

watch(
  () => props.phase,
  (phase) => {
    if (phase === 'imbalance') {
      imbalanceLegendRevealed.value = true
    }
  },
  { immediate: true },
)

watch(
  () => props.runKey,
  () => {
    queueLegendRevealed.value = false
    imbalanceLegendRevealed.value = false
  },
)
</script>

<template>
  <aside class="chan-legend" aria-label="渠化图图例">
    <h4>图例说明</h4>

    <div v-if="showDirectionRoles" class="legend-block direction-roles">
      <span class="icon">🧭</span>
      <div>
        <strong>方向角色</strong>
        <ul class="swatches">
          <li><i class="sw focus" />关注方向</li>
          <li><i class="sw protect" />保护方向</li>
        </ul>
      </div>
    </div>

    <div v-if="queueLegendRevealed" class="legend-block">
      <span class="icon">🚗</span>
      <div>
        <strong>排队车辆</strong>
        <p>停车线后方色块，每辆约 6–8 米。颜色越深表示饱和度越高。</p>
        <ul class="swatches">
          <li><i class="sw high" />过饱和 ≥0.85</li>
          <li><i class="sw med" />偏高 0.70–0.85</li>
          <li><i class="sw low" />缓行 0.50–0.70</li>
          <li><i class="sw ok" />畅通 &lt;0.50</li>
        </ul>
      </div>
    </div>

    <div class="legend-block">
      <span class="icon">📊</span>
      <div>
        <strong>饱和度</strong>
        <p>进口流量 ÷ 通行能力。≥0.85 为过饱和，路口易排队溢出。</p>
      </div>
    </div>

    <div v-if="imbalanceLegendRevealed" class="legend-block">
      <span class="icon">⚖️</span>
      <div>
        <strong>失衡</strong>
        <p>各进口饱和度差异大时，高饱和进口道会叠加橙色光带提示。</p>
      </div>
    </div>

    <div class="legend-block">
      <span class="icon">🛑</span>
      <div>
        <strong>停车线 / 斑马线</strong>
        <p>红色为停车线，白色条纹为行人过街，箭头为车道转向。</p>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.chan-legend {
  /* 路口信息卡占用左侧，图例移至右下角 */
  position: absolute;
  right: 12px;
  bottom: 12px;
  z-index: 4;
  max-width: 280px;
  padding: 10px 12px;
  border-radius: 6px;
  background: rgba(8, 12, 20, 0.88);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 10px;
  color: rgba(220, 230, 240, 0.85);
  pointer-events: none;
}

.chan-legend h4 {
  margin: 0 0 8px;
  font-size: 9px;
  letter-spacing: 1px;
  color: rgba(180, 195, 210, 0.7);
  text-transform: uppercase;
}

.legend-block {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.legend-block:last-child {
  margin-bottom: 0;
}

.icon {
  font-size: 14px;
  line-height: 1.2;
  flex-shrink: 0;
}

.legend-block strong {
  display: block;
  font-size: 11px;
  color: #f0f4f8;
  margin-bottom: 2px;
}

.legend-block p {
  margin: 0;
  line-height: 1.45;
  color: rgba(200, 215, 230, 0.75);
}

.swatches {
  list-style: none;
  margin: 6px 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 2px 8px;
}

.swatches li {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 9px;
}

.sw {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  display: inline-block;
}

.sw.high {
  background: #dd2233;
}
.sw.med {
  background: #dd6600;
}
.sw.low {
  background: #ccaa00;
}
.sw.ok {
  background: #338844;
}
.sw.focus {
  background: #ff6b4a;
}
.sw.protect {
  background: #6dffb5;
}
</style>

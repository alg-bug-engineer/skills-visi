<script setup lang="ts">
import type { PhaseStageTiming } from '@/api/types'
import StageMovementCanvas from '@/viz/StageMovementCanvas.vue'
import { flowKeysFromStage, formatFlowKeysText, pctText } from '@/viz/planVisualization'

defineProps<{ stages: PhaseStageTiming[] }>()

function sec(value?: number | null) {
  return typeof value === 'number' && Number.isFinite(value) ? `${value}s` : '—'
}

function delta(value?: number | null) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value === 0 ? '±0s' : `${value > 0 ? '+' : ''}${value}s`
}

function stageTotal(stage: PhaseStageTiming): number | null | undefined {
  return stage.optimized_timing?.stage_total_s ?? stage.green_time_s
}

function flowLabel(stage: PhaseStageTiming): string {
  return formatFlowKeysText(flowKeysFromStage(stage))
}

function hasFlow(stage: PhaseStageTiming): boolean {
  return flowKeysFromStage(stage).length > 0
}
</script>

<template>
  <section class="stages">
    <article v-for="(stage, i) in stages" :key="stage.phase_stage_id || i" class="card">
      <h4 :title="stage.phase_stage_name">阶段 {{ i + 1 }}</h4>
      <p class="stage-name">{{ stage.phase_stage_name || '未命名阶段' }}</p>
      <div class="cmp">
        <span class="old">{{ sec(stage.current_timing?.stage_total_s) }}</span>
        <span>→</span>
        <strong>{{ sec(stageTotal(stage)) }}</strong>
        <b :class="{ up: (stage.stage_delta_s ?? 0) > 0, down: (stage.stage_delta_s ?? 0) < 0 }">{{ delta(stage.stage_delta_s) }}</b>
      </div>
      <StageMovementCanvas :stage="stage" />
      <div v-if="hasFlow(stage)" class="flow-label">{{ flowLabel(stage) }}</div>
      <div v-else class="missing">后端未返回释放方向证据</div>
      <div class="meta">
        <span>绿灯 {{ sec(stage.current_timing?.green_time_s) }} → {{ sec(stage.optimized_timing?.green_time_s ?? stage.green_time_s) }}</span>
        <span>Δ绿灯 {{ delta(stage.green_delta_s) }}</span>
        <span>最小/最大绿 {{ sec(stage.min_green_time_s) }} / {{ sec(stage.max_green_time_s) }}</span>
        <span>饱和度 {{ pctText(stage.phase_saturation) }}</span>
      </div>
    </article>
  </section>
</template>

<style scoped>
.stages {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.card {
  flex: 0 0 190px;
  padding: 10px;
  border: 1px solid rgba(138, 160, 180, 0.28);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
}
h4 {
  margin: 0;
  text-align: center;
  color: var(--text);
  font-size: 13px;
}
.stage-name {
  min-height: 32px;
  margin: 3px 0 8px;
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.35;
  text-align: center;
}
.cmp {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 5px;
  margin-bottom: 8px;
  color: var(--text-dim);
}
.old {
  text-decoration: line-through;
}
strong {
  color: var(--protected);
  font-size: 22px;
}
b {
  color: var(--text-mute);
  font-size: 12px;
}
b.up {
  color: var(--evidence);
}
b.down {
  color: var(--alarm);
}
.meta,
.missing,
.flow-label {
  display: grid;
  gap: 3px;
  margin-top: 7px;
  color: var(--text-mute);
  font-size: 11px;
}
.flow-label {
  min-height: 30px;
  align-items: center;
  color: var(--text-dim);
  line-height: 1.35;
  text-align: center;
}
</style>

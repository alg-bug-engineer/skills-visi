<script setup lang="ts">
import type { PhaseStageTiming } from '@/api/types'
import StageMovementCanvas from '@/viz/StageMovementCanvas.vue'
import { flowKeysFromStage, formatFlowKeysText } from '@/viz/planVisualization'
import { ratio } from '@/utils/format'

defineProps<{
  stages: PhaseStageTiming[]
  /** 覆盖默认提示，例如门控后拟实施借绿对照 */
  hint?: string
}>()

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

function currentGreen(stage: PhaseStageTiming): number | null | undefined {
  return stage.current_timing?.green_time_s
}

function optimizedGreen(stage: PhaseStageTiming): number | null | undefined {
  return stage.optimized_timing?.green_time_s ?? stage.green_time_s
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
    <header class="stages-head">
      <h4>阶段形式</h4>
      <span class="hint">{{ hint || '现状 → 优化（括号内为差值）' }}</span>
    </header>
    <div class="cards">
      <article v-for="(stage, i) in stages" :key="stage.phase_stage_id || i" class="card">
        <div class="card-head">
          <strong>阶段 {{ i + 1 }}</strong>
          <span class="stage-total">
            {{ sec(stage.current_timing?.stage_total_s) }}
            →
            {{ sec(stageTotal(stage)) }}
            <em :class="{ up: (stage.stage_delta_s ?? 0) > 0, down: (stage.stage_delta_s ?? 0) < 0 }">
              ({{ delta(stage.stage_delta_s) }})
            </em>
          </span>
        </div>
        <p class="stage-name">{{ stage.phase_stage_name || '未命名阶段' }}</p>
        <div class="green-cmp">
          <span class="label">绿灯</span>
          <span class="old">{{ sec(currentGreen(stage)) }}</span>
          <span class="arrow">→</span>
          <span class="new">{{ sec(optimizedGreen(stage)) }}</span>
          <span class="delta" :class="{ up: (stage.green_delta_s ?? 0) > 0, down: (stage.green_delta_s ?? 0) < 0 }">
            {{ delta(stage.green_delta_s) }}
          </span>
        </div>
        <StageMovementCanvas :stage="stage" />
        <div v-if="hasFlow(stage)" class="flow-label">{{ flowLabel(stage) }}</div>
        <div v-else class="missing">后端未返回释放方向证据</div>
        <div class="meta">
          <span>最小/最大绿 {{ sec(stage.min_green_time_s) }} / {{ sec(stage.max_green_time_s) }}</span>
          <span>阶段饱和度 {{ ratio(stage.phase_saturation) }}</span>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.stages {
  display: grid;
  gap: 8px;
}
.stages-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.stages-head h4 {
  margin: 0;
  font-size: 13px;
  color: var(--text);
}
.hint {
  color: var(--text-mute);
  font-size: 11px;
}
.cards {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}
.card {
  flex: 0 0 200px;
  padding: 10px;
  border: 1px solid rgba(138, 160, 180, 0.28);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.025);
}
.card-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 4px;
}
.card-head strong {
  color: var(--text);
  font-size: 13px;
}
.stage-total {
  color: var(--text-dim);
  font-size: 11px;
}
.stage-total em {
  font-style: normal;
  font-weight: 700;
}
.stage-total em.up {
  color: var(--evidence);
}
.stage-total em.down {
  color: var(--alarm);
}
.stage-name {
  min-height: 28px;
  margin: 0 0 8px;
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.35;
  text-align: center;
}
.green-cmp {
  display: flex;
  align-items: baseline;
  justify-content: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
  padding: 6px 4px;
  border-radius: 6px;
  background: rgba(0, 229, 255, 0.06);
}
.green-cmp .label {
  width: 100%;
  text-align: center;
  color: var(--text-mute);
  font-size: 10px;
}
.old {
  text-decoration: line-through;
  color: var(--text-dim);
  font-size: 13px;
}
.arrow {
  color: var(--text-mute);
  font-size: 12px;
}
.new {
  color: var(--protected);
  font-size: 22px;
  font-weight: 700;
}
.delta {
  color: var(--text-mute);
  font-size: 12px;
  font-weight: 700;
}
.delta.up {
  color: var(--evidence);
}
.delta.down {
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
  min-height: 28px;
  align-items: center;
  color: var(--text-dim);
  line-height: 1.35;
  text-align: center;
}
</style>

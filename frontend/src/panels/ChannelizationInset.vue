<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { directionMovement } from '@/labels/enums'
import { ratio, meters, laneTone } from '@/utils/format'

const store = usePresentationStore()
const tk = computed(() => store.ticket)
const m = computed(() => store.diagnosis?.metrics ?? null)
// 渠化小窗：以目标转向为主车道，展示排队占用（真实排队比），其余车道无逐车道数据 → 标注暂缺。
const fill = computed(() => {
  const r = m.value?.queue_ratio
  return typeof r === 'number' ? Math.min(100, Math.max(4, r * 100)) : 0
})
const tone = computed(() => laneTone(m.value?.queue_ratio))
</script>

<template>
  <div class="inset us-panel" data-testid="channelization-inset">
    <div class="inset__hd">渠化 · 车道级</div>
    <div class="approach">
      <div class="lane" :class="`tone-${tone}`">
        <div class="lane__fill" :style="{ height: fill + '%' }" />
        <span class="lane__arrow">↑</span>
      </div>
      <div class="lane muted"><span class="lane__na">暂缺</span></div>
      <div class="lane muted"><span class="lane__na">暂缺</span></div>
    </div>
    <div class="inset__ft">
      <span>{{ directionMovement(tk?.direction, tk?.movement) }}</span>
      <span class="us-mono">排队比 {{ ratio(m?.queue_ratio) }} · {{ meters(m?.queue_length_m) }}</span>
    </div>
  </div>
</template>

<style scoped>
.inset {
  width: 168px;
  padding: 10px;
}
.inset__hd {
  font-size: 11px;
  color: var(--text-mute);
  margin-bottom: 8px;
  letter-spacing: 1px;
}
.approach {
  display: flex;
  gap: 6px;
  height: 72px;
}
.lane {
  position: relative;
  flex: 1;
  border: 1px solid var(--panel-border);
  border-radius: 4px;
  overflow: hidden;
  display: grid;
  place-items: end center;
  background: rgba(255, 255, 255, 0.03);
}
.lane__fill {
  position: absolute;
  left: 0;
  bottom: 0;
  width: 100%;
  background: var(--primary);
  opacity: 0.55;
  transition: height 0.6s;
}
.tone-alarm .lane__fill {
  background: var(--alarm);
}
.tone-evidence .lane__fill {
  background: var(--evidence);
}
.tone-protected .lane__fill {
  background: var(--protected);
}
.lane__arrow {
  position: relative;
  z-index: 1;
  color: var(--text);
  font-size: 16px;
  padding-bottom: 4px;
}
.lane.muted {
  opacity: 0.4;
}
.lane__na {
  font-size: 10px;
  color: var(--text-mute);
  align-self: center;
}
.inset__ft {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 8px;
  font-size: 11px;
  color: var(--text-dim);
}
</style>

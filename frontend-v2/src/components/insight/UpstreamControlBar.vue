<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(
  defineProps<{
    idx: number
    total: number
    playing: boolean
    speed?: number
    showHop2?: boolean
  }>(),
  { speed: 1, showHop2: true },
)

const emit = defineEmits<{
  play: []
  pause: []
  step: [delta: number]
  seek: [n: number]
  'set-speed': [speed: number]
  'toggle-hop2': [show: boolean]
}>()

const last = computed(() => Math.max(0, props.total - 1))
const progressLabel = computed(() => `${Math.min(props.idx + 1, props.total)}/${props.total}`)

function onScrub(event: Event) {
  const value = Number((event.target as HTMLInputElement).value)
  emit('seek', value)
}

function cycleSpeed() {
  emit('set-speed', props.speed >= 2 ? 1 : 2)
}
</script>

<template>
  <div data-testid="upstream-control-bar" class="upstream-bar">
    <button class="ub-btn" title="后退一帧" data-testid="ctl-prev" @click="emit('step', -1)">◀◀</button>
    <button
      class="ub-btn ub-btn--play"
      :title="playing ? '暂停' : '播放'"
      data-testid="ctl-toggle"
      @click="playing ? emit('pause') : emit('play')"
    >
      {{ playing ? '⏸' : '⏯' }}
    </button>
    <button class="ub-btn" title="前进一帧" data-testid="ctl-next" @click="emit('step', 1)">▶▶</button>

    <input
      class="ub-scrub"
      type="range"
      min="0"
      :max="last"
      :value="idx"
      data-testid="ctl-scrub"
      @input="onScrub"
    />
    <span class="ub-progress" data-testid="ctl-progress">{{ progressLabel }}</span>

    <label class="ub-hop2" data-testid="ctl-hop2">
      <input
        type="checkbox"
        :checked="showHop2"
        @change="emit('toggle-hop2', ($event.target as HTMLInputElement).checked)"
      />
      展开二跳
    </label>

    <button class="ub-btn ub-speed" title="倍速" data-testid="ctl-speed" @click="cycleSpeed">
      {{ speed }}x
    </button>
  </div>
</template>

<style scoped>
.upstream-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(8, 12, 20, 0.92);
  border: 1px solid rgba(126, 200, 255, 0.35);
  color: #d6e6ff;
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 12px;
}
.ub-btn {
  border: none;
  background: transparent;
  color: #cfe6ff;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
}
.ub-btn--play {
  font-size: 16px;
}
.ub-scrub {
  flex: 1 1 auto;
  min-width: 80px;
  accent-color: #7ec8ff;
}
.ub-progress {
  font-variant-numeric: tabular-nums;
  color: #9fb6d6;
  min-width: 34px;
  text-align: center;
}
.ub-hop2 {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: #9fb6d6;
  cursor: pointer;
}
.ub-speed {
  border: 1px solid rgba(126, 200, 255, 0.3);
  border-radius: 10px;
  padding: 1px 7px;
}
</style>

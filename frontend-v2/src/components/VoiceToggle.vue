<script setup lang="ts">
defineProps<{
  enabled: boolean
  playing?: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()
</script>

<template>
  <button
    type="button"
    class="voice-toggle"
    :class="{ active: enabled, playing }"
    :title="enabled ? '关闭语音引导' : '开启语音引导'"
    data-testid="voice-toggle"
    @click="emit('toggle')"
  >
    {{ enabled ? '🔊' : '🔇' }}
    <span class="label">{{ enabled ? '语音引导' : '静音' }}</span>
  </button>
</template>

<style scoped>
.voice-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid rgba(120, 200, 255, 0.25);
  background: rgba(0, 20, 40, 0.75);
  color: rgba(210, 240, 255, 0.85);
  font-size: 12px;
  cursor: pointer;
}

.voice-toggle.active {
  border-color: rgba(80, 200, 255, 0.55);
  color: #b8ecff;
}

.voice-toggle.playing .label {
  opacity: 0.85;
}

.label {
  letter-spacing: 0.02em;
}
</style>

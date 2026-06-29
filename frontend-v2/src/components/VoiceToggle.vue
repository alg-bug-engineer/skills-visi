<script setup lang="ts">
import voiceIconUrl from '../assets/voice-toggle-icon.png'

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
    :class="{ active: enabled, playing, muted: !enabled }"
    :title="enabled ? '关闭语音播报' : '开启语音播报'"
    :aria-label="enabled ? '关闭语音播报' : '开启语音播报'"
    :aria-pressed="enabled"
    data-testid="voice-toggle"
    @click="emit('toggle')"
  >
    <span class="voice-toggle__ring" aria-hidden="true" />
    <span class="voice-toggle__avatar" aria-hidden="true">
      <img
        class="voice-toggle__icon"
        :src="voiceIconUrl"
        alt=""
        width="64"
        height="64"
        draggable="false"
      />
    </span>
    <span class="voice-toggle__hover-action" aria-hidden="true">
      <svg
        v-if="enabled"
        class="voice-toggle__glyph voice-toggle__glyph--mute"
        viewBox="0 0 24 24"
        width="24"
        height="24"
        focusable="false"
      >
        <path
          fill="currentColor"
          d="M3 9v6h4l5 5V4L7 9H3zm11.2 2.4c0-1.2-.65-2.22-1.62-2.8v5.6c.97-.58 1.62-1.6 1.62-2.8z"
        />
        <path
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          d="M5.5 5.5l13 13"
        />
      </svg>
      <svg
        v-else
        class="voice-toggle__glyph voice-toggle__glyph--unmute"
        viewBox="0 0 24 24"
        width="24"
        height="24"
        focusable="false"
      >
        <path
          fill="currentColor"
          d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"
        />
      </svg>
    </span>
  </button>
</template>

<style scoped>
.voice-toggle {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  padding: 0;
  overflow: hidden;
  border: 1.5px solid rgba(0, 229, 255, 0.82);
  border-radius: 50%;
  background: rgba(6, 14, 24, 0.72);
  backdrop-filter: blur(8px);
  box-shadow: 0 0 16px rgba(0, 229, 255, 0.14);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.15s ease;
}

.voice-toggle:hover {
  border-color: #00e5ff;
  box-shadow: 0 0 20px rgba(0, 229, 255, 0.28);
  transform: scale(1.04);
}

.voice-toggle:active {
  transform: scale(0.98);
}

.voice-toggle.muted {
  border-color: rgba(0, 229, 255, 0.55);
  box-shadow: 0 0 10px rgba(0, 229, 255, 0.08);
}

.voice-toggle__ring {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 1px solid transparent;
  pointer-events: none;
}

.voice-toggle.active .voice-toggle__ring {
  border-color: rgba(0, 229, 255, 0.16);
}

.voice-toggle.playing .voice-toggle__ring {
  animation: voice-pulse 1.4s ease-out infinite;
}

.voice-toggle__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  overflow: hidden;
  background: #c8dce8;
}

.voice-toggle__icon {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center 12%;
  transition:
    filter 0.2s ease,
    opacity 0.2s ease,
    transform 0.2s ease;
}

.voice-toggle:hover .voice-toggle__icon {
  opacity: 0.42;
  filter: blur(1px);
  transform: scale(1.03);
}

.voice-toggle__hover-action {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  color: #00e5ff;
  background: transparent;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.18s ease;
}

.voice-toggle:hover .voice-toggle__hover-action {
  opacity: 1;
  background: rgba(4, 14, 24, 0.38);
}

.voice-toggle__glyph {
  filter: drop-shadow(0 0 8px rgba(0, 229, 255, 0.5));
}

@keyframes voice-pulse {
  0% {
    transform: scale(1);
    opacity: 0.75;
  }
  100% {
    transform: scale(1.18);
    opacity: 0;
  }
}
</style>

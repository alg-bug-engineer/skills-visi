<script setup lang="ts">
import { ref } from 'vue'
import { DEFAULT_PROMPT } from '../constants'

const props = defineProps<{
  docked: boolean
  locked: boolean
  loading: boolean
  conversation?: boolean
}>()

const emit = defineEmits<{
  send: [content: string]
  inputActivity: [value: string]
}>()

const input = ref('')
const placeholder = DEFAULT_PROMPT

function submit() {
  if (props.locked || props.loading) return
  const text = input.value.trim() || placeholder
  input.value = ''
  emit('send', text)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}
</script>

<template>
  <div :class="['input-dock', { docked, locked }]">
    <div class="dock-inner">
      <p v-if="!docked" class="hero-title">济南交通智能体</p>
      <p v-if="!docked" class="hero-sub">描述路口拥堵，或直接使用示例一键分析</p>
      <div class="composer">
        <textarea
          v-model="input"
          :rows="docked ? 1 : 2"
          :placeholder="placeholder"
          :disabled="locked || loading"
          @input="emit('inputActivity', input)"
          @keydown="onKeydown"
        />
        <button
          type="button"
          class="send-btn"
          data-testid="send-button"
          :disabled="locked || loading"
          @click="submit"
        >
          <span v-if="loading" class="spinner" />
          <span v-else>发送</span>
        </button>
      </div>
      <p v-if="docked && conversation && !locked" class="lock-hint conversation-hint">
        请补充信息后发送，系统将引导您完成描述
      </p>
      <p v-else-if="locked" class="lock-hint">分析进行中，请跟随地图步骤…</p>
    </div>
  </div>
</template>

<style scoped>
.input-dock {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  z-index: 12;
  width: min(640px, calc(100% - 32px));
  transition:
    top 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    bottom 0.85s cubic-bezier(0.22, 1, 0.36, 1),
    transform 0.85s cubic-bezier(0.22, 1, 0.36, 1);
}

.input-dock:not(.docked) {
  top: 50%;
  bottom: auto;
  transform: translate(-50%, -50%);
}

.input-dock.docked {
  top: auto;
  bottom: 20px;
  transform: translateX(-50%);
  z-index: 20;
}

.dock-inner {
  padding: 16px 18px;
  border-radius: 4px;
  background: rgba(0, 10, 20, 0.88);
  border: 1px solid rgba(0, 229, 255, 0.28);
  backdrop-filter: blur(12px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);
  font-family: 'Courier New', Courier, monospace;
}

.input-dock.docked .dock-inner {
  padding: 10px 14px;
}

.hero-title {
  margin: 0 0 4px;
  text-align: center;
  font-size: 20px;
  font-weight: 600;
  color: rgba(238, 246, 255, 0.95);
  letter-spacing: 1px;
}

.hero-sub {
  margin: 0 0 14px;
  text-align: center;
  font-size: 12px;
  color: rgba(220, 240, 255, 0.45);
}

.composer {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.composer textarea {
  flex: 1;
  resize: none;
  min-height: 44px;
  padding: 10px 12px;
  border-radius: 2px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: rgba(0, 8, 16, 0.85);
  color: rgba(238, 246, 255, 0.95);
  font-size: 13px;
  font-family: inherit;
  line-height: 1.5;
}

.composer textarea:focus {
  outline: none;
  border-color: rgba(0, 229, 255, 0.55);
  box-shadow: 0 0 0 1px rgba(0, 212, 240, 0.2);
}

.send-btn {
  min-width: 72px;
  height: 42px;
  border: 1px solid rgba(0, 229, 255, 0.45);
  border-radius: 2px;
  background: rgba(0, 212, 240, 0.15);
  color: #00e5ff;
  font-weight: 600;
  font-size: 12px;
  cursor: pointer;
  letter-spacing: 1px;
  font-family: inherit;
}

.send-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.lock-hint {
  margin: 8px 0 0;
  text-align: center;
  font-size: 12px;
  color: #a0aec0;
}

.spinner {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>

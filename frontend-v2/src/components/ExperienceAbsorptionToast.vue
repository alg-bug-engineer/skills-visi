<script setup lang="ts">
import type { AbsorptionToast } from '../composables/useAbsorptionToasts'

defineProps<{
  toasts: AbsorptionToast[]
}>()

const emit = defineEmits<{ dismiss: [id: number] }>()

function kindLabel(kind: string): string {
  return kind === 'cognition' ? '认知经验' : '诊断经验'
}
</script>

<template>
  <div class="toast-stack" aria-live="polite">
    <TransitionGroup name="toast-rise">
      <article
        v-for="t in toasts"
        :key="t.id"
        class="toast"
        :class="[`kind-${t.kind}`, t.kind === 'cognition' ? `st-${t.status}` : '']"
        data-testid="absorption-toast"
      >
        <header class="toast-head">
          <span class="kind-badge">{{ kindLabel(t.kind) }}</span>
          <button type="button" class="close" aria-label="关闭" @click="emit('dismiss', t.id)">×</button>
        </header>
        <p class="toast-title">{{ t.header }}</p>
        <p v-if="t.text" class="toast-text">{{ t.text }}</p>
        <div v-if="t.tags.length" class="tag-row">
          <span v-for="(tag, i) in t.tags" :key="i" class="tag">{{ tag }}</span>
        </div>
        <p class="toast-footer">{{ t.footer }}</p>
      </article>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 1200;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 320px;
  max-width: calc(100vw - 36px);
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  padding: 12px 14px;
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(10, 22, 38, 0.98), rgba(6, 14, 26, 0.98));
  border: 1px solid rgba(94, 184, 255, 0.22);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  color: #e6f2ff;
  backdrop-filter: blur(8px);
}

.toast.kind-cognition.st-verified {
  border-left: 3px solid #4ade80;
}

.toast.kind-cognition.st-data_doubt {
  border-left: 3px solid #fbbf24;
}

.toast.kind-diagnosis {
  border-left: 3px solid #38bdf8;
}

.toast-head {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
}

.kind-badge {
  font-size: 10px;
  letter-spacing: 0.5px;
  padding: 1px 7px;
  border-radius: 8px;
  background: rgba(56, 189, 248, 0.16);
  color: #7dd3fc;
}

.close {
  margin-left: auto;
  border: none;
  background: transparent;
  color: rgba(186, 215, 240, 0.6);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.close:hover {
  color: #e6f2ff;
}

.toast-title {
  margin: 0;
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.5;
  color: #f0f8ff;
}

.toast-text {
  margin: 5px 0 0;
  font-size: 11.5px;
  line-height: 1.55;
  color: rgba(210, 228, 244, 0.85);
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.tag {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(94, 184, 255, 0.18);
  color: rgba(214, 234, 248, 0.9);
}

.toast-footer {
  margin: 9px 0 0;
  padding-top: 7px;
  border-top: 1px dashed rgba(120, 140, 160, 0.2);
  font-size: 11px;
  color: rgba(125, 211, 252, 0.92);
}

.toast-rise-enter-active {
  transition: transform 0.32s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.32s ease;
}

.toast-rise-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
  position: absolute;
}

.toast-rise-enter-from {
  transform: translateY(24px);
  opacity: 0;
}

.toast-rise-leave-to {
  transform: translateY(8px);
  opacity: 0;
}
</style>

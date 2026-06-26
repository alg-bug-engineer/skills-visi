<script setup lang="ts">
defineProps<{
  labels: readonly string[]
  activeIndex: number
}>()
</script>

<template>
  <div class="process-bar">
    <div
      v-for="(label, i) in labels"
      :key="label"
      :class="['step', { done: i < activeIndex, active: i === activeIndex }]"
    >
      <span class="dot">{{ i + 1 }}</span>
      <span class="label">{{ label }}</span>
    </div>
  </div>
</template>

<style scoped>
.process-bar {
  position: absolute;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 8;
  display: flex;
  gap: 4px;
  padding: 6px 10px;
  border-radius: 2px;
  background: rgba(0, 10, 20, 0.82);
  border: 1px solid rgba(0, 229, 255, 0.28);
  backdrop-filter: blur(8px);
  max-width: calc(100% - 420px);
  overflow-x: auto;
  font-family: 'Courier New', Courier, monospace;
}

.step {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 2px;
  color: rgba(220, 240, 255, 0.35);
  font-size: 10px;
  white-space: nowrap;
  letter-spacing: 0.5px;
  border: 1px solid transparent;
}

.step.done {
  color: rgba(220, 240, 255, 0.55);
}

.step.active {
  color: #00e5ff;
  background: rgba(0, 229, 255, 0.12);
  border-color: rgba(0, 229, 255, 0.45);
}

.dot {
  width: 14px;
  height: 14px;
  border-radius: 2px;
  display: grid;
  place-items: center;
  font-size: 9px;
  background: rgba(255, 255, 255, 0.06);
}

.step.active .dot {
  background: rgba(0, 212, 240, 0.25);
  color: #00d4f0;
  font-weight: 700;
}

.step.done .dot {
  background: rgba(255, 255, 255, 0.08);
}
</style>

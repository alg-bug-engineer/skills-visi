<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { useTyping } from '@/composables/useTyping'

const store = usePresentationStore()
const { acts, currentAct } = storeToRefs(store)

const instant = ref(
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
)

const lines = computed(() => store.activeAct?.narration ?? [])

const { shown, done } = useTyping(lines, {
  instant: instant.value,
  onDone: () => {
    const idx = store.currentAct
    store.onActTyped(idx)
    if (store.autoPlay && idx < store.lastActIndex) {
      window.setTimeout(() => {
        if (store.currentAct === idx) store.advance()
      }, 750)
    }
  },
})
</script>

<template>
  <aside class="process us-panel" data-testid="process-panel">
    <header class="process__hd">
      <span class="dot" />
      <h2>理解过程</h2>
    </header>

    <ol class="steps">
      <li
        v-for="(a, i) in acts"
        :key="a.id"
        class="step"
        :class="{ active: i === currentAct, done: i < currentAct }"
        @click="store.goToAct(i)"
      >
        <span class="step__idx">{{ i < currentAct ? '✓' : i + 1 }}</span>
        <span class="step__title">{{ a.processTitle }}</span>
      </li>
    </ol>

    <div class="typing" data-testid="process-typing">
      <p v-for="(l, i) in shown" :key="i" class="typing__line">
        {{ l }}<span v-if="i === shown.length - 1 && !done" class="caret">▍</span>
      </p>
    </div>
  </aside>
</template>

<style scoped>
.process {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px 14px;
  overflow: hidden;
}
.process__hd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.process__hd h2 {
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 3px;
  margin: 0;
  color: var(--text);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: var(--glow-primary);
}
.steps {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-mute);
  font-size: 13px;
  transition: all 0.2s;
}
.step.active {
  color: var(--primary);
  background: var(--primary-dim);
}
.step.done {
  color: var(--protected);
}
.step__idx {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px solid currentColor;
  font-size: 11px;
  flex: 0 0 auto;
}
.typing {
  flex: 1;
  overflow-y: auto;
  border-top: 1px solid var(--panel-border);
  padding-top: 12px;
}
.typing__line {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-dim);
  white-space: pre-wrap;
  word-break: break-word;
}
.caret {
  color: var(--primary);
  animation: blink 1s step-end infinite;
}
@keyframes blink {
  50% {
    opacity: 0;
  }
}
</style>

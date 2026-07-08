<script setup lang="ts">
import { computed } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()

const promptIntersection = computed(
  () => productCopy(store.ticket?.intersection_name ?? '') || '本路口',
)
</script>

<template>
  <Teleport to="body">
    <div
      v-if="store.solidifyPhase === 'prompt'"
      class="solidify-overlay"
      role="dialog"
      aria-label="技能固化确认"
      data-testid="solidify-overlay"
    >
      <div class="prompt us-panel" data-testid="solidify-prompt">
        <h2 class="prompt__title">技能固化</h2>
        <p class="prompt__body">
          是否将本次『{{ promptIntersection }}』的处置经验固化为可复用路口技能？确认后请在右侧「经验固化」页签查看进度。
        </p>
        <div class="prompt__actions">
          <button
            type="button"
            class="btn btn--ghost"
            data-testid="solidify-decline"
            @click="store.declineSolidify()"
          >
            暂不固化
          </button>
          <button
            type="button"
            class="btn btn--primary"
            data-testid="solidify-confirm"
            @click="store.confirmSolidify()"
          >
            确认固化
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.solidify-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3vh 3vw;
  background: rgba(2, 8, 16, 0.78);
  backdrop-filter: blur(6px);
}
.prompt {
  width: min(460px, calc(100% - 32px));
  padding: 22px 24px;
  border-radius: var(--radius);
  border: 1px solid rgba(0, 229, 255, 0.32);
  background: rgba(6, 14, 26, 0.98);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.55);
}
.prompt__title {
  margin: 0 0 12px;
  font-size: 17px;
  color: var(--text);
}
.prompt__body {
  margin: 0 0 20px;
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--text-dim);
}
.prompt__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.btn {
  padding: 8px 20px;
  border-radius: var(--radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
}
.btn--primary {
  background: var(--primary);
  color: var(--bg);
}
.btn--ghost {
  background: transparent;
  border-color: var(--panel-border);
  color: var(--text-dim);
}
.btn--ghost:hover {
  color: var(--primary);
  border-color: var(--primary);
}
</style>

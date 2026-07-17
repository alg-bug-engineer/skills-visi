<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'
import { useSkillBuildProcess } from '@/composables/useSkillBuildProcess'
import SkillBuildPanel from '@/panels/SkillBuildPanel.vue'

const store = usePresentationStore()
const { solidifyPhase } = storeToRefs(store)

const build = useSkillBuildProcess()

const instant = (() => {
  const reduced =
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const automation =
    typeof navigator !== 'undefined' && (navigator as Navigator).webdriver === true
  return reduced || automation
})()

const buildStarted = ref(false)

watch(
  () => solidifyPhase.value,
  (phase) => {
    if (phase === 'idle') {
      buildStarted.value = false
      build.reset()
    }
  },
)

watch(
  () => [solidifyPhase.value, store.skillResult] as const,
  ([phase, result]) => {
    if (phase === 'building' && result && !buildStarted.value) {
      buildStarted.value = true
      build.start(
        result.build,
        {
          skillId: result.skill_id,
          skillDir: result.skill_dir,
          downloadUrl: result.download_url,
          intersection: result.intersection ?? '',
          timePeriodLabel: result.time_period_label ?? '',
          action: result.action,
        },
        {
          instant,
          // 技能沉淀打字速度降为原来的 0.8（每块间隔 16ms → 20ms）
          typeDelayMs: 20,
          onDone: () => store.setSolidifyPhase('completed'),
        },
      )
    }
  },
  { immediate: true },
)
</script>

<template>
  <Transition name="skill-drawer">
    <aside
      v-if="solidifyPhase === 'building' || solidifyPhase === 'completed'"
      class="skill-drawer us-panel"
      data-testid="skill-build-drawer"
    >
      <SkillBuildPanel
        :state="build.state"
        @select="build.selectFile($event)"
        @finish="store.finishSolidify()"
      />
    </aside>
  </Transition>
</template>

<style scoped>
.skill-drawer {
  position: absolute;
  top: 64px;
  bottom: 16px;
  left: 16px;
  width: min(1080px, 72vw);
  z-index: 45;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 14px 16px;
  border-radius: var(--radius);
  border-color: rgba(26, 127, 255, 0.32);
  background: rgba(4, 13, 24, 0.96);
  box-shadow: 0 18px 60px rgba(0, 0, 0, 0.55);
}
.skill-drawer > :deep(*) {
  flex: 1;
  min-height: 0;
}
.skill-drawer-enter-active,
.skill-drawer-leave-active {
  transition:
    transform 0.42s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.42s cubic-bezier(0.22, 1, 0.36, 1);
}
.skill-drawer-enter-from,
.skill-drawer-leave-to {
  transform: translateX(-24px);
  opacity: 0;
}
</style>

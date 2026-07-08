<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { usePresentationStore } from '@/stores/presentation'
import { useExperienceAbsorption } from '@/composables/useExperienceAbsorption'
import { useSkillBuildProcess } from '@/composables/useSkillBuildProcess'
import ExperienceAbsorptionPanel from '@/panels/ExperienceAbsorptionPanel.vue'
import SkillBuildPanel from '@/panels/SkillBuildPanel.vue'
import { productCopy } from '@/utils/productCopy'

const store = usePresentationStore()

const absorption = useExperienceAbsorption()
const build = useSkillBuildProcess()

// 即时全量：无障碍偏好或自动化环境（与 composables 探测一致，保证测试确定性）。
const instant = (() => {
  const reduced =
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const automation =
    typeof navigator !== 'undefined' && (navigator as Navigator).webdriver === true
  return reduced || automation
})()

const absorptionStarted = ref(false)
const buildStarted = ref(false)

const promptIntersection = computed(
  () => productCopy(store.ticket?.intersection_name ?? '') || '本路口',
)

watch(
  () => [store.solidifyPhase, store.skillResult] as const,
  ([phase, result]) => {
    if (phase === 'absorbing' && result && !absorptionStarted.value) {
      absorptionStarted.value = true
      absorption.start(result.absorption, {
        instant,
        skillId: result.skill_id,
        intersection: result.intersection ?? '',
        onDone: () => store.setSolidifyPhase('building'),
      })
    } else if (phase === 'building' && result && !buildStarted.value) {
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
          onDone: () => store.setSolidifyPhase('completed'),
        },
      )
    } else if (phase === 'idle') {
      absorptionStarted.value = false
      buildStarted.value = false
      absorption.reset()
      build.reset()
    }
  },
  { immediate: true },
)
</script>

<template>
  <Teleport to="body">
    <div
      v-if="store.solidifyPhase !== 'idle'"
      class="solidify-overlay"
      role="dialog"
      aria-label="技能固化"
      data-testid="solidify-overlay"
    >
      <!-- 确认弹窗 -->
      <div v-if="store.solidifyPhase === 'prompt'" class="prompt us-panel" data-testid="solidify-prompt">
        <h2 class="prompt__title">技能固化</h2>
        <p class="prompt__body">
          是否将本次『{{ promptIntersection }}』的处置经验固化为可复用路口技能？
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

      <!-- 吸收 / 构建工作台 -->
      <div v-else class="workspace">
        <div
          v-if="store.solidifyPhase === 'absorbing'"
          class="workspace__absorb-full"
        >
          <ExperienceAbsorptionPanel :state="absorption.state" />
        </div>

        <div v-else class="workspace__split">
          <div class="workspace__aside">
            <ExperienceAbsorptionPanel :state="absorption.state" />
          </div>
          <div class="workspace__main">
            <SkillBuildPanel
              :state="build.state"
              @select="build.selectFile($event)"
              @finish="store.finishSolidify()"
            />
          </div>
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
.workspace {
  width: 100%;
  height: 100%;
  display: flex;
}
.workspace__absorb-full {
  margin: auto;
  width: min(720px, 100%);
  height: min(80vh, 100%);
}
.workspace__split {
  display: grid;
  grid-template-columns: minmax(280px, 0.9fr) minmax(0, 2fr);
  gap: 14px;
  width: 100%;
  height: 100%;
}
.workspace__aside,
.workspace__main {
  min-height: 0;
  min-width: 0;
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
@media (max-width: 980px) {
  .workspace__split {
    grid-template-columns: 1fr;
    grid-auto-rows: minmax(0, 1fr);
  }
}
</style>

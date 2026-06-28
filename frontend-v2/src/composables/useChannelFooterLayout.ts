import { computed, type ComputedRef, type Ref, unref } from 'vue'
import type { CognitionPayload } from '../types/map'
import type { ProblemEvidence } from '../types/evidence'
import type { PipelinePhase, RuntimeMetrics } from '../types/presentation'
import { buildQueueDataFromEvidence } from '../utils/cognitionChannelAdapter'

/** 浮动面板距底边基础间距（图例、运行数据卡等同层浮层） */
export const CHAN_FOOTER_BASE = 12

type MaybeRef<T> = Ref<T> | ComputedRef<T>

export function useChannelFooterLayout(options: {
  phase: MaybeRef<PipelinePhase>
  cognition: MaybeRef<CognitionPayload | null>
  evidence: MaybeRef<ProblemEvidence | null>
  runtimeMetrics?: MaybeRef<RuntimeMetrics | null>
  fullscreen?: MaybeRef<boolean>
  active?: MaybeRef<boolean>
  /** 新一轮分析标识，预留用于重置粘性浮层（当前未使用，保持调用方类型一致） */
  runKey?: MaybeRef<number>
}) {
  const queueArms = computed(() =>
    buildQueueDataFromEvidence(
      unref(options.cognition),
      unref(options.evidence),
      unref(options.runtimeMetrics) ?? null,
    ),
  )

  const layoutActive = computed(() => {
    if (options.active !== undefined && !unref(options.active)) return false
    if (options.fullscreen !== undefined && !unref(options.fullscreen)) return false
    return true
  })

  const floatingBottomPx = computed(() => (layoutActive.value ? CHAN_FOOTER_BASE : CHAN_FOOTER_BASE))

  const floatingBottomStyle = computed(() => ({
    bottom: `${floatingBottomPx.value}px`,
  }))

  return {
    queueArms,
    floatingBottomPx,
    floatingBottomStyle,
  }
}

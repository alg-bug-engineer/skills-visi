import { computed, ref, watch, type ComputedRef, type Ref, unref } from 'vue'
import type { CognitionPayload } from '../types/map'
import type { ProblemEvidence } from '../types/evidence'
import type { PipelinePhase, RuntimeMetrics } from '../types/presentation'
import { buildQueueDataFromEvidence } from '../utils/cognitionChannelAdapter'

/** 四向进口横幅揭示阶段：分向饱和度起，后续阶段粘性常驻 */
const METRIC_STRIP_REVEAL_PHASES: PipelinePhase[] = [
  'direction',
  'granularity',
  'timing',
  'corridor',
  'external',
  'saturation',
  'imbalance',
  'rule',
  'conclusion',
  'evidence',
]

/** 浮动面板距底边基础间距（仅用于与底部横幅同层的浮层，如图例在 chan-body 内则勿叠加 footer 高度） */
export const CHAN_FOOTER_BASE = 12
/** 四向进口指标条占用高度（含内边距） */
export const CHAN_FOOTER_METRIC_H = 76
/** 进口失衡系数横幅占用高度（含内边距） */
export const CHAN_FOOTER_IMBALANCE_H = 44

type MaybeRef<T> = Ref<T> | ComputedRef<T>

export function useChannelFooterLayout(options: {
  phase: MaybeRef<PipelinePhase>
  cognition: MaybeRef<CognitionPayload | null>
  evidence: MaybeRef<ProblemEvidence | null>
  runtimeMetrics?: MaybeRef<RuntimeMetrics | null>
  fullscreen?: MaybeRef<boolean>
  active?: MaybeRef<boolean>
  /** 新一轮分析时递增，用于重置底部横幅揭示状态 */
  runKey?: MaybeRef<number>
}) {
  const metricStripRevealed = ref(false)
  const imbalanceRevealed = ref(false)
  const imbalance = computed(
    () =>
      unref(options.evidence)?.metrics?.imbalance_index ??
      unref(options.runtimeMetrics)?.imbalance_index,
  )

  const queueArms = computed(() =>
    buildQueueDataFromEvidence(
      unref(options.cognition),
      unref(options.evidence),
      unref(options.runtimeMetrics) ?? null,
    ),
  )

  watch(
    () => unref(options.runKey),
    () => {
      metricStripRevealed.value = false
      imbalanceRevealed.value = false
    },
  )

  watch(
    () =>
      [
        unref(options.phase),
        queueArms.value.length,
        imbalance.value,
      ] as const,
    ([phase, armCount, imb]) => {
      if (
        armCount > 0 &&
        METRIC_STRIP_REVEAL_PHASES.includes(phase ?? 'idle')
      ) {
        metricStripRevealed.value = true
      }
      if (imb != null && phase === 'imbalance') {
        imbalanceRevealed.value = true
      }
    },
    { immediate: true },
  )

  const layoutActive = computed(() => {
    if (options.active !== undefined && !unref(options.active)) return false
    if (options.fullscreen !== undefined && !unref(options.fullscreen)) return false
    return true
  })

  const showMetricStrip = computed(
    () =>
      layoutActive.value &&
      metricStripRevealed.value &&
      queueArms.value.length > 0,
  )

  const showImbalanceBanner = computed(
    () =>
      layoutActive.value &&
      imbalanceRevealed.value &&
      imbalance.value != null &&
      metricStripRevealed.value,
  )

  const floatingBottomPx = computed(() => {
    let bottom = CHAN_FOOTER_BASE
    if (showMetricStrip.value) bottom += CHAN_FOOTER_METRIC_H
    if (showImbalanceBanner.value) bottom += CHAN_FOOTER_IMBALANCE_H
    return bottom
  })

  const floatingBottomStyle = computed(() => ({
    bottom: `${floatingBottomPx.value}px`,
  }))

  return {
    queueArms,
    showMetricStrip,
    showImbalanceBanner,
    metricStripRevealed,
    imbalanceRevealed,
    imbalance,
    floatingBottomPx,
    floatingBottomStyle,
  }
}

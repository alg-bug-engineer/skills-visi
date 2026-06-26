<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { CognitionArm, ArmMetric, CognitionPayload } from '../../types/map'
import type { ProblemEvidence } from '../../types/evidence'
import { drawChannelization } from '../../utils/channelizationDraw'
import { buildLaneQueueMap } from '../../utils/channelizationMetrics'
import { normalizeDir } from '../../utils/mapMarkers'

const props = defineProps<{
  cognition: CognitionPayload | null
  highlightDirs?: string[]
  highlightTurnKeys?: string[]
  evidence?: ProblemEvidence | null
  protectedDirs?: string[]
  showMetrics?: boolean
  compact?: boolean
  fullscreen?: boolean
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)
let resizeObs: ResizeObserver | null = null

const laneQueues = computed(() =>
  buildLaneQueueMap(props.cognition, props.evidence ?? null),
)

function pickHighlightDir(): string | null {
  if (props.highlightDirs?.length) {
    return normalizeDir(props.highlightDirs[0])
  }
  return null
}

function render() {
  const svg = svgRef.value
  const container = containerRef.value
  if (!svg || !container || !props.cognition?.arms?.length) return

  const rect = container.getBoundingClientRect()
  const maxSize = props.fullscreen ? Math.min(rect.width, rect.height) : Math.min(rect.width, rect.height, 520)
  const size = Math.max(280, maxSize)
  const scale = size / (props.fullscreen ? 360 : 320)

  svg.setAttribute('width', String(size))
  svg.setAttribute('height', String(size))
  svg.innerHTML = ''

  drawChannelization(svg, {
    centerX: size / 2,
    centerY: size / 2,
    scale,
    arms: props.cognition.arms as CognitionArm[],
    metricsByArm: (props.cognition.metrics_by_arm ?? []) as ArmMetric[],
    showMetrics: props.showMetrics !== false,
    highlightDir: pickHighlightDir(),
    highlightTurnKeys: props.highlightTurnKeys ?? [],
    laneQueues: laneQueues.value,
    compact: props.compact ?? false,
    fullscreen: props.fullscreen ?? false,
  })
}

watch(
  () => [
    props.cognition,
    props.highlightDirs,
    props.highlightTurnKeys,
    props.evidence,
    props.protectedDirs,
    props.showMetrics,
    props.fullscreen,
    laneQueues.value,
  ],
  () => render(),
  { deep: true },
)

onMounted(() => {
  render()
  if (containerRef.value) {
    resizeObs = new ResizeObserver(() => render())
    resizeObs.observe(containerRef.value)
  }
})

onUnmounted(() => resizeObs?.disconnect())
</script>

<template>
  <div
    ref="containerRef"
    class="channelization-view"
    :class="{ fullscreen: fullscreen }"
  >
    <div v-if="!cognition?.arms?.length" class="empty">渠化数据加载后显示示意图</div>
    <svg v-else ref="svgRef" class="chan-svg" role="img" aria-label="路口渠化示意图" />
  </div>
</template>

<style scoped>
.channelization-view {
  width: 100%;
  height: 100%;
  min-height: 200px;
  display: grid;
  place-items: center;
  background: rgba(0, 6, 14, 0.75);
  border: 1px solid rgba(0, 212, 240, 0.12);
}

.channelization-view.fullscreen {
  min-height: 0;
  border: none;
  background: #1e2430;
}

.chan-svg {
  display: block;
  max-width: 100%;
  max-height: 100%;
}

.empty {
  font-size: 12px;
  color: rgba(200, 230, 255, 0.4);
  padding: 24px;
  text-align: center;
}
</style>

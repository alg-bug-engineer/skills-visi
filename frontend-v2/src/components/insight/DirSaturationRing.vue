<script setup lang="ts">
import { computed } from 'vue'
import { severityColor } from '../../utils/ringSeverity'

interface ApproachProfile {
  dir8_code: number
  turn_saturation_max?: number | null
  green_util_min?: number | null
}

const props = withDefaults(
  defineProps<{
    profiles?: ApproachProfile[]
    size?: number
  }>(),
  { profiles: () => [], size: 64 },
)

// 四个主进口道按方位固定落点：北(上)/东(右)/南(下)/西(左)。
const DIR8_SEGMENTS = [
  { dir8: 0, label: '北', mid: -90 },
  { dir8: 2, label: '东', mid: 0 },
  { dir8: 4, label: '南', mid: 90 },
  { dir8: 6, label: '西', mid: 180 },
]

const radius = computed(() => props.size / 2 - 6)
const center = computed(() => props.size / 2)

function polar(angleDeg: number, r: number) {
  const a = (angleDeg * Math.PI) / 180
  return { x: center.value + r * Math.cos(a), y: center.value + r * Math.sin(a) }
}

function arcPath(midDeg: number): string {
  const r = radius.value
  const start = polar(midDeg - 40, r)
  const end = polar(midDeg + 40, r)
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`
}

const segments = computed(() =>
  DIR8_SEGMENTS.map((seg) => {
    const profile = props.profiles.find((p) => p.dir8_code === seg.dir8)
    const sat = profile?.turn_saturation_max ?? null
    return {
      ...seg,
      sat,
      color: severityColor(sat),
      d: arcPath(seg.mid),
    }
  }),
)
</script>

<template>
  <svg
    data-testid="dir-saturation-ring"
    :width="size"
    :height="size"
    :viewBox="`0 0 ${size} ${size}`"
    class="dir-saturation-ring"
  >
    <path
      v-for="seg in segments"
      :key="seg.dir8"
      class="ring-seg"
      :data-dir8="seg.dir8"
      :data-sat="seg.sat ?? ''"
      :d="seg.d"
      :stroke="seg.color"
      fill="none"
      stroke-width="6"
      stroke-linecap="round"
    />
  </svg>
</template>

<style scoped>
.dir-saturation-ring {
  display: block;
}
.ring-seg {
  transition: stroke 0.3s ease;
}
</style>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { PhaseStageTiming, StageMovement } from '@/api/types'
import { flowKeysFromStage, flowKeysFromStageMovements, type FlowKey } from '@/viz/planVisualization'

const props = defineProps<{ stage?: PhaseStageTiming; movements?: StageMovement[] }>()
const canvasRef = ref<HTMLCanvasElement | null>(null)

const activeKeys = computed<FlowKey[]>(() => {
  if (props.stage) return flowKeysFromStage(props.stage)
  return flowKeysFromStageMovements(props.movements)
})

function draw() {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) return
  const width = canvas.width
  const height = canvas.height
  ctx.clearRect(0, 0, width, height)
  ctx.fillStyle = '#073f5e'
  ctx.fillRect(0, 0, width, height)
  drawRoadBase(ctx, width, height)
  drawActiveFlows(ctx, width, height, new Set(activeKeys.value))
}

function drawRoadBase(ctx: CanvasRenderingContext2D, width: number, height: number) {
  ctx.strokeStyle = 'rgba(226,232,240,.16)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(42, 0)
  ctx.lineTo(42, 42)
  ctx.lineTo(0, 42)
  ctx.moveTo(108, 0)
  ctx.lineTo(108, 42)
  ctx.lineTo(width, 42)
  ctx.moveTo(42, height)
  ctx.lineTo(42, 108)
  ctx.lineTo(0, 108)
  ctx.moveTo(108, height)
  ctx.lineTo(108, 108)
  ctx.lineTo(width, 108)
  ctx.moveTo(0, 75)
  ctx.lineTo(width, 75)
  ctx.moveTo(75, 0)
  ctx.lineTo(75, height)
  ctx.stroke()
}

function drawActiveFlows(ctx: CanvasRenderingContext2D, width: number, height: number, active: Set<string>) {
  const color = '#12d6bd'
  const ped = '#4ade80'
  const up = -Math.PI / 2
  const down = Math.PI / 2
  const left = Math.PI
  const right = 0
  const defs: Record<string, { points: number[][]; angle: number; width?: number; arrowSize?: number }> = {
    '0_1': { points: [[64, 0], [64, 38]], angle: down },
    '0_2': { points: [[74, 0], [74, 29], [85, 40]], angle: 0.78 },
    '0_3': { points: [[54, 0], [54, 28], [45, 40]], angle: 2.28 },
    '4_1': { points: [[86, height], [86, 112]], angle: up },
    '4_2': { points: [[76, height], [76, 121], [64, 110]], angle: -2.36 },
    '4_3': { points: [[96, height], [96, 122], [105, 110]], angle: -0.86 },
    '2_1': { points: [[width, 62], [112, 62]], angle: left },
    '2_2': { points: [[width, 74], [123, 74], [112, 85]], angle: 2.36 },
    '2_3': { points: [[width, 52], [123, 52], [111, 44]], angle: -2.55 },
    '6_1': { points: [[0, 88], [38, 88]], angle: right },
    '6_2': { points: [[0, 76], [27, 76], [38, 65]], angle: -0.78 },
    '6_3': { points: [[0, 98], [27, 98], [39, 106]], angle: 0.58 },
    '0_4': { points: [[88, 0], [88, 42], [99, 42], [99, 27]], angle: up, width: 3.1, arrowSize: 8.5 },
    '4_4': { points: [[62, height], [62, 108], [51, 108], [51, 123]], angle: down, width: 3.1, arrowSize: 8.5 },
    '2_4': { points: [[width, 86], [108, 86], [108, 97], [123, 97]], angle: right, width: 3.1, arrowSize: 8.5 },
    '6_4': { points: [[0, 64], [42, 64], [42, 53], [27, 53]], angle: left, width: 3.1, arrowSize: 8.5 },
  }

  for (const [key, def] of Object.entries(defs)) {
    if (active.has(key)) drawPathWithArrow(ctx, def.points, def.angle, color, def.width ?? 3.8, def.arrowSize ?? 10.5)
  }
  if (active.has('0_5')) zebraCrossing(ctx, 38, 48, 90, 56, ped, false)
  if (active.has('4_5')) zebraCrossing(ctx, 68, 94, 120, 102, ped, false)
  if (active.has('2_5')) zebraCrossing(ctx, 98, 36, 106, 82, ped, true)
  if (active.has('6_5')) zebraCrossing(ctx, 44, 76, 52, 118, ped, true)
}

function drawPathWithArrow(
  ctx: CanvasRenderingContext2D,
  points: number[][],
  angle: number,
  color: string,
  width: number,
  arrowSize: number,
) {
  ctx.strokeStyle = color
  ctx.fillStyle = color
  ctx.lineWidth = width
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.beginPath()
  ctx.moveTo(points[0][0], points[0][1])
  for (let i = 1; i < points.length; i += 1) ctx.lineTo(points[i][0], points[i][1])
  ctx.stroke()

  const [x, y] = points[points.length - 1]
  ctx.beginPath()
  ctx.moveTo(x, y)
  ctx.lineTo(x - arrowSize * Math.cos(angle - Math.PI / 6), y - arrowSize * Math.sin(angle - Math.PI / 6))
  ctx.lineTo(x - arrowSize * Math.cos(angle + Math.PI / 6), y - arrowSize * Math.sin(angle + Math.PI / 6))
  ctx.fill()
}

function zebraCrossing(
  ctx: CanvasRenderingContext2D,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  color: string,
  vertical: boolean,
) {
  ctx.fillStyle = color
  const stripeCount = 4
  if (!vertical) {
    const stripeW = (x1 - x0) / (stripeCount * 2 - 1)
    for (let i = 0; i < stripeCount; i += 1) ctx.fillRect(x0 + i * stripeW * 2, y0, stripeW, y1 - y0)
  } else {
    const stripeH = (y1 - y0) / (stripeCount * 2 - 1)
    for (let i = 0; i < stripeCount; i += 1) ctx.fillRect(x0, y0 + i * stripeH * 2, x1 - x0, stripeH)
  }
}

onMounted(draw)
watch(activeKeys, draw, { deep: true })
</script>

<template>
  <div class="movement">
    <canvas ref="canvasRef" width="150" height="150" aria-label="阶段释放方向图" />
  </div>
</template>

<style scoped>
.movement {
  display: grid;
  justify-items: center;
}
canvas {
  width: 100%;
  max-width: 150px;
  border-radius: var(--radius-sm);
  background: #073f5e;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.12);
}
</style>

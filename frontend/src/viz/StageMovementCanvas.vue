<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { StageMovement } from '@/api/types'

const props = defineProps<{ movements: StageMovement[] }>()
const canvasRef = ref<HTMLCanvasElement | null>(null)

function draw() {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx) return
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.fillStyle = '#08394a'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.strokeStyle = 'rgba(231,245,255,.12)'
  ctx.lineWidth = 4
  ctx.beginPath()
  ctx.moveTo(0, 75)
  ctx.lineTo(150, 75)
  ctx.moveTo(75, 0)
  ctx.lineTo(75, 150)
  ctx.stroke()
  props.movements.forEach((movement, index) => drawMovement(ctx, movement, index))
}

function drawMovement(ctx: CanvasRenderingContext2D, movement: StageMovement, index: number) {
  const dir = movement.dir8No
  if (typeof dir !== 'number') return
  const color = index % 2 === 0 ? '#12d6bd' : '#6dffb5'
  ctx.strokeStyle = color
  ctx.fillStyle = color
  ctx.lineWidth = 4
  ctx.beginPath()
  if (dir === 6) {
    ctx.moveTo(10, 82)
    ctx.lineTo(58, 82)
  } else if (dir === 2) {
    ctx.moveTo(140, 68)
    ctx.lineTo(92, 68)
  } else if (dir === 4) {
    ctx.moveTo(82, 140)
    ctx.lineTo(82, 92)
  } else {
    ctx.moveTo(68, 10)
    ctx.lineTo(68, 58)
  }
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(dir === 6 ? 58 : dir === 2 ? 92 : dir === 4 ? 82 : 68, dir === 6 ? 82 : dir === 2 ? 68 : dir === 4 ? 92 : 58, 4, 0, Math.PI * 2)
  ctx.fill()
}

onMounted(draw)
watch(() => props.movements, draw, { deep: true })
</script>

<template>
  <div class="movement">
    <canvas ref="canvasRef" width="150" height="150" aria-label="阶段释放方向图" />
    <div class="labels">
      {{ movements.map((m) => m.label || m.movement_key || m.movementKey || '未知转向').join('、') }}
    </div>
  </div>
</template>

<style scoped>
.movement {
  display: grid;
  gap: 6px;
  justify-items: center;
}
canvas {
  width: 100%;
  max-width: 150px;
  border-radius: 6px;
  background: #08394a;
}
.labels {
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.35;
  text-align: center;
}
</style>

/** Corridor green-wave schematic + mini space-time diagram. */

import type { CorridorContext, CorridorNode } from '../types/evidence'

function escapeXml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function shortName(name: string, max = 8): string {
  const t = name.replace(/路口$/, '').trim()
  return t.length > max ? `${t.slice(0, max - 1)}…` : t
}

function greenSegments(offset: number, green: number, cycle: number): Array<[number, number]> {
  const C = cycle
  const o = ((offset % C) + C) % C
  const g = Math.min(green, C)
  if (o + g <= C) return [[o, o + g]]
  return [
    [o, C],
    [0, o + g - C],
  ]
}

export function renderCorridorWaveSvg(
  corridor: CorridorContext,
  opts: { width?: number; height?: number } = {},
): string {
  const width = opts.width ?? 300
  const height = opts.height ?? 128
  const nodes = corridor.corridor_nodes ?? []
  const cycle = Math.max(corridor.coord_cycle_sec ?? 100, 60)
  const green = Math.min(cycle * 0.42, cycle - 10)
  const nodeCount = Math.max(nodes.length, corridor.corridor_inter_count ?? 0)

  if (!nodeCount) {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><text x="50%" y="50%" text-anchor="middle" fill="rgba(150,180,210,0.6)" font-size="10">无协调走廊拓扑</text></svg>`
  }

  const displayNodes: CorridorNode[] =
    nodes.length > 0
      ? nodes
      : Array.from({ length: nodeCount }, (_, i) => ({
          seq: i + 1,
          inter_name: `节点${i + 1}`,
          is_current: corridor.inter_position === i + 1,
        }))

  const topH = 38
  const stTop = topH + 8
  const stH = height - stTop - 6
  const left = 8
  const chartW = width - 16
  const step = chartW / Math.max(displayNodes.length - 1, 1)

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">`
  svg += `<rect width="100%" height="100%" fill="rgba(0,12,28,0.3)" rx="2"/>`

  // Topology chain
  displayNodes.forEach((node, i) => {
    const x = left + i * step
    const cy = 18
    const isCur = node.is_current
    const r = isCur ? 7 : 5
    svg += `<circle cx="${x}" cy="${cy}" r="${r}" fill="${isCur ? '#00e5ff' : 'rgba(0,180,220,0.35)'}" stroke="${isCur ? '#fff' : 'rgba(0,229,255,0.5)'}" stroke-width="1"/>`
    svg += `<text x="${x}" y="${cy + 3}" text-anchor="middle" fill="${isCur ? '#001018' : 'rgba(200,230,255,0.9)'}" font-size="7" font-weight="700">${node.seq ?? i + 1}</text>`
    svg += `<text x="${x}" y="${cy + 16}" text-anchor="middle" fill="${isCur ? '#00e5ff' : 'rgba(180,210,240,0.75)'}" font-size="7">${escapeXml(shortName(node.inter_name ?? ''))}</text>`
    if (i < displayNodes.length - 1) {
      const nx = left + (i + 1) * step
      svg += `<line x1="${x + r}" y1="${cy}" x2="${nx - r}" y2="${cy}" stroke="rgba(0,229,255,0.35)" stroke-width="1.5"/>`
      if (corridor.green_wave_break_risk) {
        svg += `<text x="${(x + nx) / 2}" y="${cy - 6}" text-anchor="middle" fill="#ff8a65" font-size="6">停车偏高</text>`
      }
    }
  })

  // Space-time (2 cycles)
  const cyclesShow = 2
  const timeScale = (stH - 12) / (cycle * cyclesShow)
  for (let k = 0; k <= cyclesShow; k++) {
    const y = stTop + k * cycle * timeScale
    svg += `<line x1="${left}" y1="${y}" x2="${left + chartW}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-width="0.5"/>`
  }

  const offsets = displayNodes.map((_, i) => (i * (cycle / Math.max(displayNodes.length, 1)) * 0.35) % cycle)

  displayNodes.forEach((node, i) => {
    const x = left + i * step - 3
    const offset = offsets[i] ?? 0
    const segs = greenSegments(offset, green, cycle)
    for (let k = 0; k < cyclesShow; k++) {
      for (const [a, b] of segs) {
        const y1 = stTop + (a + k * cycle) * timeScale
        const y2 = stTop + (b + k * cycle) * timeScale
        svg += `<rect x="${x}" y="${y1}" width="6" height="${Math.max(y2 - y1, 1)}" fill="${node.is_current ? '#00c853' : 'rgba(0,200,83,0.55)'}" rx="1"/>`
      }
    }
    svg += `<line x1="${x + 3}" y1="${stTop}" x2="${x + 3}" y2="${stTop + cycle * cyclesShow * timeScale}" stroke="rgba(0,229,255,0.2)" stroke-width="0.5"/>`
  })

  // Forward green bands between adjacent nodes
  for (let i = 0; i < displayNodes.length - 1; i++) {
    const x1 = left + i * step
    const x2 = left + (i + 1) * step
    const travel = cycle * 0.08
    const la = offsets[i] ?? 0
    const ra = (offsets[i + 1] ?? 0) - travel
    const lb = la + green
    const rb = ra + green
    const overlapStart = Math.max(la, ra)
    const overlapEnd = Math.min(lb, rb)
    if (overlapEnd > overlapStart) {
      const y1 = stTop + overlapStart * timeScale
      const y2 = stTop + overlapEnd * timeScale
      svg += `<polygon points="${x1 + 6},${y1} ${x2},${y1 + travel * timeScale} ${x2},${y2 + travel * timeScale} ${x1 + 6},${y2}" fill="rgba(0,230,118,0.18)" stroke="rgba(0,230,118,0.45)" stroke-width="0.6"/>`
    }
  }

  const pos = corridor.inter_position
  const total = corridor.corridor_inter_count
  svg += `<text x="${left}" y="${height - 2}" fill="rgba(150,180,210,0.55)" font-size="7">绿波时距示意 · 节点 ${pos ?? '?'}/${total ?? '?'} · 周期 ${cycle.toFixed(0)}s</text>`
  svg += '</svg>'
  return svg
}

/** Ring-Barrier compact SVG renderer (adapted from signal ring-barrier-viewer). */

export interface RingDiagramRecord {
  cycle_len: number
  ring_count?: number
  pattern?: string
  green_times: number[]
  yellow_times: number[]
  red_times: number[]
  rings: Array<{ phases: number[]; barriers: number[] }>
  channel_info?: Array<Array<[number, number]>>
  follow_phase_info?: unknown[]
  offset_sec?: number | null
}

const DIRECTION_NAME: Record<number, string> = {
  0: '北', 1: '东北', 2: '东', 3: '东南', 4: '南', 5: '西南', 6: '西', 7: '西北',
}
const TURN_NAME: Record<number, string> = {
  11: '直行', 12: '左转', 13: '右转', 31: '掉头', 21: '直左', 22: '直右',
}

function movementText(m: [number, number]): string {
  const dir = DIRECTION_NAME[m[0]] ?? `D${m[0]}`
  const turn = TURN_NAME[m[1]] ?? `T${m[1]}`
  return `${dir}${turn}`
}

function escapeXml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function phaseMatchesDeficit(
  phaseNo: number,
  record: RingDiagramRecord,
  deficitLabels: string[],
): boolean {
  if (!deficitLabels.length) return false
  const channels = record.channel_info?.[phaseNo - 1] ?? []
  const text = channels.map(movementText).join('')
  return deficitLabels.some((lbl) => text.includes(lbl) || lbl.includes(text))
}

export function renderTimingRingSvg(
  record: RingDiagramRecord,
  opts: { width?: number; height?: number; deficitLabels?: string[] } = {},
): string {
  const width = opts.width ?? 280
  const height = opts.height ?? 118
  const deficitLabels = opts.deficitLabels ?? []
  const cycleLen = Math.max(record.cycle_len || 1, 1)
  const rings = record.rings ?? []
  const left = 36
  const chartWidth = width - left - 8
  const scale = chartWidth / cycleLen
  const ringPitch = Math.min(28, Math.floor((height - 28) / Math.max(rings.length, 1)))
  const barH = 14
  const ringTop = 18

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">`
  svg += `<rect width="100%" height="100%" fill="rgba(0,12,28,0.3)" rx="2"/>`
  svg += `<text x="${width / 2}" y="11" text-anchor="middle" fill="rgba(0,229,255,0.75)" font-size="9" font-family="system-ui,sans-serif">周期 ${cycleLen}s · ${rings.length}环</text>`

  rings.forEach((ring, ringIdx) => {
    const y = ringTop + ringIdx * ringPitch
    svg += `<text x="${left - 4}" y="${y + barH / 2 + 3}" text-anchor="end" fill="rgba(200,230,255,0.7)" font-size="8" font-weight="600">R${ringIdx + 1}</text>`
    let xPos = 0
    ;(ring.phases ?? []).forEach((phaseNoRaw, phaseIdx) => {
      const phaseNo = Number(phaseNoRaw)
      const idx = phaseNo - 1
      const g = record.green_times[idx] ?? 0
      const yy = record.yellow_times[idx] ?? 0
      const r = record.red_times[idx] ?? 0
      const total = g + yy + r
      if (total <= 0) return
      const x = left + xPos * scale
      const deficit = phaseMatchesDeficit(phaseNo, record, deficitLabels)
      const stroke = deficit ? '#ff6b6b' : 'rgba(17,24,39,0.6)'
      const sw = deficit ? 1.4 : 0.5
      if (g > 0) {
        svg += `<rect x="${x}" y="${y}" width="${g * scale}" height="${barH}" fill="${deficit ? '#c62828' : '#2e7d32'}" stroke="${stroke}" stroke-width="${sw}"/>`
      }
      if (yy > 0) {
        svg += `<rect x="${x + g * scale}" y="${y}" width="${yy * scale}" height="${barH}" fill="#f9a825" stroke="${stroke}" stroke-width="${sw}"/>`
      }
      if (r > 0) {
        svg += `<rect x="${x + (g + yy) * scale}" y="${y}" width="${r * scale}" height="${barH}" fill="#c62828" opacity="0.85" stroke="${stroke}" stroke-width="${sw}"/>`
      }
      const label = (record.channel_info?.[idx] ?? []).map(movementText).join('/').slice(0, 6)
      if (label && g * scale >= 14) {
        svg += `<text x="${x + 2}" y="${y - 2}" fill="${deficit ? '#ff8a80' : 'rgba(0,229,255,0.65)'}" font-size="7">${escapeXml(label)}</text>`
      }
      xPos += total
      if ((ring.barriers ?? []).map(Number).includes(phaseIdx)) {
        const bx = left + xPos * scale
        svg += `<line x1="${bx}" y1="${ringTop - 2}" x2="${bx}" y2="${ringTop + rings.length * ringPitch}" stroke="rgba(255,255,255,0.35)" stroke-width="1" stroke-dasharray="3 2"/>`
      }
    })
  })

  svg += `<text x="${left}" y="${height - 4}" fill="rgba(150,180,210,0.55)" font-size="7">绿/黄/红 · 红框为最小绿不足转向</text>`
  svg += '</svg>'
  return svg
}

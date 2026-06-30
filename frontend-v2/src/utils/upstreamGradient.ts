/** 上游溯源蔓延渐变：近端白/黄 → 远端绿（对齐产品参考截图）。 */
export const UPSTREAM_GRADIENT_STOPS = [
  '#ffffff',
  '#fff4a8',
  '#ffc857',
  '#ff9a3c',
  '#7ee081',
  '#00e676',
] as const

export const UPSTREAM_SPREAD_SEGMENT_COUNT = 14

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

function rgbToHex(r: number, g: number, b: number): string {
  return `#${[r, g, b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`
}

/** 在渐变色带上按 0~1 取色。 */
export function colorAtGradientProgress(t: number): string {
  const stops = UPSTREAM_GRADIENT_STOPS
  const clamped = Math.max(0, Math.min(1, t))
  const scaled = clamped * (stops.length - 1)
  const i = Math.min(stops.length - 2, Math.floor(scaled))
  const local = scaled - i
  const [r1, g1, b1] = hexToRgb(stops[i])
  const [r2, g2, b2] = hexToRgb(stops[i + 1])
  return rgbToHex(r1 + (r2 - r1) * local, g1 + (g2 - g1) * local, b1 + (b2 - b1) * local)
}

/** 将折线均分为若干段，每段附带渐变进度中点。 */
export function segmentPathWithGradient(
  path: Array<[number, number]>,
  segmentCount = UPSTREAM_SPREAD_SEGMENT_COUNT,
): Array<{ path: Array<[number, number]>; progress: number }> {
  if (path.length < 2) return []
  const pts = path.map((p) => [p[0], p[1]] as [number, number])
  const lengths: number[] = []
  let total = 0
  for (let i = 1; i < pts.length; i++) {
    const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
    lengths.push(d)
    total += d
  }
  if (total <= 0) return []

  const cuts = Array.from({ length: segmentCount + 1 }, (_, i) => (total * i) / segmentCount)
  const segments: Array<{ path: Array<[number, number]>; progress: number }> = []

  function pointAt(dist: number): [number, number] {
    let acc = 0
    for (let i = 1; i < pts.length; i++) {
      const seg = lengths[i - 1]
      if (acc + seg >= dist || i === pts.length - 1) {
        const t = seg > 0 ? (dist - acc) / seg : 0
        return [
          pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t,
          pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t,
        ]
      }
      acc += seg
    }
    return pts[pts.length - 1]
  }

  for (let s = 0; s < segmentCount; s++) {
    const a = pointAt(cuts[s])
    const b = pointAt(cuts[s + 1])
    if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-8) continue
    segments.push({
      path: [a, b],
      progress: (s + 0.5) / segmentCount,
    })
  }
  return segments
}

export function sleepMs(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

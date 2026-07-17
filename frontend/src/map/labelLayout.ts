export interface LabelRect {
  id: string
  anchorX: number
  anchorY: number
  width: number
  height: number
  priority: number
}

export interface PlacedLabel extends LabelRect {
  dx: number
  dy: number
  hidden: boolean
}

export interface LabelViewport {
  left: number
  top: number
  right: number
  bottom: number
}

const CANDIDATES: ReadonlyArray<readonly [number, number]> = [
  [0, -42], [68, 0], [0, 42], [-68, 0],
  [68, -42], [68, 42], [-68, 42], [-68, -42],
  [0, -84], [136, 0], [0, 84], [-136, 0],
]

function bounds(label: PlacedLabel) {
  const cx = label.anchorX + label.dx
  const cy = label.anchorY + label.dy
  return {
    left: cx - label.width / 2,
    right: cx + label.width / 2,
    top: cy - label.height / 2,
    bottom: cy + label.height / 2,
  }
}

function overlaps(a: ReturnType<typeof bounds>, b: ReturnType<typeof bounds>, gap = 8) {
  return !(
    a.right + gap <= b.left ||
    a.left >= b.right + gap ||
    a.bottom + gap <= b.top ||
    a.top >= b.bottom + gap
  )
}

/** 高优先级优先，屏幕像素空间依次搜索上/右/下/左/四角；无位可放则收纳。 */
export function layoutLabels(labels: LabelRect[], viewport: LabelViewport): PlacedLabel[] {
  const placed: PlacedLabel[] = []
  const ordered = [...labels].sort((a, b) => b.priority - a.priority || a.id.localeCompare(b.id))
  for (const label of ordered) {
    let winner: PlacedLabel | null = null
    for (const [dx, dy] of CANDIDATES) {
      const candidate: PlacedLabel = { ...label, dx, dy, hidden: false }
      const r = bounds(candidate)
      const inViewport = r.left >= viewport.left && r.right <= viewport.right && r.top >= viewport.top && r.bottom <= viewport.bottom
      if (inViewport && !placed.some((other) => !other.hidden && overlaps(r, bounds(other)))) {
        winner = candidate
        break
      }
    }
    placed.push(winner ?? { ...label, dx: 0, dy: 0, hidden: true })
  }
  return placed
}

const LABEL_SELECTOR = '.map-marker, .trace-label, .topology-label, .channel-label, .us-node, .us-badge'

/** 对 AMap 已渲染文本做最终像素避让；返回被 +N 收纳的数量。 */
export function resolveRenderedLabelCollisions(root: HTMLElement): number {
  const rootRect = root.getBoundingClientRect()
  const elements = Array.from(root.querySelectorAll<HTMLElement>(LABEL_SELECTOR))
  // 标签默认带 translate 过渡。逐个清除后立即测量会读到动画中的旧矩形，
  // 造成布局器误判“未重叠”。先批量关闭过渡并强制一次同步布局，再统一测量。
  const inlineTransitions = elements.map((el) => el.style.transition)
  elements.forEach((el) => {
    el.style.transition = 'none'
    el.style.removeProperty('translate')
    el.style.removeProperty('visibility')
  })
  void root.offsetWidth
  const specs = elements.map((el, index) => {
    const rect = el.getBoundingClientRect()
    return {
      id: `label-${index}`,
      anchorX: rect.left + rect.width / 2 - rootRect.left,
      anchorY: rect.top + rect.height / 2 - rootRect.top,
      width: Math.min(Math.max(rect.width, 72), 220),
      height: Math.min(Math.max(rect.height, 28), 88),
      priority: Number(el.dataset.labelPriority ?? (elements.length - index)),
    }
  })
  const placed = layoutLabels(specs, {
    left: 12,
    top: 52,
    right: Math.max(12, rootRect.width - 12),
    bottom: Math.max(52, rootRect.height - 52),
  })
  let hidden = 0
  for (const item of placed) {
    const el = elements[Number(item.id.slice('label-'.length))]
    if (!el) continue
    if (item.hidden) {
      el.style.visibility = 'hidden'
      hidden += 1
    } else {
      el.style.translate = `${item.dx}px ${item.dy}px`
    }
  }
  void root.offsetWidth
  elements.forEach((el, index) => {
    if (inlineTransitions[index]) el.style.transition = inlineTransitions[index]
    else el.style.removeProperty('transition')
  })
  return hidden
}

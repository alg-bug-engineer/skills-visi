import { describe, expect, it } from 'vitest'
import { layoutLabels, resolveRenderedLabelCollisions } from '@/map/labelLayout'

describe('map label layout', () => {
  it('同锚点标注按优先级避让且不返回相同 offset', () => {
    const labels = [
      { id: 'high', anchorX: 200, anchorY: 160, width: 110, height: 34, priority: 100 },
      { id: 'mid', anchorX: 200, anchorY: 160, width: 110, height: 34, priority: 50 },
      { id: 'low', anchorX: 200, anchorY: 160, width: 110, height: 34, priority: 10 },
    ]
    const result = layoutLabels(labels, { left: 0, top: 0, right: 400, bottom: 320 })
    expect(result.every((item) => !item.hidden)).toBe(true)
    expect(new Set(result.map((item) => `${item.dx}:${item.dy}`)).size).toBe(3)
    expect(result[0].id).toBe('high')
  })

  it('视口无空间时收纳低优先级标注', () => {
    const labels = Array.from({ length: 20 }, (_, i) => ({ id: String(i), anchorX: 50, anchorY: 50, width: 90, height: 40, priority: 20 - i }))
    const result = layoutLabels(labels, { left: 0, top: 0, right: 100, bottom: 100 })
    expect(result.some((item) => item.hidden)).toBe(true)
  })

  it('像素终检在测量前关闭位移动画，避免读取过渡中的旧矩形', () => {
    const root = document.createElement('div')
    const labels = [document.createElement('div'), document.createElement('div')]
    labels.forEach((label) => {
      label.className = 'trace-label'
      label.style.transition = 'translate 180ms ease'
      label.style.translate = '0px -42px'
      label.getBoundingClientRect = () => {
        expect(label.style.transition).toBe('none')
        return { left: 145, right: 255, top: 143, bottom: 177, width: 110, height: 34, x: 145, y: 143, toJSON: () => ({}) }
      }
      root.appendChild(label)
    })
    root.getBoundingClientRect = () => ({ left: 0, right: 400, top: 0, bottom: 320, width: 400, height: 320, x: 0, y: 0, toJSON: () => ({}) })
    Object.defineProperty(root, 'offsetWidth', { configurable: true, value: 400 })

    expect(resolveRenderedLabelCollisions(root)).toBe(0)
    expect(new Set(labels.map((label) => label.style.translate)).size).toBe(2)
    expect(labels.every((label) => label.style.transition === 'translate 180ms ease')).toBe(true)
  })
})

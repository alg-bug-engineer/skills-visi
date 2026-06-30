import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DirSaturationRing from './DirSaturationRing.vue'

const PROFILES = [
  { dir8_code: 0, turn_saturation_max: 0.95 }, // 北 高
  { dir8_code: 2, turn_saturation_max: 0.7 }, // 东 中
  { dir8_code: 4, turn_saturation_max: 0.4 }, // 南 低
  // 6 西 缺省 → unknown
]

describe('DirSaturationRing', () => {
  it('renders four directional segments', () => {
    const wrapper = mount(DirSaturationRing, { props: { profiles: PROFILES } })
    expect(wrapper.findAll('.ring-seg')).toHaveLength(4)
  })

  it('colors each segment by approach saturation', () => {
    const wrapper = mount(DirSaturationRing, { props: { profiles: PROFILES } })
    const byDir = (d: number) =>
      wrapper.find(`.ring-seg[data-dir8="${d}"]`).attributes('stroke')
    expect(byDir(0)).toBe('#ff6b4a') // high
    expect(byDir(2)).toBe('#ffaa44') // medium
    expect(byDir(4)).toBe('#6dffb5') // low
    expect(byDir(6)).toBe('#3a4a66') // unknown
  })
})

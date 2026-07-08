import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ExperienceAbsorptionPanel from '@/panels/ExperienceAbsorptionPanel.vue'
import { useExperienceAbsorption } from '@/composables/useExperienceAbsorption'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const result = fixture as unknown as SkillSolidificationResult

function terminalState() {
  const { state, start } = useExperienceAbsorption()
  start(result.absorption, { instant: true })
  return state
}

describe('ExperienceAbsorptionPanel', () => {
  it('renders stage labels, evidence chip values and value table rows', () => {
    const state = terminalState()
    const wrapper = mount(ExperienceAbsorptionPanel, { props: { state } })
    const text = wrapper.text()

    // 阶段标签
    expect(text).toContain('回顾本轮约束')
    // 证据 chip 值（数字与字符串）
    expect(text).toContain('经十路与转山西路路口')
    // 价值前后对照维度
    const table = wrapper.find('[data-testid="absorption-value-table"]')
    expect(table.exists()).toBe(true)
    expect(table.text()).toContain('复用方式')
    expect(table.text()).toContain('技能库按标签自动命中')
  })

  it('renders one trace line per stage', () => {
    const state = terminalState()
    const wrapper = mount(ExperienceAbsorptionPanel, { props: { state } })
    expect(wrapper.findAll('.trace__item')).toHaveLength(result.absorption.stages.length)
  })
})

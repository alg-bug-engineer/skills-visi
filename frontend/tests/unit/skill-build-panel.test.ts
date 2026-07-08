import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SkillBuildPanel from '@/panels/SkillBuildPanel.vue'
import { useSkillBuildProcess, type SkillBuildMeta } from '@/composables/useSkillBuildProcess'
import type { SkillSolidificationResult } from '@/api/types'
import fixture from '@/mock/skill_solidify_fixture.json'

const result = fixture as unknown as SkillSolidificationResult

function metaFrom(r: SkillSolidificationResult): SkillBuildMeta {
  return {
    skillId: r.skill_id,
    skillDir: r.skill_dir,
    downloadUrl: r.download_url,
    intersection: r.intersection ?? '',
    timePeriodLabel: r.time_period_label ?? '',
    action: r.action,
  }
}

function completedState() {
  const { state, start } = useSkillBuildProcess()
  start(result.build, metaFrom(result), { instant: true })
  return state
}

describe('SkillBuildPanel', () => {
  it('renders file tree names, 100% progress and the completed footer', () => {
    const state = completedState()
    const wrapper = mount(SkillBuildPanel, { props: { state } })
    const text = wrapper.text()

    // 文件树名
    expect(text).toContain('SKILL.md')
    expect(text).toContain('fetch_traffic_data.sql')
    // 进度 100
    expect(wrapper.find('[data-testid="build-progress"]').text()).toBe('100%')
    // 完成态页脚
    expect(wrapper.find('[data-testid="build-footer"]').exists()).toBe(true)
    expect(text).toContain('新建固化')
  })

  it('renders download link with the exact fixture download_url (no re-prefix)', () => {
    const state = completedState()
    const wrapper = mount(SkillBuildPanel, { props: { state } })
    const anchor = wrapper.find('[data-testid="skill-download"]')
    expect(anchor.exists()).toBe(true)
    expect(anchor.attributes('href')).toBe(result.download_url)
    expect(anchor.text()).toContain('下载技能包')
  })

  it('emits finish when 返回主页 clicked', async () => {
    const state = completedState()
    const wrapper = mount(SkillBuildPanel, { props: { state } })
    const btn = wrapper.find('[data-testid="solidify-finish"]')
    expect(btn.text()).toContain('返回主页')
    await btn.trigger('click')
    expect(wrapper.emitted('finish')).toBeTruthy()
  })
})

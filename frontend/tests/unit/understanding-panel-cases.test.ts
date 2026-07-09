import { describe, expect, it, beforeEach } from 'vitest'
import { nextTick } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import UnderstandingPanel from '@/panels/UnderstandingPanel.vue'
import { usePresentationStore } from '@/stores/presentation'
import expertKnowledge from '@/data/expertKnowledge.json'
import type { RunResponse } from '@/api/types'

/** 构造仅含成因阶段（含相似案例卡）的快照，用于点亮「路口案例」的本轮检索结果。 */
function snapWithCases(): RunResponse {
  return {
    trace_id: 't',
    completed: null,
    pipeline_complete: false,
    diagnosis_ticket: null,
    phases: {
      intent: {},
      cause: {
        case_cards: {
          cards: [
            {
              case_id: 'CASE_777',
              title: '文化路溢出治理',
              similarity: 0.91,
              action: '双向绿波 + 上游调控',
              outcome: '排队下降 40%',
              lesson: '优先消散下游',
            },
          ],
        },
      },
    } as unknown as RunResponse['phases'],
    plan: null,
    phase_results: [],
  }
}

/** 避免 onMounted 触发真实网络：标记沉淀已加载。 */
function markPrecipLoaded(s: ReturnType<typeof usePresentationStore>) {
  s.precip.loaded = true
}

describe('沉淀面板 · 案例库（行业/路口）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('行业案例子标签渲染全部 19 个场景条目', async () => {
    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-industry"]').trigger('click')

    const scenes = wrapper.findAll('[data-testid="industry-scene"]')
    expect(scenes.length).toBe((expertKnowledge as unknown[]).length)
    expect(scenes.length).toBe(19)
  })

  it('行业案例本地过滤场景列表（匹配数少于全部）', async () => {
    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-industry"]').trigger('click')

    const input = wrapper.find('[data-testid="industry-search"]')
    await input.setValue('货运通道')

    const scenes = wrapper.findAll('[data-testid="industry-scene"]')
    expect(scenes.length).toBeGreaterThanOrEqual(1)
    expect(scenes.length).toBeLessThan(19)
    expect(wrapper.text()).toContain('货运通道关键节点')
  })

  it('代表案例锚点唯一，采用 industry-case-<sceneId>-<caseId> 格式', async () => {
    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-industry"]').trigger('click')
    for (const head of wrapper.findAll('.scene-head')) {
      await head.trigger('click')
    }

    const anchors = wrapper.findAll('li.rep-case[id]')
    expect(anchors.length).toBeGreaterThan(0)
    const ids = anchors.map((a) => a.attributes('id') as string)
    expect(new Set(ids).size).toBe(ids.length)
    for (const id of ids) {
      expect(id).toMatch(/^industry-case-.+-.+$/)
    }
  })

  it('路口案例呈现本轮检索到的相似案例并展示 case_id', async () => {
    const s = usePresentationStore()
    markPrecipLoaded(s)
    s.applySnapshot(snapWithCases())

    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-intersection"]').trigger('click')

    const items = wrapper.findAll('[data-testid="inter-case"]')
    expect(items.length).toBe(1)
    const text = wrapper.text()
    expect(text).toContain('文化路溢出治理')
    expect(text).toContain('CASE_777')
    expect(wrapper.find('#inter-case-CASE_777').exists()).toBe(true)
  })

  it('路口案例无沉淀时显示空态提示（非「待检索」门控）', async () => {
    const s = usePresentationStore()
    markPrecipLoaded(s)

    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-intersection"]').trigger('click')
    await nextTick()

    expect(wrapper.findAll('[data-testid="inter-case"]').length).toBe(0)
    expect(wrapper.text()).toContain('暂无路口沉淀案例')
  })

  it('路口案例：英文 plan_id 与逐字 spatial_structure 展示为中文', async () => {
    const s = usePresentationStore()
    s.precip.loaded = true
    s.precip.interCases = [
      {
        case_id: 'recommended_df0137044e4843db_downstream_protection',
        category: 'recommended',
        title: 'downstream_protection',
        plan_id: 'downstream_protection',
        inter_id: 'INT_B',
        intersection_name: '解放东路与奥体中路路口',
        time_period: 'morning_peak',
        tags: {
          problem_type: 'queue_spillover',
          spatial_structure: '解, 放, 东, 路, 与, 奥, 体, 中, 路, 路, 口, 南, 向, 北, 直, 行, 方, 向',
        },
        lesson: '历史接受方案',
      },
    ]

    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-intersection"]').trigger('click')

    const text = wrapper.text()
    expect(text).toContain('下游保护方案')
    expect(text).not.toContain('downstream_protection')
    expect(text).toContain('解放东路与奥体中路路口南向北直行方向')
    expect(text).not.toMatch(/解,\s*放,\s*东/)
  })

  it('路口案例：含固化技能的确认案例展示「下载技能包」入口', async () => {
    const s = usePresentationStore()
    s.precip.loaded = true
    s.precip.interCases = [
      {
        case_id: 'recommended_t1_plan_dp',
        category: 'recommended',
        title: '干线联控',
        inter_id: 'INT_A',
        intersection_name: '经十路与转山西路路口',
        time_period: '早高峰',
        tags: { strategy_applied: '干线联控', primary_cause: '下游受阻' },
        skill: {
          skill_id: 'skill-INT_A-早高峰',
          download_url: '/api/v1/agent/skills/skill-INT_A-早高峰/download',
        },
      },
    ]

    const wrapper = mount(UnderstandingPanel)
    await wrapper.find('[data-testid="case-library-tab"]').trigger('click')
    await wrapper.find('[data-testid="case-subtab-intersection"]').trigger('click')

    const dl = wrapper.find('[data-testid="skill-download"]')
    expect(dl.exists()).toBe(true)
    expect(dl.attributes('href')).toContain('/api/v1/agent/skills/skill-INT_A-早高峰/download')
    // 结构化标签 chips 呈现路口与策略
    expect(wrapper.text()).toContain('经十路与转山西路路口')
  })

  it('监听 open-case-library 事件 → 切到路口案例并定位', async () => {
    ;(Element.prototype as unknown as { scrollIntoView?: () => void }).scrollIntoView = () => {}
    const s = usePresentationStore()
    markPrecipLoaded(s)
    s.applySnapshot(snapWithCases())

    const wrapper = mount(UnderstandingPanel, { attachTo: document.body })
    window.dispatchEvent(
      new CustomEvent('open-case-library', {
        detail: { tab: 'intersection', refId: 'inter-case-CASE_777' },
      }),
    )
    await nextTick()
    await nextTick()

    expect(wrapper.find('[data-testid="case-library-tab"]').classes()).toContain('active')
    expect(wrapper.find('[data-testid="case-subtab-intersection"]').classes()).toContain('active')
    expect(wrapper.find('#inter-case-CASE_777').exists()).toBe(true)
    wrapper.unmount()
  })

  it('监听 open-case-library 事件（行业场景）→ 展开对应场景并切标签', async () => {
    ;(Element.prototype as unknown as { scrollIntoView?: () => void }).scrollIntoView = () => {}
    const wrapper = mount(UnderstandingPanel, { attachTo: document.body })
    window.dispatchEvent(
      new CustomEvent('open-case-library', {
        detail: {
          tab: 'industry',
          refId: 'industry-scene-general_intersection',
          sceneId: 'general_intersection',
        },
      }),
    )
    await nextTick()
    await nextTick()

    expect(wrapper.find('[data-testid="case-subtab-industry"]').classes()).toContain('active')
    expect(wrapper.find('#industry-scene-general_intersection .scene-body').exists()).toBe(true)
    wrapper.unmount()
  })
})

describe('沉淀面板 · 经验库（全量历史 + 本轮新吸收）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('认知经验全量呈现并渲染结构化标签 chips', async () => {
    const s = usePresentationStore()
    s.precip.loaded = true
    s.precip.experiences = {
      cognitive: [
        {
          record_id: 'ue_1',
          experience_type: 'cognitive',
          content: '早高峰东向西直行排队溢出',
          intersection_name: '经十路与转山西路路口',
          tags: {
            problem_type: '排队溢出',
            time_period: '早高峰',
            direction: '东向西',
            movement: '直行',
          },
        },
      ],
      diagnostic: [],
      solution: [],
    }

    const wrapper = mount(UnderstandingPanel)
    // 默认即经验库 + 认知子标签
    const items = wrapper.findAll('[data-testid="exp-item"]')
    expect(items.length).toBe(1)
    const text = wrapper.text()
    expect(text).toContain('早高峰东向西直行排队溢出')
    expect(text).toContain('经十路与转山西路路口')
    expect(text).toContain('排队溢出')
    // 全量呈现不依赖本轮推演 → 无「待检索」门控
    expect(text).not.toContain('待检索')
  })

  it('本轮新吸收经验置顶并标记 fresh 徽标', async () => {
    const s = usePresentationStore()
    s.precip.loaded = true
    s.precip.experiences = {
      cognitive: [
        { record_id: 'old', experience_type: 'cognitive', content: '历史沉淀经验条目' },
      ],
      diagnostic: [],
      solution: [],
    }
    // 本轮推演从 intent 阶段吸收一条新认知经验
    s.applySnapshot({
      trace_id: 't2',
      completed: null,
      pipeline_complete: false,
      diagnosis_ticket: null,
      phases: {
        intent: {
          user_experiences: [
            { experience_type: 'cognitive', content: '本轮新吸收经验条目' },
          ],
        },
      } as unknown as RunResponse['phases'],
      plan: null,
      phase_results: [],
    })

    const wrapper = mount(UnderstandingPanel)
    const items = wrapper.findAll('[data-testid="exp-item"]')
    expect(items.length).toBe(2)
    // 新吸收置顶
    expect(items[0].text()).toContain('本轮新吸收经验条目')
    expect(items[0].find('[data-testid="exp-fresh"]').exists()).toBe(true)
    expect(items[0].classes()).toContain('fresh')
  })
})

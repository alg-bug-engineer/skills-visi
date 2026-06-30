import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { UpstreamTreeView } from '../../types/map'
import UpstreamGovernanceCard from './UpstreamGovernanceCard.vue'

const TREES: UpstreamTreeView[] = [
  {
    tree_id: 'N',
    approach: '北进口',
    nodes: [
      { id: 'T', inter_id: 'T', name: '目标', role: 'target', hop: 0 },
      { id: 'U1', inter_id: 'U1', name: '上游枢纽', role: 'upstream', hop: 1, decision: '继续上溯' },
      {
        id: 'A', inter_id: 'A', name: 'A路口', role: 'governance', hop: 2, decision: '治理落点',
        approach_profiles: [{ dir8_code: 0, turn_saturation_max: 0.7 }],
      },
    ],
    edges: [],
  },
  {
    tree_id: 'E',
    approach: '东进口',
    nodes: [
      { id: 'T', inter_id: 'T', name: '目标', role: 'target', hop: 0 },
      { id: 'U2', inter_id: 'U2', name: '上游2', role: 'upstream', hop: 1, decision: '继续上溯' },
    ],
    edges: [],
  },
]

describe('UpstreamGovernanceCard', () => {
  it('renders one tab per tree (approach)', () => {
    const wrapper = mount(UpstreamGovernanceCard, { props: { trees: TREES } })
    const tabs = wrapper.findAll('[data-testid="upstream-tab"]')
    expect(tabs).toHaveLength(2)
    expect(tabs[0].text()).toBe('北进口')
  })

  it('marks governance point with a star', () => {
    const wrapper = mount(UpstreamGovernanceCard, { props: { trees: TREES, activeTree: 'N' } })
    const gov = wrapper.find('[data-testid="upstream-node"][data-governance="1"]')
    expect(gov.exists()).toBe(true)
    expect(gov.find('[data-testid="governance-star"]').exists()).toBe(true)
  })

  it('collapses hop2 rows when showHop2 is false', () => {
    const collapsed = mount(UpstreamGovernanceCard, {
      props: { trees: TREES, activeTree: 'N', showHop2: false },
    })
    expect(collapsed.findAll('[data-testid="upstream-node"]')).toHaveLength(1) // only hop1

    const expanded = mount(UpstreamGovernanceCard, {
      props: { trees: TREES, activeTree: 'N', showHop2: true },
    })
    expect(expanded.findAll('[data-testid="upstream-node"]')).toHaveLength(2) // hop1 + hop2
  })

  it('emits focus-node when a node is clicked', async () => {
    const wrapper = mount(UpstreamGovernanceCard, { props: { trees: TREES, activeTree: 'N' } })
    await wrapper.find('[data-testid="upstream-node"][data-governance="1"]').trigger('click')
    expect(wrapper.emitted('focus-node')?.[0]).toEqual(['A'])
  })
})

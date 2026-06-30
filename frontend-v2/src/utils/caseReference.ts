import type { IndustryCaseScenario } from '../types/experience'

export type CaseSubTab = 'industry' | 'intersection'

export interface ParsedCaseRef {
  subTab: CaseSubTab
  /** industry → scenario_id；intersection → inter_id */
  key: string
}

/** 解析建议溯源依据/锚点 id：`industry:<scenario_id>` 或 `intersection:<inter_id>`。 */
export function parseCaseReferenceId(id: string | null | undefined): ParsedCaseRef | null {
  if (!id) return null
  const [head, ...rest] = id.split(':')
  const key = rest.join(':').trim()
  if (!key) return null
  if (head === 'industry') return { subTab: 'industry', key }
  if (head === 'intersection') return { subTab: 'intersection', key }
  return null
}

/** 客户端按关键词过滤行业案例（场景名/描述/典型问题）。 */
export function filterIndustryCases(
  scenarios: IndustryCaseScenario[],
  query: string,
): IndustryCaseScenario[] {
  const needle = query.trim()
  if (!needle) return scenarios
  return scenarios.filter((sc) => {
    const blob =
      sc.scenario_name +
      (sc.description ?? '') +
      sc.problems.map((p) => p.problem).join('')
    return blob.includes(needle)
  })
}

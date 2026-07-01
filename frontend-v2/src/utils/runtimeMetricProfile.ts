/** 多类型叠加时的主问题优先级（安全 > 扩散 > 空放 > 拥堵）。 */
export const PROBLEM_TYPE_PRIORITY = ['conflict', 'spillback', 'empty_green', 'congestion'] as const

export type ProblemType = (typeof PROBLEM_TYPE_PRIORITY)[number]

export function resolvePrimaryProblemType(problemTypes: string[] | undefined | null): ProblemType {
  if (!problemTypes?.length) return 'congestion'
  for (const pt of PROBLEM_TYPE_PRIORITY) {
    if (problemTypes.includes(pt)) return pt
  }
  return 'congestion'
}

export type RuntimeMetricEmphasis = 'primary' | 'secondary' | 'background'

export interface ServerRuntimeMetricItem {
  key: string
  id: string
  label: string
  value: string
  emphasis?: RuntimeMetricEmphasis
  severity?: 'high' | 'medium' | 'low'
}

export interface RuntimeMetricProfile {
  primary: string[]
  secondary: string[]
  background: string[]
  hidden: string[]
}

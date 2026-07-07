const REPLACEMENTS: Array<[RegExp, string]> = [
  [/校验问题：?\s*/g, '核验项：'],
  [/加绿以后，车有没有地方去？/g, '下游承接空间是否充足'],
  [/车有没有地方去/g, '下游承接空间是否充足'],
  [/相位差匹配：?\s*pg\b/gi, '协调数据：真实信控数据'],
  [/\bPG\s*真源\b/g, '真实信控数据'],
  [/\bpg\b/gi, '真实信控数据'],
  [/下游接不住/g, '下游承接不足'],
  [/接不住/g, '承接不足'],
  [/硬约束/g, '红线'],
  [/护栏/g, '安全校验'],
  [/target_green_delta\s*:\s*/g, '目标方向绿灯调整 '],
  [/\bvs\b/gi, '与'],
  [/智能体/g, '系统'],
]

export function productCopy(input: string | null | undefined): string {
  if (!input) return ''
  return REPLACEMENTS.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), input)
}

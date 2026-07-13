import { labelAny } from '@/labels/enums'

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
  [/\bcorridor\b/gi, '干线'],
  [/\bdownstream\s+check\b/gi, '下游通行核查'],
  [/\bdata\s+validation\b/gi, '数据质量校验'],
  [/\bdownstream\s+validation\b/gi, '下游通行校验'],
  [/\bdata\s+quality\s+check\b/gi, '数据质量核查'],
  [/\bplan\s+diagnostic\b/gi, '方案诊断'],
  [/\bdiagnostic\s+data\b/gi, '诊断数据'],
  [/\bdata\s+cleaning\b/gi, '数据清洗'],
  [/\bdetection\s+data\b/gi, '检测数据'],
  [/\bdiagnostic\b/gi, '诊断'],
  [/\bvalidation\b/gi, '校验'],
  [/\bdetection\b/gi, '检测'],
  [/\bcleaning\b/gi, '清洗'],
]

const SNAKE_TOKEN = /\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/gi

/** 将文案中的 snake_case 枚举编码替换为中文标签。 */
function translateEnumTokens(text: string): string {
  const trimmed = text.trim()
  if (/^[a-z][a-z0-9_]*$/i.test(trimmed) && trimmed.includes('_')) {
    return labelAny(trimmed)
  }
  if (!SNAKE_TOKEN.test(text)) return text
  return text.replace(SNAKE_TOKEN, (token) => labelAny(token))
}

export function productCopy(input: string | null | undefined): string {
  if (!input) return ''
  const base = REPLACEMENTS.reduce((text, [pattern, replacement]) => text.replace(pattern, replacement), input)
  return translateEnumTokens(base)
}

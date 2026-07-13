import { t, directionMovement } from '@/labels/enums'
import { productCopy } from '@/utils/productCopy'
import type { DiagnosisTicket } from '@/api/types'

/** 内部方法论文案，不在工单「约束」区展示。 */
const HIDDEN_CONSTRAINT_RE = /跨周峰值|跨周均值|目标峰值日|披露峰值风险|典型单点溢流|可用流量/

/** 工单约束是否应对用户展示（过滤 NLU 解析出的内部口径说明）。 */
export function isDisplayableTicketConstraint(value: string): boolean {
  const text = value.trim()
  if (!text) return false
  return !HIDDEN_CONSTRAINT_RE.test(text)
}

function rawConstraintItems(ticket: DiagnosisTicket | null | undefined): string[] {
  const c = ticket?.constraints as unknown
  if (Array.isArray(c)) return c.filter((x): x is string => typeof x === 'string' && x.trim().length > 0)
  if (typeof c === 'string' && c.trim()) return [c.trim()]
  return []
}

/** 工单约束列表（已过滤内部方法论文案）。 */
export function ticketConstraintList(ticket: DiagnosisTicket | null | undefined): string[] {
  return rawConstraintItems(ticket).filter(isDisplayableTicketConstraint)
}

/** 工单时段展示：无具体时刻时仅显示「早高峰」等，避免出现「—（早高峰）」。 */
export function ticketTimeLabel(ticket: DiagnosisTicket | null | undefined): string {
  const period = t('period', ticket?.period)
  const range = ticket?.time_range?.trim()
  if (range) return `${range}（${period}）`
  if (period && period !== '—') return period
  return '—'
}

/** 首条用户约束（兼容字符串 / 数组，避免对字符串取 [0] 变成单字）。 */
export function ticketPrimaryConstraint(ticket: DiagnosisTicket | null | undefined): string | null {
  const first = ticketConstraintList(ticket)[0]
  if (!first) return null
  return productCopy(t('constraint', first))
}

/** 诊断对象识别旁白：路口名优先，避免「对象：路口｜路口：xxx」重复。 */
export function ticketLocationLine(ticket: DiagnosisTicket | null | undefined): string {
  const name = ticket?.intersection_name?.trim()
  if (name) return `已识别路口：${productCopy(name)}`
  return `对象类型：${t('object_type', ticket?.object_type)}`
}

export function ticketDirectionProblemLine(ticket: DiagnosisTicket | null | undefined): string {
  return `方向与问题：${directionMovement(ticket?.direction, ticket?.movement)}｜${t('problem_type', ticket?.problem_type)}`
}

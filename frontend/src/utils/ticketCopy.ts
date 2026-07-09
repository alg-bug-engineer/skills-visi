import { t, directionMovement } from '@/labels/enums'
import { productCopy } from '@/utils/productCopy'
import type { DiagnosisTicket } from '@/api/types'

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
  const c = ticket?.constraints as unknown
  if (Array.isArray(c)) {
    const first = c.find((x): x is string => typeof x === 'string' && x.trim().length > 0)
    return first ? productCopy(t('constraint', first.trim())) : null
  }
  if (typeof c === 'string' && c.trim()) return productCopy(c.trim())
  return null
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

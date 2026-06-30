import { ref } from 'vue'

export type AbsorptionKind = 'cognition' | 'diagnosis'
export type AbsorptionAction = 'inserted' | 'exists' | 'updated'
export type CognitionStatus = 'verified' | 'data_doubt'

export interface AbsorptionToastInput {
  kind: AbsorptionKind
  /** 仅认知经验：是否有数据支撑 */
  status?: CognitionStatus
  action: AbsorptionAction
  /** 标签化的经验理解 */
  tags: string[]
  /** 经验原文（标题下展示） */
  text?: string
}

export interface AbsorptionToast extends AbsorptionToastInput {
  id: number
  header: string
  footer: string
}

const FOOTER_VERB: Record<AbsorptionAction, string> = {
  inserted: '已插入',
  updated: '已更新',
  exists: '已存在',
}

/** 纯函数：由吸收结果生成 toast 文案（标题 + 入库结论）。 */
export function buildToastCopy(input: AbsorptionToastInput): { header: string; footer: string } {
  if (input.kind === 'cognition') {
    const header =
      input.status === 'verified'
        ? '已验证用户提供的路口认知经验'
        : '用户提供的路口认知经验未找到数据支撑，已记录'
    const footer = `${FOOTER_VERB[input.action]}该路口认知经验库`
    return { header, footer }
  }
  // diagnosis：可能无数据，统一为「已吸收并入库」
  const header = '已吸收用户提供的诊断经验并入库'
  const footer =
    input.action === 'exists'
      ? '该诊断经验已存在（不再插入/更新）'
      : input.action === 'updated'
        ? '已更新该路口诊断经验库'
        : '已并入该路口诊断经验库'
  return { header, footer }
}

export function useAbsorptionToasts(autoDismissMs = 6000) {
  const toasts = ref<AbsorptionToast[]>([])
  let seq = 0
  const timers = new Map<number, ReturnType<typeof setTimeout>>()

  function push(input: AbsorptionToastInput): AbsorptionToast {
    const { header, footer } = buildToastCopy(input)
    const toast: AbsorptionToast = { ...input, id: ++seq, header, footer }
    toasts.value = [...toasts.value, toast]
    if (autoDismissMs > 0) {
      timers.set(
        toast.id,
        setTimeout(() => dismiss(toast.id), autoDismissMs),
      )
    }
    return toast
  }

  function dismiss(id: number) {
    toasts.value = toasts.value.filter((t) => t.id !== id)
    const timer = timers.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.delete(id)
    }
  }

  function clear() {
    timers.forEach((t) => clearTimeout(t))
    timers.clear()
    toasts.value = []
  }

  return { toasts, push, dismiss, clear }
}

import { onUnmounted, ref } from 'vue'
import { ANALYSIS_STEP_LABELS } from '../constants'

export interface ProcessStepState {
  index: number
  label: string
  fullText: string
  displayedLength: number
  collapsed: boolean
  status: 'typing' | 'done'
}

const CHAR_MS = 22

export interface UnderstandingProcessOptions {
  /** 某一步首次出现在理解过程面板、开始展示时触发（与语音旁白对齐） */
  onStepStart?: (index: number) => void
  /** 某一步打字动画结束（本轮）时触发 */
  onStepComplete?: (index: number) => void
}

export function useUnderstandingProcess(options: UnderstandingProcessOptions = {}) {
  const steps = ref<ProcessStepState[]>([])
  let timer: ReturnType<typeof setInterval> | null = null
  const pending: Array<{ index: number; text: string; append: boolean; silent: boolean }> = []
  let busy = false

  function clearTimers() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  function reset() {
    clearTimers()
    steps.value = []
    pending.length = 0
    busy = false
  }

  function findStep(index: number) {
    return steps.value.find((s) => s.index === index)
  }

  function sortSteps() {
    steps.value.sort((a, b) => a.index - b.index)
  }

  /** 仅在新步骤出现时折叠更早的步骤，当前步骤保持展开 */
  function collapsePriorSteps(beforeIndex: number) {
    for (const step of steps.value) {
      if (step.index < beforeIndex) {
        step.collapsed = true
      }
    }
  }

  function finalizeStep(step: ProcessStepState) {
    step.displayedLength = step.fullText.length
    step.status = 'done'
    options.onStepComplete?.(step.index)
  }

  /** 切换到其他步骤前，结束仍在打字中的步骤，避免全局 timer 被清掉后卡在 typing */
  function finalizeOtherTypingSteps(activeIndex: number) {
    for (const step of steps.value) {
      if (step.index !== activeIndex && step.status === 'typing') {
        finalizeStep(step)
      }
    }
  }

  function pumpQueue() {
    if (busy || pending.length === 0) return
    const next = pending.shift()!
    runStep(next.index, next.text, next.append, next.silent)
  }

  function enqueue(index: number, text: string, append = false, silent = false) {
    const trimmed = text.trim()
    if (!trimmed) return
    pending.push({ index, text: trimmed, append, silent })
    pumpQueue()
  }

  function runStep(index: number, text: string, append: boolean, silent: boolean) {
    busy = true
    finalizeOtherTypingSteps(index)
    let step = findStep(index)

    if (step) {
      const nextText = append
        ? step.fullText
          ? `${step.fullText}\n${text}`
          : text
        : text.length > step.fullText.length
          ? text
          : step.fullText

      if (silent && step.status === 'typing') {
        step.fullText = append ? nextText : text
        busy = false
        pumpQueue()
        return
      }

      if (silent && step.status === 'done') {
        step.fullText = append ? nextText : text
        step.displayedLength = step.fullText.length
        busy = false
        pumpQueue()
        return
      }

      if (append) {
        step.fullText = nextText
      } else if (text.length > step.fullText.length) {
        step.fullText = text
      } else {
        busy = false
        pumpQueue()
        return
      }
      step.collapsed = false
      step.status = 'typing'
    } else {
      collapsePriorSteps(index)
      step = {
        index,
        label: ANALYSIS_STEP_LABELS[index] ?? `步骤 ${index + 1}`,
        fullText: text,
        displayedLength: 0,
        collapsed: false,
        status: 'typing',
      }
      steps.value.push(step)
      sortSteps()
      options.onStepStart?.(index)
    }

    clearTimers()

    timer = setInterval(() => {
      const current = findStep(index)
      if (!current) return
      if (current.displayedLength < current.fullText.length) {
        current.displayedLength += 1
        return
      }

      clearTimers()
      current.status = 'done'
      current.collapsed = false
      options.onStepComplete?.(current.index)
      busy = false
      pumpQueue()
    }, CHAR_MS)
  }

  function toggleStep(index: number) {
    const step = findStep(index)
    if (step && step.status === 'done') {
      step.collapsed = !step.collapsed
    }
  }

  onUnmounted(reset)

  function whenIdle(): Promise<void> {
    return new Promise((resolve) => {
      const tick = () => {
        if (!busy && pending.length === 0) resolve()
        else window.setTimeout(tick, 50)
      }
      tick()
    })
  }

  return { steps, enqueue, reset, toggleStep, whenIdle }
}

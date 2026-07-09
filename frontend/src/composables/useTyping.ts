import { ref, watch, onBeforeUnmount, type Ref } from 'vue'

/**
 * 打字机：顺序逐字输出多行；完成触发 onDone（→ 揭示证据卡）。
 * 支持 reduced-motion / 测试环境即时完成；支持外部暂停。
 */
export function useTyping(
  lines: Ref<string[]>,
  opts: {
    speed?: number
    onDone?: () => void
    instant?: boolean
    /** 仅当此 key 变化时重启（避免同 act 内 lines 引用变化重复打字）。 */
    restartKey?: Ref<string | number>
    paused?: Ref<boolean>
  } = {},
) {
  const shown = ref<string[]>([])
  const done = ref(false)
  let timer: number | null = null
  let li = 0
  let ci = 0
  let all: string[] = []
  let ticking = false

  const clear = () => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
    ticking = false
  }

  const finishInstant = () => {
    shown.value = [...lines.value]
    done.value = true
    opts.onDone?.()
  }

  const tick = () => {
    if (opts.paused?.value) {
      timer = window.setTimeout(tick, 80)
      return
    }
    const line = all[li] ?? ''
    if (ci < line.length) {
      shown.value[li] = line.slice(0, ci + 1)
      shown.value = [...shown.value]
      ci++
      timer = window.setTimeout(tick, opts.speed ?? 18)
    } else if (li < all.length - 1) {
      li++
      ci = 0
      shown.value.push('')
      timer = window.setTimeout(tick, (opts.speed ?? 18) * 6)
    } else {
      ticking = false
      done.value = true
      opts.onDone?.()
    }
  }

  const start = () => {
    clear()
    shown.value = []
    done.value = false
    all = lines.value
    li = 0
    ci = 0
    if (!all.length) {
      done.value = true
      opts.onDone?.()
      return
    }
    if (opts.instant) {
      finishInstant()
      return
    }
    shown.value = ['']
    ticking = true
    timer = window.setTimeout(tick, opts.speed ?? 18)
  }

  if (opts.restartKey) {
    watch(opts.restartKey, start, { immediate: true })
  } else {
    watch(lines, start, { immediate: true })
  }

  if (opts.paused) {
    watch(opts.paused, (p) => {
      if (!p && ticking && timer == null) tick()
    })
  }

  onBeforeUnmount(clear)

  return { shown, done, restart: start }
}

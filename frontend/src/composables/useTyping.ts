import { ref, watch, onBeforeUnmount, type Ref } from 'vue'

/**
 * 打字机：顺序逐字输出多行；完成触发 onDone（→ 揭示证据卡）。
 * 支持 reduced-motion / 测试环境即时完成。
 */
export function useTyping(
  lines: Ref<string[]>,
  opts: { speed?: number; onDone?: () => void; instant?: boolean } = {},
) {
  const shown = ref<string[]>([])
  const done = ref(false)
  let timer: number | null = null

  const clear = () => {
    if (timer != null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const finishInstant = () => {
    shown.value = [...lines.value]
    done.value = true
    opts.onDone?.()
  }

  const start = () => {
    clear()
    shown.value = []
    done.value = false
    const all = lines.value
    if (!all.length) {
      done.value = true
      opts.onDone?.()
      return
    }
    if (opts.instant) {
      finishInstant()
      return
    }
    let li = 0
    let ci = 0
    shown.value = ['']
    const speed = opts.speed ?? 18
    const tick = () => {
      const line = all[li] ?? ''
      if (ci < line.length) {
        shown.value[li] = line.slice(0, ci + 1)
        shown.value = [...shown.value]
        ci++
        timer = window.setTimeout(tick, speed)
      } else if (li < all.length - 1) {
        li++
        ci = 0
        shown.value.push('')
        timer = window.setTimeout(tick, speed * 6)
      } else {
        done.value = true
        opts.onDone?.()
      }
    }
    timer = window.setTimeout(tick, speed)
  }

  watch(lines, start, { immediate: true })
  onBeforeUnmount(clear)

  return { shown, done, restart: start }
}

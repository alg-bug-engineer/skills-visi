import { onBeforeUnmount, onMounted } from 'vue'
import { storeToRefs } from 'pinia'
import { usePresentationStore } from '@/stores/presentation'

/** 是否在可编辑控件中（避免空格触发暂停）。 */
function isEditableTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  return el.isContentEditable
}

/**
 * 空格键切换步骤间暂停（仅阻塞幕切换，不打断当前幕打字/语音/地图）。
 * 演示已开始（currentAct≥0）且非空闲/提交态时生效；技能阶段报错不打断暂停。
 */
export function useStepPauseKeyboard() {
  const store = usePresentationStore()
  const { status, currentAct } = storeToRefs(store)

  function canPause(): boolean {
    if (status.value === 'idle' || status.value === 'submitting') return false
    return currentAct.value >= 0
  }

  function onKeydown(e: KeyboardEvent) {
    if (e.code !== 'Space' && e.key !== ' ') return
    if (!canPause()) return
    if (isEditableTarget(e.target)) return
    e.preventDefault()
    e.stopPropagation()
    store.toggleStepPause()
  }

  onMounted(() => window.addEventListener('keydown', onKeydown, true))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown, true))
}

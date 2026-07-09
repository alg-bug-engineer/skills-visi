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
 * 空格键切换步骤间暂停（仅前端推进，不影响后端 SSE）。
 * 运行态且焦点不在输入框时生效。
 */
export function useStepPauseKeyboard() {
  const store = usePresentationStore()
  const { status } = storeToRefs(store)

  function onKeydown(e: KeyboardEvent) {
    if (e.code !== 'Space' && e.key !== ' ') return
    if (status.value === 'idle' || status.value === 'error') return
    if (isEditableTarget(e.target)) return
    e.preventDefault()
    store.toggleStepPause()
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
}

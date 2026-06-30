import { ref } from 'vue'
import { fetchExperienceLibrary } from '../api/client'
import type {
  ExperienceCognitionItem,
  ExperienceDiagnosisItem,
} from '../types/experience'

/** 经验库认知/诊断两桶数据（方案桶复用技能榜）。 */
export function useExperienceLibrary() {
  const cognition = ref<ExperienceCognitionItem[]>([])
  const diagnosis = ref<ExperienceDiagnosisItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let loadedOnce = false

  async function load(interId?: string | null, force = false) {
    if (loadedOnce && !force) return
    loading.value = true
    error.value = null
    try {
      const lib = await fetchExperienceLibrary(interId)
      cognition.value = lib.cognition ?? []
      diagnosis.value = lib.diagnosis ?? []
      loadedOnce = true
    } catch (err) {
      error.value = err instanceof Error ? err.message : '加载经验库失败'
    } finally {
      loading.value = false
    }
  }

  function refresh(interId?: string | null) {
    return load(interId, true)
  }

  return { cognition, diagnosis, loading, error, load, refresh }
}

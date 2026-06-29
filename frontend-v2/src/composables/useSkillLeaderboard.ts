import { ref, watch } from 'vue'
import { fetchSkillLeaderboard } from '../api/client'
import type { SkillLeaderboardItem, SkillLeaderboardSort } from '../types/skillLeaderboard'

export function useSkillLeaderboard() {
  const items = ref<SkillLeaderboardItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const sort = ref<SkillLeaderboardSort>('hits')
  const expandedId = ref<string | null>(null)

  async function load(force = false) {
    if (loading.value && !force) return
    loading.value = true
    error.value = null
    try {
      items.value = await fetchSkillLeaderboard(sort.value)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '技能库加载失败'
      items.value = []
    } finally {
      loading.value = false
    }
  }

  function setSort(next: SkillLeaderboardSort) {
    if (sort.value === next) return
    sort.value = next
    expandedId.value = null
    void load(true)
  }

  function toggleExpanded(skillId: string) {
    expandedId.value = expandedId.value === skillId ? null : skillId
  }

  function refresh() {
    void load(true)
  }

  watch(sort, () => {
    /* load triggered explicitly in setSort */
  })

  return {
    items,
    loading,
    error,
    sort,
    expandedId,
    load,
    setSort,
    toggleExpanded,
    refresh,
  }
}

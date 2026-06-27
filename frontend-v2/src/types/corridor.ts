export interface CorridorIntersectionMetrics {
  saturation_max?: number | null
  unbalance_index?: number | null
  level_label?: string
}

export interface CorridorIntersectionItem {
  inter_id: string
  inter_name: string
  lon?: number | null
  lat?: number | null
  rank?: number | null
  has_data?: boolean
  severity?: string
  annotation?: string
  metrics?: CorridorIntersectionMetrics
}

export interface CorridorScanState {
  lineName: string
  timePeriodLabel: string
  intersections: CorridorIntersectionItem[]
  selectedInterId: string | null
  focusInterId: string | null
}

export function sortCorridorIntersections(
  items: CorridorIntersectionItem[],
): CorridorIntersectionItem[] {
  const ranked = items
    .filter((i) => i.has_data && i.rank != null)
    .sort((a, b) => Number(a.rank) - Number(b.rank))
  const noData = items.filter((i) => !i.has_data)
  return [...ranked, ...noData]
}

export function findCorridorIntersection(
  state: CorridorScanState | null | undefined,
  interId: string,
): CorridorIntersectionItem | undefined {
  return state?.intersections.find((i) => i.inter_id === interId)
}

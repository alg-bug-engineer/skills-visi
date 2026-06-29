import type { FlowTrace, FlowTraceEntry } from '../types/evidence'

export interface FlowTraceSummaryLine {
  id: string
  text: string
  entry: string
}

/** 地图左下角简要摘要：每行一个进口道结论（100 辆 / 上一路口左直右）。 */
export function buildFlowTraceSummaryLines(
  flowTrace: FlowTrace | null | undefined,
): FlowTraceSummaryLine[] {
  if (!flowTrace?.available) return []
  const entries = flowTrace.entry_traces ?? []
  return entries
    .filter((e) => e.narrative)
    .map((e) => ({
      id: `entry-${e.dir8_code}`,
      entry: e.entry,
      text: e.narrative,
    }))
}

/** 单条进口道的上游左/直/右辆数（用于地图标注）。 */
export function formatEntryMovementBrief(entry: FlowTraceEntry): string {
  const dom = entry.dominant_movement
  if (!dom) return entry.narrative
  return `${entry.entry} ← ${entry.upstream_inter_name ?? '上一路口'} ${dom.turn} ${dom.vehicles_of_100}辆/100`
}

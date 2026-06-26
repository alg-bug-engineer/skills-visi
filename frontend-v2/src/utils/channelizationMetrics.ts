import type { CognitionArm, CognitionPayload } from '../types/map'
import type { ProblemEvidence } from '../types/evidence'
import { normalizeDir } from './mapMarkers'

export type QueueColorLevel = 'high' | 'medium' | 'low' | 'none'

export interface LaneQueueSpec {
  vehicleCount: number
  saturation: number | null
  colorLevel: QueueColorLevel
}

const VEHICLE_LEN_M = 6.5
const MAX_VEHICLES = 14

const TURN_CODE: Record<string, string> = {
  '11': '直',
  '12': '左',
  '13': '右',
  '22': '调',
  '31': '直',
  '32': '左',
  '33': '右',
}

function normalizeTurn(raw: string): string {
  const t = String(raw || '').trim()
  if (TURN_CODE[t]) return TURN_CODE[t]
  if (t.includes('左')) return '左'
  if (t.includes('右')) return '右'
  if (t.includes('调') || t.includes('U')) return '调'
  if (t.includes('直')) return '直'
  return '直'
}

function parseTurns(arm: CognitionArm): string[] {
  const laneCount = arm.lane_num || arm.lanes?.length || 3
  if (arm.lanes?.length) {
    return arm.lanes.map((l) => normalizeTurn(l.turn_move))
  }
  const raw = arm.turn_move || arm.lane_info || ''
  if (!raw) return Array.from({ length: laneCount }, () => '直')
  const parts = raw.split(/[|,，]/).map((p) => normalizeTurn(p.trim()))
  if (parts.length >= laneCount) return parts.slice(0, laneCount)
  return [...parts, ...Array.from({ length: laneCount - parts.length }, () => '直')]
}

function queueFromMeters(m: number | null | undefined): number {
  if (m == null || m <= 0) return 0
  return Math.min(MAX_VEHICLES, Math.max(1, Math.round(m / VEHICLE_LEN_M)))
}

function queueFromSaturation(sat: number | null | undefined): number {
  if (sat == null || sat <= 0) return 0
  return Math.min(MAX_VEHICLES, Math.max(1, Math.round(sat * 8)))
}

function colorLevelForSat(sat: number | null | undefined): QueueColorLevel {
  if (sat == null || sat <= 0) return 'none'
  if (sat >= 0.85) return 'high'
  if (sat >= 0.65) return 'medium'
  return 'low'
}

function dirFromLabel(label: string): string {
  const m = label.match(/[东南西北]/)
  return m ? m[0] : normalizeDir(label.slice(0, 1))
}

function turnFromLabel(label: string): string | null {
  const m = label.match(/(左|直|右|调)/)
  return m ? m[1] : null
}

/** 车道排队键：link_id + 0-based 车道序号 */
export function laneQueueKey(linkId: string, laneIndex: number): string {
  return `${linkId}:${laneIndex}`
}

/**
 * 由认知渠化 + 证据粒度数据构建车道级排队，优先 by_lane → by_turn → 进口排队 → 进口饱和度
 */
export function buildLaneQueueMap(
  cognition: CognitionPayload | null,
  evidence: ProblemEvidence | null,
): Map<string, LaneQueueSpec> {
  const result = new Map<string, LaneQueueSpec>()
  if (!cognition?.arms?.length) return result

  const byLane = evidence?.by_lane ?? []
  const byTurn = evidence?.by_turn ?? []
  const byApproach = evidence?.by_approach ?? []

  const approachByLink = new Map(
    byApproach.filter((a) => a.link_id).map((a) => [a.link_id!, a]),
  )
  const approachByDir = new Map(
    byApproach.map((a) => [dirFromLabel(a.dir8_label ?? ''), a]),
  )

  for (const arm of cognition.arms) {
    const turns = parseTurns(arm)
    const laneCount = turns.length
    const armMetric = cognition.metrics_by_arm?.find(
      (m) => m.link_id === arm.link_id || m.dir4_label === arm.dir4_label,
    )
    const approach =
      approachByLink.get(arm.link_id) ?? approachByDir.get(arm.dir4_label)

    const perLaneQueue =
      approach?.queue_len_est_m != null
        ? Math.max(0, Math.round(queueFromMeters(approach.queue_len_est_m) / laneCount))
        : 0

    for (let i = 0; i < laneCount; i++) {
      const key = laneQueueKey(arm.link_id, i)
      const laneMeta = arm.lanes?.[i]
      const laneId = laneMeta?.lane_id
      const turn = turns[i]

      let sat: number | null = null
      let vehicles = 0

      const laneRow = byLane.find((b) => b.lane_id && b.lane_id === laneId)
      if (laneRow?.lane_saturation != null) {
        sat = laneRow.lane_saturation
        vehicles = queueFromSaturation(sat)
      }

      if (!vehicles && byTurn.length) {
        const turnRow = byTurn.find((t) => {
          const d = dirFromLabel(t.label)
          const tr = turnFromLabel(t.label)
          return d === arm.dir4_label && (tr == null || tr === turn)
        })
        if (turnRow?.turn_saturation != null) {
          sat = turnRow.turn_saturation
          vehicles = queueFromSaturation(sat)
        }
      }

      if (!vehicles && perLaneQueue > 0) {
        vehicles = perLaneQueue
        sat = armMetric?.saturation ?? null
      }

      if (!vehicles && armMetric?.saturation != null) {
        sat = armMetric.saturation
        vehicles = queueFromSaturation(sat)
      }

      result.set(key, {
        vehicleCount: vehicles,
        saturation: sat,
        colorLevel: colorLevelForSat(sat),
      })
    }
  }

  return result
}

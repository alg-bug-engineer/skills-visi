/**
 * 将后端 cognition + evidence 转为 channelizationLayer.js 所需路口结构
 */
import type { CognitionArm, CognitionPayload, IntersectionLink } from '../types/map'
import type { ProblemEvidence } from '../types/evidence'
import type { HighlightTurn, RuntimeMetrics } from '../types/presentation'
import { normalizeDir } from './mapMarkers'
import { maxTurnSatForDir, resolveTurnMetrics } from './turnMetrics'

const DIR_BEARING: Record<string, number> = {
  北: 0,
  东: 90,
  南: 180,
  西: 270,
  东北: 45,
  东南: 135,
  西南: 225,
  西北: 315,
}

const GROUP_TO_DIRS: Record<string, string[]> = {
  东西向: ['东', '西'],
  南北向: ['南', '北'],
  东南向: ['东南'],
  西南向: ['西南'],
  东北向: ['东北'],
  西北向: ['西北'],
}

const TURN_TO_CODE: Record<string, string> = {
  左: 'B',
  直: 'C',
  右: 'D',
  调: 'A',
  '11': 'C',
  '12': 'B',
  '13': 'D',
  '22': 'A',
  '31': 'C',
  '32': 'B',
  '33': 'D',
}

export interface ChannelQueueArm {
  armAngle: number
  queueM: number
  satPct: number
  satRatio: number | null
  dir4: string
  label: string
}

export interface ChannelInterItem {
  intersection_info: {
    longitude: number
    latitude: number
    name: string
  }
  surrounding_links: {
    进入路口的路段: ChannelLinkRow[]
    离开路口的路段: ChannelLinkRow[]
  }
}

export interface ChannelLinkRow {
  lane_info: string
  c_lane_num: number
  lane_num: number
  geom: string
  t_angle: number
  f_angle: number
  link_id?: string
}

function turnToCode(raw: string): string {
  const t = String(raw || '').trim()
  if (TURN_TO_CODE[t]) return TURN_TO_CODE[t]
  if (t.includes('左')) return 'B'
  if (t.includes('右')) return 'D'
  if (t.includes('调')) return 'A'
  if (t.includes('直')) return 'C'
  return 'C'
}

function laneInfoFromArm(arm: CognitionArm): string {
  if (arm.lane_info && arm.lane_info !== 'null') return arm.lane_info
  if (arm.lanes?.length) {
    return arm.lanes.map((l) => turnToCode(l.turn_move)).join('|')
  }
  const n = arm.lane_num || 3
  return Array(n).fill('C').join('|')
}

function pathToGeom(path: Array<[number, number]>): string {
  if (!path?.length) return ''
  const pts = path.map(([lon, lat]) => `${lon} ${lat}`).join(', ')
  return `LINESTRING(${pts})`
}

function armBearing(arm: CognitionArm): number {
  if (arm.entrance_angle != null) return arm.entrance_angle
  return DIR_BEARING[arm.dir4_label] ?? 0
}

function linkRowFromArm(arm: CognitionArm, links: IntersectionLink[]): ChannelLinkRow {
  const link = links.find((l) => l.link_id === arm.link_id)
  const bearing = armBearing(arm)
  const laneInfo = laneInfoFromArm(arm)
  const laneCount = arm.lane_num || arm.lanes?.length || laneInfo.split('|').length
  return {
    link_id: arm.link_id,
    lane_info: laneInfo,
    c_lane_num: laneCount,
    lane_num: laneCount,
    geom: link?.path ? pathToGeom(link.path) : '',
    t_angle: bearing,
    f_angle: (bearing + 180) % 360,
  }
}

function exitLinkRow(link: IntersectionLink): ChannelLinkRow {
  const bearing =
    link.dir4_label && DIR_BEARING[link.dir4_label] != null
      ? DIR_BEARING[link.dir4_label]
      : 0
  const laneNum = link.lane_num || 2
  return {
    link_id: link.link_id,
    lane_info: Array(laneNum).fill('C').join('|'),
    c_lane_num: laneNum,
    lane_num: laneNum,
    geom: link.path ? pathToGeom(link.path) : '',
    t_angle: (bearing + 180) % 360,
    f_angle: bearing,
  }
}

export function buildInterItemFromCognition(cognition: CognitionPayload): ChannelInterItem {
  const inter = cognition.intersection
  const links = cognition.links ?? []
  const inLinks = cognition.arms.map((arm) => linkRowFromArm(arm, links))
  const armIds = new Set(cognition.arms.map((a) => a.link_id))
  const outLinks = links
    .filter((l) => !armIds.has(l.link_id))
    .filter((l) => l.link_role !== 'entrance' && l.link_role !== '进口')
    .map(exitLinkRow)

  return {
    intersection_info: {
      longitude: inter.lon,
      latitude: inter.lat,
      name: inter.name,
    },
    surrounding_links: {
      进入路口的路段: inLinks,
      离开路口的路段: outLinks,
    },
  }
}

function dirFromLabel(label: string): string {
  const m = label.match(/[东南西北]/)
  return m ? m[0] : normalizeDir(label.slice(0, 1))
}

function dirsForGroup(group: string): string[] {
  if (GROUP_TO_DIRS[group]) return GROUP_TO_DIRS[group]
  const m = group.match(/[东南西北]/)
  return m ? [m[0]] : []
}

function resolveArmSaturation(
  arm: CognitionArm,
  cognition: CognitionPayload | null,
  evidence: ProblemEvidence | null,
  runtime?: RuntimeMetrics | null,
): number | null {
  const turnMetrics = resolveTurnMetrics(cognition, evidence?.by_turn)
  const turnMax = maxTurnSatForDir(turnMetrics, arm.dir4_label)
  if (turnMax != null && turnMax > 0) return turnMax

  const metric = cognition?.metrics_by_arm?.find(
    (m) => m.link_id === arm.link_id || m.dir4_label === arm.dir4_label,
  )
  if (metric?.saturation != null && Number(metric.saturation) > 0) {
    return Number(metric.saturation)
  }

  const turnOnArm = evidence?.by_turn?.find((t) => t.label?.includes(arm.dir4_label))
  if (turnOnArm?.turn_saturation != null && Number(turnOnArm.turn_saturation) > 0) {
    return Number(turnOnArm.turn_saturation)
  }

  const group = cognition?.direction_groups?.find(
    (g) =>
      g.arm_labels?.includes(arm.dir4_label) ||
      dirsForGroup(g.group).includes(arm.dir4_label),
  )
  const groupSat = group?.saturation_max ?? group?.saturation_avg
  if (groupSat != null && Number(groupSat) > 0) return Number(groupSat)

  const dirRow = evidence?.by_direction?.find((d) =>
    dirsForGroup(d.group).includes(arm.dir4_label),
  )
  if (dirRow?.saturation != null && Number(dirRow.saturation) > 0) {
    return Number(dirRow.saturation)
  }

  const overall =
    evidence?.metrics?.saturation_rate ?? runtime?.saturation_rate ?? null
  if (overall != null && Number(overall) > 0) return Number(overall)

  return null
}

export function buildQueueDataFromEvidence(
  cognition: CognitionPayload | null,
  evidence: ProblemEvidence | null,
  runtime?: RuntimeMetrics | null,
): ChannelQueueArm[] {
  if (!cognition?.arms?.length) return []

  const byApproach = evidence?.by_approach ?? []
  const approachByLink = new Map(
    byApproach.filter((a) => a.link_id).map((a) => [a.link_id!, a]),
  )
  const approachByDir = new Map(byApproach.map((a) => [dirFromLabel(a.dir8_label ?? ''), a]))

  return cognition.arms.map((arm) => {
    const angle = armBearing(arm)
    const approach =
      approachByLink.get(arm.link_id) ?? approachByDir.get(arm.dir4_label)
    const sat = resolveArmSaturation(arm, cognition, evidence, runtime)
    const queueM =
      approach?.queue_len_est_m ??
      evidence?.metrics?.avg_queue_m ??
      (sat != null ? Math.round(sat * 80) : 0)

    return {
      armAngle: angle,
      queueM: Math.max(0, Number(queueM) || 0),
      satRatio: sat,
      satPct: sat != null ? Math.min(200, sat * 100) : 0,
      dir4: arm.dir4_label,
      label: arm.dir_label || `${arm.dir4_label}进口`,
    }
  })
}

/** 供 applyCheckHighlight 使用的证据对象 */
export function buildHighlightEvidence(
  cognition: CognitionPayload | null,
  evidence: ProblemEvidence | null,
  runtime?: RuntimeMetrics | null,
): Record<string, number | null | undefined> {
  const turns = resolveTurnMetrics(cognition, evidence?.by_turn)
  const turnSats = turns
    .map((t) => t.turn_saturation)
    .filter((s): s is number => s != null && Number(s) > 0)
  const maxTurnSat = turnSats.length ? Math.max(...turnSats) : null

  const armSats =
    cognition?.metrics_by_arm
      ?.map((m) => m.saturation)
      .filter((s): s is number => s != null && Number(s) > 0) ?? []
  const maxArmSat = armSats.length ? Math.max(...armSats) : null

  const sat =
    maxTurnSat ??
    evidence?.metrics?.saturation_rate ??
    runtime?.saturation_rate ??
    maxArmSat ??
    undefined

  const topTurn = turns[0]
  return {
    saturation_max: sat,
    max_turn_saturation: maxTurnSat ?? topTurn?.turn_saturation ?? sat ?? undefined,
    unbalance_index:
      evidence?.metrics?.imbalance_index ?? runtime?.imbalance_index ?? undefined,
    turn_imbalance_ratio:
      evidence?.metrics?.imbalance_index ?? runtime?.imbalance_index ?? undefined,
    avg_jam_delay_index:
      evidence?.metrics?.delay_index ?? runtime?.delay_index ?? undefined,
    avg_green_ratio: evidence?.by_turn?.[0]?.green_utilization ?? undefined,
  }
}

export function highlightVerdict(
  value: number | null | undefined,
  high: number,
  warn: number,
): 'fail' | 'warn' | 'pass' | 'partial' {
  if (value == null || Number.isNaN(value)) return 'partial'
  if (value >= high) return 'fail'
  if (value >= warn) return 'warn'
  return 'pass'
}

export function parseHighlightTurn(
  raw: { dir: string; turn: string; label?: string; saturation?: number | null } | null | undefined,
): HighlightTurn | null {
  if (!raw?.dir || !raw?.turn) return null
  return {
    dir: raw.dir,
    turn: raw.turn,
    label: raw.label,
    saturation: raw.saturation ?? null,
  }
}

export function turnCodeFromLabel(turn: string): string {
  return turnToCode(turn)
}

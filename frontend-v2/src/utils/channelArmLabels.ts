import { THRESHOLDS } from '../constants'
import type { CognitionPayload, MapSceneMarker } from '../types/map'
import type { ChannelQueueArm } from './cognitionChannelAdapter'
import { normalizeDir } from './mapMarkers'
import { formatSaturation, highlightDirsForGroup, normalizeAxisFocusGroups, toAxisFocusGroup } from './evidencePresentation'
import {
  maxTurnSatForDir,
  resolveTurnMetrics,
  sortTurnMetrics,
  dirFromTurnLabel,
} from './turnMetrics'
import { resolvePrimaryProblemType } from './runtimeMetricProfile'
import { formatGreenUtilizationRaw } from './evidencePresentation'

const PLACEHOLDER_LINES = new Set(['—', '-', '–', ''])

/** 从臂标第二行解析饱和度数值（支持纯小数或带前缀文案）。 */
export function parseSaturationFromLabelLine(line2: string): number | null {
  const t = line2.trim()
  if (PLACEHOLDER_LINES.has(t)) return null
  const m =
    t.match(/(?:过饱和|饱和偏高|接近饱和|饱和[度]?)\s*([\d.]+)/) ??
    t.match(/^饱和([\d.]+)/) ??
    t.match(/^([\d.]+)$/)
  if (!m) return null
  const n = Number(m[1])
  return Number.isFinite(n) ? n : null
}

/** 饱和度问题提示（地图臂标第二行）。 */
export function saturationProblemHint(sat: number): string {
  if (sat >= 1.0) return `过饱和 ${sat.toFixed(2)}`
  if (sat >= THRESHOLDS.saturationHigh) return `饱和偏高 ${sat.toFixed(2)}`
  if (sat >= 0.85) return `接近饱和 ${sat.toFixed(2)}`
  return `饱和 ${sat.toFixed(2)}`
}

export function saturationHintColor(sat: number): string {
  if (sat >= 0.85) return '#ff6b4a'
  if (sat >= THRESHOLDS.saturationHigh) return '#ffaa44'
  return '#6dffb5'
}

export function isPlaceholderLabelLine(line2?: string | null): boolean {
  return PLACEHOLDER_LINES.has((line2 ?? '').trim())
}

export interface ArmSceneLabel {
  dir: string
  line1: string
  line2: string
  colorHex: string
}

function inferAxisGroupsFromDirs(dirs: string[]): string[] {
  const groups: string[] = []
  for (const d of dirs) {
    const axis = toAxisFocusGroup(d)
    if (axis && !groups.includes(axis)) groups.push(axis)
  }
  return normalizeAxisFocusGroups(groups)
}

function dirKeyFromLabel(dir?: string): string | null {
  if (!dir) return null
  const n = normalizeDir(dir)
  if (n.includes('东')) return '东'
  if (n.includes('西')) return '西'
  if (n.includes('南')) return '南'
  if (n.includes('北')) return '北'
  return null
}

function severityColor(sev?: string): string {
  if (sev === 'high') return '#ff6b4a'
  if (sev === 'medium') return '#ffaa44'
  if (sev === 'low') return '#6dffb5'
  return '#00e5ff'
}

/** 从 metrics_by_turn 生成渠化转向饱和度标签（每转向一条，按车道侧标注）。 */
export function buildTurnLabelsFromCognition(
  cognition: CognitionPayload | null,
): ArmSceneLabel[] {
  const turns = resolveTurnMetrics(cognition)
  const labels: ArmSceneLabel[] = []
  for (const t of sortTurnMetrics(turns)) {
    if (t.turn_saturation == null) continue
    const dir = normalizeDir(t.dir4_label || dirFromTurnLabel(t.label))
    if (!dir) continue
    const sat = Number(t.turn_saturation)
    labels.push({
      dir,
      line1: t.label,
      line2: formatSaturation(sat),
      colorHex: sat >= 0.85 ? '#ff6b4a' : sat >= 0.65 ? '#ffaa44' : '#6dffb5',
    })
  }
  return labels
}

/** 从 cognition 取单进口饱和度（有转向数据时取 max(turn_saturation)，与左侧面板口径一致）。 */
export function saturationForDir(
  cognition: CognitionPayload | null,
  dir: string,
): number | null {
  if (!cognition) return null
  const key = dirKeyFromLabel(dir)
  if (!key) return null
  const turnMax = maxTurnSatForDir(resolveTurnMetrics(cognition), key)
  if (turnMax != null && turnMax > 0) return turnMax
  for (const arm of cognition.metrics_by_arm ?? []) {
    const d = dirKeyFromLabel(arm.dir4_label)
    if (d === key && arm.saturation != null) return Number(arm.saturation)
  }
  return null
}

/** 关注/保护方向臂标：按问题类型突出主指标。 */
export function buildRoleArmLabels(
  highlightDirs: string[],
  protectedDirs: string[],
  cognition: CognitionPayload | null,
  queueArms: ChannelQueueArm[] = [],
  imbalanceIndex?: number | null,
  problemTypes: string[] = [],
): ArmSceneLabel[] {
  const byDir = new Map<string, ArmSceneLabel>()
  const queueByDir = new Map<string, ChannelQueueArm>()
  const primary = resolvePrimaryProblemType(problemTypes)
  for (const q of queueArms) {
    const key = dirKeyFromLabel(q.dir4) ?? dirKeyFromLabel(q.label)
    if (key && q.queueM > 0) queueByDir.set(key, q)
  }

  function lowUtilForDir(dirKey: string): number | null {
    const turns = resolveTurnMetrics(cognition).filter(
      (t) => dirKeyFromLabel(t.dir4_label || dirFromTurnLabel(t.label)) === dirKey,
    )
    const utils = turns
      .map((t) => t.green_utilization)
      .filter((v): v is number => v != null && Number.isFinite(v))
    if (!utils.length) return null
    return Math.min(...utils)
  }

  function metricLine(dirKey: string, sat: number | null, isFocus: boolean): string {
    const parts: string[] = []
    const q = queueByDir.get(dirKey)
    const lowUtil = lowUtilForDir(dirKey)

    if (primary === 'empty_green') {
      if (lowUtil != null) parts.push(`绿灯利用 ${formatGreenUtilizationRaw(lowUtil)}`)
      else if (sat != null) parts.push(`饱和 ${sat.toFixed(2)}`)
    } else if (primary === 'spillback') {
      if (q && q.queueM > 0) parts.push(`排队~${Math.round(q.queueM)}m`)
      if (sat != null) parts.push(`饱和 ${sat.toFixed(2)}`)
    } else if (primary === 'conflict') {
      parts.push('关注冲突点')
      if (sat != null) parts.push(`饱和 ${sat.toFixed(2)}`)
    } else {
      if (sat != null) parts.push(`饱和 ${sat.toFixed(2)}`)
      if (isFocus && imbalanceIndex != null && Number.isFinite(imbalanceIndex)) {
        parts.push(`失衡 ${Number(imbalanceIndex).toFixed(2)}`)
      }
      if (q && q.queueM > 0) parts.push(`排队~${Math.round(q.queueM)}m`)
    }
    return parts.length ? parts.join(' · ') : isFocus ? '重点关注' : '保护'
  }

  for (const group of normalizeAxisFocusGroups(inferAxisGroupsFromDirs(highlightDirs))) {
    for (const dir of highlightDirsForGroup(group)) {
      const key = dirKeyFromLabel(dir)
      if (!key) continue
      const sat = saturationForDir(cognition, key)
      byDir.set(key, {
        dir: key,
        line1: `关注 ${group}`,
        line2: metricLine(key, sat, true),
        colorHex: saturationHintColor(sat ?? 1.0),
      })
    }
  }
  for (const group of protectedDirs) {
    for (const dir of highlightDirsForGroup(group)) {
      const key = dirKeyFromLabel(dir)
      if (!key || byDir.has(key)) continue
      const sat = saturationForDir(cognition, key)
      byDir.set(key, {
        dir: key,
        line1: `保护 ${group}`,
        line2: metricLine(key, sat, false),
        colorHex: '#6dffb5',
      })
    }
  }
  return [...byDir.values()]
}

/** 从 direction_groups 补全四向饱和度标签（metrics_by_turn 缺项时 fallback）。 */
export function buildArmLabelsFromDirectionGroups(
  cognition: CognitionPayload | null,
): ArmSceneLabel[] {
  const labels: ArmSceneLabel[] = []
  for (const group of cognition?.direction_groups ?? []) {
    const groupName = group.group ?? ''
    const satRaw = group.saturation_max ?? group.saturation_avg
    if (satRaw == null || !groupName) continue
    const sat = Number(satRaw)
    const dirs =
      groupName === '东西向'
        ? ['东', '西']
        : groupName === '南北向'
          ? ['南', '北']
          : (group.arm_labels ?? [])
              .map((a) => dirKeyFromLabel(a))
              .filter((d): d is string => Boolean(d))
    for (const dir of dirs) {
      labels.push({
        dir,
        line1: groupName,
        line2: sat.toFixed(2),
        colorHex: sat >= 0.85 ? '#ff6b4a' : sat >= 0.65 ? '#ffaa44' : '#00e5ff',
      })
    }
  }
  return labels
}

/**
 * 排队长度标签：在渠化进口显示估算排队长度（米）+ 饱和度。
 * 解决「排队长度在渠化上缺少显示」——数据取自 buildQueueDataFromEvidence。
 */
export function buildArmLabelsFromQueue(
  queueArms: ChannelQueueArm[],
  options?: { includeSaturation?: boolean },
): ArmSceneLabel[] {
  const includeSaturation = options?.includeSaturation !== false
  const labels: ArmSceneLabel[] = []
  for (const arm of queueArms) {
    if (!(arm.queueM > 0)) continue
    const dir = dirKeyFromLabel(arm.dir4) ?? dirKeyFromLabel(arm.label)
    if (!dir) continue
    const meters = Math.round(arm.queueM)
    const sat = arm.satRatio
    const satText = includeSaturation && sat != null ? `饱和${sat.toFixed(2)} · ` : ''
    labels.push({
      dir,
      line1: arm.label || `${dir}进口`,
      line2: `${satText}排队~${meters}m`,
      colorHex:
        sat != null && sat >= 0.85
          ? '#ff6b4a'
          : sat != null && sat >= 0.65
            ? '#ffaa44'
            : '#00e5ff',
    })
  }
  return labels
}

/** 为渠化 3D 补全无运行数据的进口方向（显示 —）。 */
export function buildArmLabelsFromEntranceLinks(
  cognition: CognitionPayload | null,
  coveredDirs: Set<string>,
): ArmSceneLabel[] {
  void cognition
  void coveredDirs
  return []
}
export function buildArmLabelsFromScene(
  markers: MapSceneMarker[],
  cognition: CognitionPayload | null,
  options?: { fillFromCognition?: boolean },
): ArmSceneLabel[] {
  const byDir = new Map<string, ArmSceneLabel>()

  for (const m of markers) {
    if (m.kind === 'corridor-scan' || m.kind === 'corridor' || m.inter_id) continue
    const dir = dirKeyFromLabel(m.dir)
    if (!dir) continue
    const line1 = (m.title || m.kind || '指标').slice(0, 20)
    const rawLine2 =
      m.variant === 'turn'
        ? (m.value || '').slice(0, 24)
        : (m.value || m.subtitle || '').slice(0, 24)
    const line2 = isPlaceholderLabelLine(rawLine2) ? '' : rawLine2
    if (!line1 && !line2) continue
    // 同进口多转向：保留转向级标签（不覆盖）
    const key = m.variant === 'turn' ? `${dir}:${line1}` : dir
    if (m.variant !== 'turn' && byDir.has(dir)) continue
    byDir.set(key, {
      dir,
      line1,
      line2,
      colorHex: severityColor(m.severity),
    })
  }

  if (options?.fillFromCognition) {
    const turnLabels = buildTurnLabelsFromCognition(cognition)
    for (const l of turnLabels) {
      const key = `${l.dir}:${l.line1}`
      if (!byDir.has(key) && !byDir.has(l.dir)) {
        byDir.set(key, l)
      }
    }
    for (const arm of cognition?.metrics_by_arm ?? []) {
      const dir = dirKeyFromLabel(arm.dir4_label)
      if (!dir || byDir.has(dir)) continue
      if (arm.saturation == null) continue
      const sat = Number(arm.saturation)
      byDir.set(dir, {
        dir,
        line1: arm.dir4_label,
        line2: `饱和度 ${sat.toFixed(2)}`,
        colorHex: sat >= 0.85 ? '#ff6b4a' : sat >= 0.65 ? '#ffaa44' : '#00e5ff',
      })
    }
  }

  return [...byDir.values()]
}

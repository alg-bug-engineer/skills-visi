import type { CognitionPayload, MapSceneMarker } from '../types/map'
import type { ChannelQueueArm } from './cognitionChannelAdapter'
import { normalizeDir } from './mapMarkers'

export interface ArmSceneLabel {
  dir: string
  line1: string
  line2: string
  colorHex: string
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

/** 从 direction_groups 补全四向饱和度标签（metrics_by_arm 缺项时）。 */
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
export function buildArmLabelsFromQueue(queueArms: ChannelQueueArm[]): ArmSceneLabel[] {
  const labels: ArmSceneLabel[] = []
  for (const arm of queueArms) {
    if (!(arm.queueM > 0)) continue
    const dir = dirKeyFromLabel(arm.dir4) ?? dirKeyFromLabel(arm.label)
    if (!dir) continue
    const meters = Math.round(arm.queueM)
    const sat = arm.satRatio
    const satText = sat != null ? `饱和${sat.toFixed(2)} · ` : ''
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
  const labels: ArmSceneLabel[] = []
  const seen = new Set<string>()
  for (const link of cognition?.links ?? []) {
    const role = link.link_role || ''
    if (role !== 'entrance' && role !== '进口') continue
    const dir = dirKeyFromLabel(link.dir4_label || link.dir8_label)
    if (!dir || seen.has(dir) || coveredDirs.has(dir)) continue
    seen.add(dir)
    labels.push({
      dir,
      line1: `${dir}进口`,
      line2: '—',
      colorHex: severityColor('unknown'),
    })
  }
  return labels
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
    const line2 = (m.value || m.subtitle || '').slice(0, 24)
    if (!line1 && !line2) continue
    byDir.set(dir, {
      dir,
      line1,
      line2,
      colorHex: severityColor(m.severity),
    })
  }

  if (options?.fillFromCognition) {
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

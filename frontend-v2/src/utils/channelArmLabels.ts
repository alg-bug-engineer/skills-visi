import type { CognitionPayload, MapSceneMarker } from '../types/map'
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

/** 将 map_scene markers 转为渠化路臂 3D 标签（不再画在 AMap 上）。 */
export function buildArmLabelsFromScene(
  markers: MapSceneMarker[],
  cognition: CognitionPayload | null,
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

  return [...byDir.values()]
}

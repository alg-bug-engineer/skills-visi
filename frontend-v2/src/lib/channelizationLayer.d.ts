import type { Group, Vector3 } from 'three'

export function createChannelizationLayer(
  interItem: unknown,
  queueData?: unknown[] | null,
  options?: { centerAtOrigin?: boolean },
): Group

export function getChannelizationView(group: Group): {
  center: Vector3
  height: number
  minDistance: number
  maxDistance: number
}

export function disposeChannelizationLayer(group: Group | null): void

export function applyCheckHighlight(
  channelGroup: Group,
  indicatorId: string,
  verdict: string,
  evidence: Record<string, unknown>,
): void

export function clearCheckHighlight(channelGroup: Group): void

export function applyTurnHighlight(
  channelGroup: Group,
  spec: { dir: string; turnCode: string; label?: string; saturation?: number },
): void

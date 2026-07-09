import type { DirectionIntensity, PhaseStageTiming, StageMovement } from '@/api/types'

export type FlowKey = `${number}_${number}`

const DIR_CN_TO_DIR8: Record<string, number> = {
  北: 0,
  东北: 1,
  东: 2,
  东南: 3,
  南: 4,
  西南: 5,
  西: 6,
  西北: 7,
}

const DIR_CN_PREFIXES = ['东北', '东南', '西南', '西北', '北', '东', '南', '西']
// 后端优化引擎口径：0=掉头, 1=左转, 2=直行, 3=右转, 5=行人。
const TURN_DIR_TO_FLOWTYPE: Record<number, number> = { 0: 4, 1: 2, 2: 1, 3: 3, 5: 5 }
const TURN_LABEL_TO_FLOWTYPE: Array<[RegExp, number]> = [
  [/人行道|人行横道|行人|出行|入行/, 5],
  [/掉头|掉/, 4],
  [/左转|左/, 2],
  [/右转|右/, 3],
  [/直行|直/, 1],
]

export interface DirectionIntensityRow extends DirectionIntensity {
  label: string
  intensity: number
}

const DIR_LABEL: Record<number, string> = { 0: '北', 1: '东北', 2: '东', 3: '东南', 4: '南', 5: '西南', 6: '西', 7: '西北' }
const FLOW_LABEL: Record<number, string> = { 1: '直', 2: '左', 3: '右', 4: '掉头', 5: '行人' }

export function normalizeDir8(value: unknown): number | null {
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  if (n === 8) return 7
  if (n < 0 || n > 7) return null
  return Math.trunc(n)
}

export function canvasDir8(value: unknown): number | null {
  const n = normalizeDir8(value)
  if (n == null) return null
  return Math.floor(n / 2) * 2
}

export function turnDirToFlowType(value: unknown): number | null {
  const n = Number(value)
  if (!Number.isFinite(n)) return null
  return TURN_DIR_TO_FLOWTYPE[Math.trunc(n)] ?? null
}

export function flowKeyFromMovement(movement: StageMovement): FlowKey | null {
  const explicit = flowKeyFromString(movement.movement_key ?? movement.movementKey)
  if (explicit) return explicit

  const dir = canvasDir8(movement.dir8No)
  const flowType = turnDirToFlowType(movement.turnDirNo) ?? flowTypeFromLabel(movement.label)
  if (dir == null || flowType == null) return null
  return `${dir}_${flowType}`
}

export function flowKeysFromStageMovements(movements: StageMovement[] | undefined | null): FlowKey[] {
  const out: FlowKey[] = []
  for (const movement of movements ?? []) {
    const key = flowKeyFromMovement(movement)
    if (key && !out.includes(key)) out.push(key)
  }
  return out
}

export function flowKeysFromStageName(name: unknown): FlowKey[] {
  const text = String(name ?? '').trim()
  if (!text || /ring|barrier|环|搭接/i.test(text)) return []
  const out: FlowKey[] = []
  for (const part of text.split(/[、,，]/).map((item) => item.trim()).filter(Boolean)) {
    const key = flowKeyFromStageAtom(part)
    if (key && !out.includes(key)) out.push(key)
  }
  return out
}

export function flowKeysFromStage(stage: PhaseStageTiming): FlowKey[] {
  const combo = stage.flow_combo ?? stage.flowCombo
  if (Array.isArray(combo) && combo.length) {
    return mergeFlowKeys(
      flowKeysFromFlowCombo(combo),
      flowKeysFromPedDirs(stage.ped_dir_list ?? stage.pedDirList),
    )
  }

  const atoms = stage.source_stage_atoms ?? stage.sourceStageAtoms
  if (Array.isArray(atoms) && atoms.length) {
    const fromAtoms = flowKeysFromStageAtoms(atoms)
    if (fromAtoms.length) {
      return mergeFlowKeys(fromAtoms, flowKeysFromPedDirs(stage.ped_dir_list ?? stage.pedDirList))
    }
  }

  const keysFromMovements = flowKeysFromStageMovements(stage.movements)
  if (keysFromMovements.length) return keysFromMovements

  const keysFromName = flowKeysFromStageName(stage.phase_stage_name)
  if (keysFromName.length) return keysFromName

  return []
}

export function formatFlowKeysText(keys: FlowKey[]): string {
  if (!keys.length) return '未识别放行流向'
  return keys
    .map((key) => {
      const [dir, flow] = key.split('_').map(Number)
      return `${DIR_LABEL[dir] ?? `方向${dir}`}${FLOW_LABEL[flow] ?? `流向${flow}`}`
    })
    .join('、')
}

export function pctText(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : '—'
}

export function isRightTurnIntensityItem(item: DirectionIntensity | null | undefined): boolean {
  if (!item) return false
  const label = String(item.label ?? '')
  if (label) {
    if (/右转/.test(label)) return true
    return /^(东|西|南|北|东北|东南|西北|西南)右$/.test(label)
  }
  if (Number(item.turnDirNo) === 3) return true
  const movementKey = String(item.movementKey ?? '')
  if (/_t3$/.test(movementKey) || /_3$/.test(movementKey)) return true
  return false
}

export function directionIntensityRows(items: DirectionIntensity[] | undefined | null): DirectionIntensityRow[] {
  return (items ?? [])
    .filter((item) => !isRightTurnIntensityItem(item))
    .filter((item): item is DirectionIntensityRow => typeof item.intensity === 'number' && Number.isFinite(item.intensity))
    .map((item) => ({
      ...item,
      label: item.label || item.movementKey || '未知转向',
      intensity: item.intensity,
    }))
    .sort((a, b) => b.intensity - a.intensity)
}

function flowKeysFromStageAtoms(atoms: unknown[]): FlowKey[] {
  const out: FlowKey[] = []
  for (const atom of atoms) {
    const key = flowKeyFromStageAtom(atom)
    if (key && !out.includes(key)) out.push(key)
  }
  return out
}

function flowKeysFromFlowCombo(combo: unknown[]): FlowKey[] {
  const out: FlowKey[] = []
  for (const item of combo) {
    if (!item || typeof item !== 'object') continue
    const row = item as Record<string, unknown>
    const dir = resolveFlowDir8No(row)
    const flowType = Number(row.flow_type_no ?? row.flowTypeNo)
    if (dir == null || !Number.isFinite(flowType)) continue
    const key = `${dir}_${Math.trunc(flowType)}` as FlowKey
    if (!out.includes(key)) out.push(key)
  }
  return out
}

function flowKeysFromPedDirs(pedDirs: unknown[] | undefined | null): FlowKey[] {
  const out: FlowKey[] = []
  for (const dir of pedDirs ?? []) {
    const dir8 = canvasDir8(dir)
    if (dir8 == null) continue
    const key = `${dir8}_5` as FlowKey
    if (!out.includes(key)) out.push(key)
  }
  return out
}

function mergeFlowKeys(...groups: FlowKey[][]): FlowKey[] {
  const out: FlowKey[] = []
  for (const group of groups) {
    for (const key of group) {
      if (key && !out.includes(key)) out.push(key)
    }
  }
  return out
}

function resolveFlowDir8No(item: Record<string, unknown>): number | null {
  const name = String(item.f_dir8_name ?? item.f_dir8Name ?? '').trim()
  if (name && DIR_CN_TO_DIR8[name] != null) return DIR_CN_TO_DIR8[name]
  const atom = String(item.signal_atom ?? item.signalAtom ?? '').trim()
  for (const cn of DIR_CN_PREFIXES) {
    if (atom.startsWith(cn)) return DIR_CN_TO_DIR8[cn]
  }
  return canvasDir8(item.f_dir8_no ?? item.dir8No)
}

function flowKeyFromStageAtom(atom: unknown): FlowKey | null {
  const text = String(atom ?? '').trim()
  if (!text || /ring|barrier|环|搭接/i.test(text)) return null
  for (const dirName of DIR_CN_PREFIXES) {
    if (!text.startsWith(dirName)) continue
    const tail = text.slice(dirName.length)
    let flowType = 1
    if (/人行道|人行横道|行人|出行|入行/.test(tail)) flowType = 5
    else if (/掉/.test(tail)) flowType = 4
    else if (/左/.test(tail)) flowType = 2
    else if (/右/.test(tail)) flowType = 3
    else flowType = flowTypeFromLabel(tail) ?? 1
    return `${DIR_CN_TO_DIR8[dirName]}_${flowType}`
  }
  return null
}

function flowTypeFromLabel(label: unknown): number | null {
  const text = String(label ?? '')
  for (const [pattern, flowType] of TURN_LABEL_TO_FLOWTYPE) {
    if (pattern.test(text)) return flowType
  }
  return null
}

function flowKeyFromString(value: unknown): FlowKey | null {
  const text = String(value ?? '').trim()
  if (!text) return null

  const dmt = /^d(\d+)_t(\d+)$/.exec(text)
  if (dmt) {
    const dir = canvasDir8(dmt[1])
    const flowType = turnDirToFlowType(dmt[2])
    return dir == null || flowType == null ? null : `${dir}_${flowType}`
  }

  const plain = /^(\d+)_(\d+)$/.exec(text)
  if (plain) {
    const dir = canvasDir8(plain[1])
    const flow = Number(plain[2])
    return dir == null || !Number.isFinite(flow) ? null : `${dir}_${Math.trunc(flow)}`
  }

  return null
}

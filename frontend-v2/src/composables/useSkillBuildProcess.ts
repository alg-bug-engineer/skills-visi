import { reactive, ref } from 'vue'
import {
  STAGE_PROGRESS,
  type DiffLine,
  type SkillBuildEvent,
  type SkillBuildFileNode,
  type SkillBuildState,
} from '../types/skillBuild'

export function createInitialSkillBuildState(): SkillBuildState {
  return {
    visible: false,
    exiting: false,
    title: '技能沉淀工作台',
    status: 'idle',
    currentStage: 'idle',
    progress: 0,
    lastSeq: 0,
    action: 'create',
    diffChanges: [],
    isUpdate: false,
    thoughtText: '',
    modelStatus: '等待开始',
    files: [],
    fileContents: {},
    fileDiffs: {},
    logs: [],
  }
}

function appendLog(state: SkillBuildState, message: unknown, seq: number) {
  if (typeof message === 'string' && message.trim()) {
    state.logs.push({ seq, message })
  }
}

function addFileToTree(
  files: SkillBuildFileNode[],
  filePath: string,
  language: string,
  status: SkillBuildFileNode['status'],
  isUpdate?: boolean,
) {
  const parts = filePath.split('/')
  let siblings = files
  let currentPath = ''

  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index]
    currentPath = currentPath ? `${currentPath}/${part}` : part
    const isFile = index === parts.length - 1
    let node = siblings.find((item) => item.name === part)
    if (!node) {
      node = {
        name: part,
        path: currentPath,
        type: isFile ? 'file' : 'directory',
        language: isFile ? language : undefined,
        status: isFile ? status : 'completed',
        isUpdate: isFile ? isUpdate : undefined,
        children: isFile ? undefined : [],
      }
      siblings.push(node)
    }
    if (isFile) {
      node.language = language
      node.status = status
      node.isUpdate = isUpdate
    } else {
      node.children ||= []
      siblings = node.children
    }
  }
}

function markFileStatus(
  files: SkillBuildFileNode[],
  path: string,
  status: SkillBuildFileNode['status'],
): boolean {
  for (const node of files) {
    if (node.path === path) {
      node.status = status
      return true
    }
    if (node.children && markFileStatus(node.children, path, status)) {
      return true
    }
  }
  return false
}

export function reduceSkillBuildEvent(
  state: SkillBuildState,
  event: SkillBuildEvent,
  seq: number,
): void {
  state.lastSeq = seq
  const payload = event.payload
  appendLog(state, payload.display_text ?? payload.content, seq)
  state.currentStage = (event.stage as SkillBuildState['currentStage']) || state.currentStage

  switch (event.type) {
    case 'skill_build_start':
      state.visible = true
      state.exiting = false
      state.status = 'running'
      state.progress = Number(payload.progress ?? 1)
      state.action = String(payload.action ?? 'create')
      state.skillId = String(payload.skill_id ?? '')
      state.intersection = String(payload.intersection ?? '')
      state.timePeriodLabel = String(payload.time_period_label ?? '')
      state.diffChanges = Array.isArray(payload.diff_changes)
        ? (payload.diff_changes as string[])
        : []
      state.isUpdate = Boolean(payload.is_update)
      state.title = state.isUpdate
        ? `更新技能 · ${state.intersection}`
        : `沉淀技能 · ${state.intersection}`
      state.thoughtText = ''
      state.modelStatus = '正在理解本次诊断'
      break
    case 'stage_start':
      state.status = 'running'
      state.progress = Math.max(state.progress, Number(payload.progress ?? STAGE_PROGRESS[event.stage] ?? state.progress))
      break
    case 'stage_done':
      state.progress = Math.max(state.progress, Number(payload.progress ?? STAGE_PROGRESS[event.stage] ?? state.progress))
      break
    case 'model_call_start':
      state.modelStatus = String(payload.display_text ?? '模型正在思考')
      break
    case 'thought_delta':
      state.modelStatus = '正在组织技能沉淀思路'
      state.thoughtText += String(payload.delta ?? '')
      break
    case 'model_call_done':
      state.modelStatus = String(payload.display_text ?? '思路整理完成')
      break
    case 'file_diff': {
      const path = String(payload.path ?? '')
      const lines = (payload.lines as DiffLine[]) ?? []
      state.fileDiffs[path] = lines
      break
    }
    case 'file_created': {
      const path = String(payload.path ?? '')
      const language = String(payload.language ?? 'text')
      addFileToTree(state.files, path, language, 'created', Boolean(payload.is_update))
      state.activeFilePath = path
      state.fileContents[path] = ''
      break
    }
    case 'file_delta': {
      const path = String(payload.path ?? '')
      const delta = String(payload.delta ?? '')
      addFileToTree(state.files, path, String(payload.language ?? 'text'), 'writing')
      state.fileContents[path] = `${state.fileContents[path] ?? ''}${delta}`
      state.activeFilePath = path
      break
    }
    case 'file_done':
      markFileStatus(state.files, String(payload.path ?? ''), 'completed')
      break
    case 'skill_build_done':
      state.status = 'completed'
      state.progress = 100
      state.currentStage = 'completed'
      state.skillId = String(payload.skill_id ?? state.skillId ?? '')
      state.skillDir = String(payload.skill_dir ?? '')
      state.downloadUrl = String(payload.download_url ?? '')
      state.action = String(payload.action ?? state.action)
      state.modelStatus = String(payload.display_text ?? '技能沉淀完成')
      break
    default:
      break
  }
}

export function useSkillBuildProcess() {
  const state = reactive<SkillBuildState>(createInitialSkillBuildState())
  const eventSeq = ref(0)

  function reset() {
    Object.assign(state, createInitialSkillBuildState())
    eventSeq.value = 0
  }

  function open() {
    state.visible = true
    state.exiting = false
    state.status = 'running'
  }

  function applyEvent(event: SkillBuildEvent) {
    eventSeq.value += 1
    reduceSkillBuildEvent(state, event, eventSeq.value)
  }

  function beginExit() {
    state.exiting = true
  }

  function close() {
    reset()
  }

  function selectFile(path: string) {
    if (state.fileContents[path] !== undefined) {
      state.activeFilePath = path
    }
  }

  return {
    state,
    reset,
    open,
    applyEvent,
    beginExit,
    close,
    selectFile,
  }
}

export function removedDiffLines(diff: DiffLine[] | undefined): DiffLine[] {
  if (!diff) return []
  return diff.filter((line) => line.kind === 'removed')
}

export function lineDiffKind(diff: DiffLine[] | undefined, lineNo: number): string {
  if (!diff) return 'same'
  const hit = diff.find((line) => line.line_no === lineNo && line.kind !== 'same')
  return hit?.kind ?? 'same'
}

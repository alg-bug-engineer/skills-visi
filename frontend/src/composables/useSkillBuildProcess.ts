import { reactive } from 'vue'
import type { SkillFile, SkillSolidificationResult } from '@/api/types'
import {
  createInitialSkillBuildState,
  type SkillBuildFileNode,
  type SkillBuildStage,
  type SkillBuildState,
} from '@/types/skillBuild'

type Build = SkillSolidificationResult['build']

export interface SkillBuildMeta {
  skillId: string
  skillDir: string
  downloadUrl: string
  intersection: string
  timePeriodLabel: string
  action: string
}

export interface SkillBuildRunOptions {
  /** 即时全量（不排 timer、不逐字）。默认自动探测 reduced-motion / webdriver。 */
  instant?: boolean
  /** 每阶段（无文件）等待上限（毫秒）。 */
  maxStageDelayMs?: number
  /** 逐字节奏（毫秒/块）。 */
  typeDelayMs?: number
  onDone?: () => void
}

/** 写文件阶段 → 目标文件路径映射。 */
const STAGE_FILE_PATH: Partial<Record<SkillBuildStage, string>> = {
  writing_skill_md: 'SKILL.md',
  writing_reference: 'reference.md',
  writing_scripts: 'scripts/fetch_traffic_data.sql',
  writing_meta: 'skill.meta.json',
}

function detectInstant(): boolean {
  const reduced =
    typeof window !== 'undefined' &&
    !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const automation =
    typeof navigator !== 'undefined' && (navigator as Navigator).webdriver === true
  return reduced || automation
}

/** 按路径把文件挂到嵌套文件树（scripts/ 目录节点自动创建）。 */
function addFileToTree(
  files: SkillBuildFileNode[],
  filePath: string,
  language: string,
  status: SkillBuildFileNode['status'],
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
        children: isFile ? undefined : [],
      }
      siblings.push(node)
    }
    if (isFile) {
      node.type = 'file'
      node.language = language
      node.status = status
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
    if (node.children && markFileStatus(node.children, path, status)) return true
  }
  return false
}

/**
 * 技能固化构建驱动：消费后端一次性 `build` 结构，逐阶段点亮时间线、
 * 逐文件加入文件树、逐字写入 fileContents，并从 meta 填充完成态摘要。
 * 纯 Vue 响应式 + timer，无 DOM 依赖；timer 可在 reset() 全部取消。
 */
export function useSkillBuildProcess() {
  const state = reactive<SkillBuildState>(createInitialSkillBuildState())
  const timers: number[] = []

  function clearTimers() {
    for (const id of timers) clearTimeout(id)
    timers.length = 0
  }

  function schedule(fn: () => void, ms: number) {
    const id = window.setTimeout(fn, ms)
    timers.push(id)
  }

  function reset() {
    clearTimers()
    Object.assign(state, createInitialSkillBuildState())
  }

  function activateStage(index: number, stage: Build['stages'][number]) {
    for (let i = 0; i < index; i += 1) state.stages[i].status = 'done'
    if (state.stages[index]) state.stages[index].status = 'active'
    state.currentStage = stage.key as SkillBuildStage
    state.progress = stage.progress
  }

  function finalize(meta: SkillBuildMeta, opts: SkillBuildRunOptions) {
    state.stages.forEach((s) => (s.status = 'done'))
    state.status = 'completed'
    state.currentStage = 'completed'
    state.progress = 100
    state.active = false
    state.skillId = meta.skillId
    state.skillDir = meta.skillDir
    state.downloadUrl = meta.downloadUrl
    state.intersection = meta.intersection
    state.timePeriodLabel = meta.timePeriodLabel
    state.action = meta.action || state.action
    opts.onDone?.()
  }

  function fileForStage(build: Build, stageKey: SkillBuildStage): SkillFile | undefined {
    const path = STAGE_FILE_PATH[stageKey]
    if (!path) return undefined
    return (build.files ?? []).find((f) => f.path === path)
  }

  function start(build: Build, meta: SkillBuildMeta, opts: SkillBuildRunOptions = {}) {
    reset()
    const instant = opts.instant ?? detectInstant()
    const stageCap = Math.min(opts.maxStageDelayMs ?? 700, 400)
    const typeDelay = opts.typeDelayMs ?? 16

    state.active = true
    state.status = 'running'
    state.action = meta.action || state.action
    state.stages = (build.stages ?? []).map((s) => ({
      key: s.key as SkillBuildStage,
      label: s.label,
      progress: s.progress,
      status: 'pending' as const,
    }))

    const stages = build.stages ?? []

    if (instant) {
      stages.forEach((stage, i) => {
        activateStage(i, stage)
        const file = fileForStage(build, stage.key as SkillBuildStage)
        if (file) {
          addFileToTree(state.files, file.path, file.language, 'completed')
          state.fileContents[file.path] = file.content
          state.activeFilePath = file.path
        }
      })
      finalize(meta, opts)
      return
    }

    let i = 0

    function typeFile(file: SkillFile, done: () => void) {
      const content = file.content
      const chunk = Math.max(1, Math.ceil(content.length / 24))
      let pos = 0
      function tick() {
        pos = Math.min(content.length, pos + chunk)
        state.fileContents[file.path] = content.slice(0, pos)
        if (pos >= content.length) {
          done()
          return
        }
        schedule(tick, typeDelay)
      }
      schedule(tick, typeDelay)
    }

    function nextStage() {
      if (i >= stages.length) {
        finalize(meta, opts)
        return
      }
      const stage = stages[i]
      activateStage(i, stage)
      const file = fileForStage(build, stage.key as SkillBuildStage)
      if (file) {
        addFileToTree(state.files, file.path, file.language, 'writing')
        state.activeFilePath = file.path
        state.fileContents[file.path] = ''
        typeFile(file, () => {
          markFileStatus(state.files, file.path, 'completed')
          if (state.stages[i]) state.stages[i].status = 'done'
          i += 1
          schedule(nextStage, stageCap)
        })
      } else {
        if (state.stages[i]) state.stages[i].status = 'done'
        i += 1
        schedule(nextStage, stageCap)
      }
    }

    schedule(nextStage, 0)
  }

  function selectFile(path: string) {
    if (state.fileContents[path] !== undefined) state.activeFilePath = path
  }

  return { state, start, reset, selectFile }
}

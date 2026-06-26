export type SkillBuildStage =
  | 'idle'
  | 'understanding'
  | 'planning'
  | 'writing_skill_md'
  | 'writing_reference'
  | 'writing_scripts'
  | 'writing_meta'
  | 'packaging'
  | 'completed'
  | 'failed'

export type FileNodeStatus = 'pending' | 'created' | 'writing' | 'completed'

export type SkillBuildFileNode = {
  name: string
  path: string
  type: 'file' | 'directory'
  language?: string
  status: FileNodeStatus
  isUpdate?: boolean
  children?: SkillBuildFileNode[]
}

export type DiffLine = {
  kind: 'same' | 'added' | 'removed'
  line_no: number
  text: string
}

export type SkillBuildLog = {
  seq: number
  message: string
}

export type SkillBuildState = {
  visible: boolean
  exiting: boolean
  title: string
  status: 'idle' | 'running' | 'completed' | 'failed'
  currentStage: SkillBuildStage
  progress: number
  lastSeq: number
  action: string
  skillId?: string
  skillDir?: string
  downloadUrl?: string
  intersection?: string
  timePeriodLabel?: string
  diffChanges: string[]
  isUpdate: boolean
  thoughtText: string
  modelStatus: string
  files: SkillBuildFileNode[]
  activeFilePath?: string
  fileContents: Record<string, string>
  fileDiffs: Record<string, DiffLine[]>
  logs: SkillBuildLog[]
  error?: string
}

export type SkillBuildEvent = {
  event: 'skill_build'
  type: string
  stage: string
  timestamp?: string
  payload: Record<string, unknown>
}

export const SKILL_BUILD_STAGES: Array<{ key: SkillBuildStage; label: string }> = [
  { key: 'understanding', label: '理解沉淀' },
  { key: 'planning', label: '结构规划' },
  { key: 'writing_skill_md', label: '技能说明' },
  { key: 'writing_reference', label: '参考文档' },
  { key: 'writing_scripts', label: '查数脚本' },
  { key: 'writing_meta', label: '索引写入' },
  { key: 'packaging', label: '打包完成' },
]

export const STAGE_PROGRESS: Record<string, number> = {
  understanding: 8,
  planning: 16,
  writing_skill_md: 32,
  writing_reference: 48,
  writing_scripts: 72,
  writing_meta: 88,
  packaging: 100,
}

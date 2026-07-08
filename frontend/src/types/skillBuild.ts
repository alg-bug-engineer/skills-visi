/**
 * 技能固化（构建落盘）前端类型契约。
 * 契约以真实后端 `SkillSolidificationResult.build` 为准（见 mock/skill_solidify_fixture.json）。
 * progress 由响应 stage.progress 驱动；STAGE_PROGRESS 仅作为源缺失时的兜底。
 */

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

export type FileNodeStatus = 'pending' | 'writing' | 'completed'

export type SkillBuildFileNode = {
  name: string
  path: string
  type: 'file' | 'directory'
  language?: string
  status: FileNodeStatus
  children?: SkillBuildFileNode[]
}

/** 阶段时间线项：由 build.stages 驱动，供组件点亮进度。 */
export type SkillBuildTimelineStage = {
  key: SkillBuildStage
  label: string
  progress: number
  status: 'pending' | 'active' | 'done'
}

export type SkillBuildState = {
  active: boolean
  status: 'idle' | 'running' | 'completed' | 'failed'
  currentStage: SkillBuildStage
  progress: number
  action: string
  skillId: string
  skillDir: string
  downloadUrl: string
  intersection: string
  timePeriodLabel: string
  stages: SkillBuildTimelineStage[]
  files: SkillBuildFileNode[]
  activeFilePath: string
  fileContents: Record<string, string>
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

/** 兜底进度：仅当响应 stage.progress 缺失时使用（优先 drive 自响应）。 */
export const STAGE_PROGRESS: Record<string, number> = {
  understanding: 8,
  planning: 20,
  writing_skill_md: 45,
  writing_reference: 62,
  writing_scripts: 80,
  writing_meta: 92,
  packaging: 100,
}

export function createInitialSkillBuildState(): SkillBuildState {
  return {
    active: false,
    status: 'idle',
    currentStage: 'idle',
    progress: 0,
    action: 'created',
    skillId: '',
    skillDir: '',
    downloadUrl: '',
    intersection: '',
    timePeriodLabel: '',
    stages: [],
    files: [],
    activeFilePath: '',
    fileContents: {},
  }
}

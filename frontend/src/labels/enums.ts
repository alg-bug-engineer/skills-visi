/**
 * 枚举 → 中文标签字典。后端字段多为枚举编码（east_to_west / evening_peak…）。
 * `t()` 未知值原样返回，绝不抛错（F-01）。
 */

type Dict = Record<string, string>

const direction: Dict = {
  east_to_west: '东向西',
  west_to_east: '西向东',
  south_to_north: '南向北',
  north_to_south: '北向南',
}

const movement: Dict = {
  straight: '直行',
  left: '左转',
  right: '右转',
  through: '直行',
  uturn: '掉头',
}

const period: Dict = {
  morning_peak: '早高峰',
  evening_peak: '晚高峰',
  midday: '平峰',
  off_peak: '平峰',
  night: '夜间',
}

const problem_type: Dict = {
  queue_spillover: '排队溢出',
  congestion_spillover: '拥堵外溢',
  congestion: '拥堵',
  spillback: '拥堵传导',
  imbalance: '流量失衡',
}

const object_type: Dict = {
  intersection: '路口',
  corridor: '干线',
  area: '区域',
}

const diagnosis_scope: Dict = {
  intersection: '目标路口',
  corridor: '目标路口 + 上下游 + 干线协调',
  area: '区域',
}

const governance_goal: Dict = {
  mitigate_spillover: '控制溢出扩散',
  prevent_downstream_congestion_spillover: '避免下游继续外溢',
  clear_queue: '清空排队',
  balance: '均衡放行',
}

const constraint: Dict = {
  avoid_downstream_spillover: '优先避免下游继续外溢',
  protect_downstream: '保护下游承接空间',
}

const risk_level: Dict = {
  low: '低',
  medium: '中',
  high: '高',
  critical: '严重',
}

const data_source: Dict = {
  pg: '真实信控数据',
  task_injection: '注入上下文',
  mock: '演示数据',
}

const match_method: Dict = {
  explicit: '精确匹配',
  fuzzy: '模糊匹配',
  reversed_order: '语序匹配',
}

const experience_type: Dict = {
  cognitive: '认知经验',
  diagnostic: '诊断经验',
  solution: '方案经验',
}

const scenario: Dict = {
  mixed: '混合型',
  high_demand_downstream_blocked: '高需求 + 下游受阻',
  local_capacity: '本路口放行不足',
  downstream_blocked: '下游承接不足',
}

const plan_id: Dict = {
  plan_dp: '干线联控方案',
  downstream_protection: '下游保护方案',
  incremental_release: '目标路口小步释放方案',
  arterial_coordination: '干线联控方案',
}

const status: Dict = {
  valid: '有效',
  rejected: '否决',
  needs_review: '待复核',
  done: '完成',
  pending: '待执行',
  running: '执行中',
}

const category: Dict = {
  textbook: '教科书案例',
  recommended: '推荐案例',
  risk: '风险案例',
}

const DICTS: Record<string, Dict> = {
  direction,
  movement,
  period,
  problem_type,
  object_type,
  diagnosis_scope,
  governance_goal,
  constraint,
  risk_level,
  data_source,
  match_method,
  experience_type,
  scenario,
  plan_id,
  status,
  category,
}

/** 安全翻译：未知枚举/空值原样回退。 */
export function t(kind: keyof typeof DICTS, value: string | null | undefined): string {
  if (value == null || value === '') return '—'
  const dict = DICTS[kind]
  return (dict && dict[value]) ?? value
}

/** 方向 + 转向 组合，如「东向西直行」。 */
export function directionMovement(dir?: string | null, mov?: string | null): string {
  const d = dir ? t('direction', dir) : ''
  const m = mov ? t('movement', mov) : ''
  return `${d}${m}` || '—'
}

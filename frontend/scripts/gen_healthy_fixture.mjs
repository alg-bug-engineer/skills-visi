// 从真实 run_1 fixture 派生「健康路口」演示 fixture：仅保留 intent + 诊断，
// 将指标归一到正常区间并置 healthy=true，去除成因/策略/方案。复用真实结构以保证地图渲染。
import { readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const src = resolve(__dirname, '../src/mock/run_1_fixture.json')
const out = resolve(__dirname, '../src/mock/run_healthy_fixture.json')

const f = JSON.parse(readFileSync(src, 'utf-8'))

const ticket = structuredClone(f.diagnosis_ticket)
ticket.problem_type = 'routine_health_check'
ticket.constraints = { priority_goal: 'maintain_stable_operation' }
ticket.governance_goal = 'maintain_stable_operation'
ticket.user_experiences = [
  {
    experience_type: 'cognitive',
    content: '需核验该路口晚高峰运行是否正常，是否需要干预',
    source_span: '核验路口运行状态',
    tags: { time_period: '18:10-18:30', direction: 'east_to_west' },
  },
]

const diag = structuredClone(f.phases.diagnosis)

// 归一化主指标到健康区间。
diag.metrics = {
  ...diag.metrics,
  queue_length_m: 372.0,
  storage_length_m: 883.94,
  queue_ratio: 0.4208,
  saturation: 0.6321,
  los: 'B',
  green_utilization: 0.7124,
  stop_count: 0.28,
  avg_delay_s: 18.6,
  imbalance_index: 0.1183,
}

// 逐进口/逐转向归一到正常。
const NAMES = ['东进口', '南进口', '西进口', '北进口']
diag.metrics.by_approach = (diag.metrics.by_approach ?? []).map((a, i) => ({
  approach: a.approach ?? NAMES[i] ?? '进口',
  saturation: [0.6321, 0.5842, 0.5137][i] ?? 0.55,
  delay_index: [86.4, 78.2, 71.5][i] ?? 75,
  los: 'B',
}))
diag.metrics.by_movement = (diag.metrics.by_movement ?? []).map((m, i) => {
  const s = [0.6321, 0.5842, 0.5137, 0.4903, 0.4521, 0.4102][i] ?? 0.5
  return { movement: m.movement, saturation: s, green_utilization: s, level: '正常' }
})

diag.overflow_verification = {
  verified: true,
  risk_level: 'low',
  message: '排队尚在进口道可容纳范围内，溢出风险较低',
}
diag.problem_confirmed = false
diag.healthy = true
diag.downstream_metrics = { queue_ratio: 0.31, saturation: 0.42, green_utilization: null }

const healthy = {
  trace_id: 'healthy-demo-01',
  completed: true,
  pipeline_complete: true,
  diagnosis_ticket: ticket,
  phases: {
    intent: structuredClone(f.phases.intent),
    diagnosis: diag,
  },
  plan: null,
  phase_results: [
    { phase: 'intent', success: true, duration_ms: 0, errors: [] },
    { phase: 'diagnosis', success: true, duration_ms: 0, errors: [] },
  ],
}

// intent 内嵌 ticket 同步 problem_type，保持一致。
if (healthy.phases.intent?.diagnosis_ticket) {
  healthy.phases.intent.diagnosis_ticket.problem_type = 'routine_health_check'
}

writeFileSync(out, JSON.stringify(healthy, null, 2) + '\n', 'utf-8')
console.log('wrote', out)

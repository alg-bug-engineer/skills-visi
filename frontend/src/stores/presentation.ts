import { defineStore } from 'pinia'
import { isApiError } from '@/api/client'
import { runAgent, runAgentStream, regeneratePlan, submitDecision, DEMO_INPUT } from '@/api/endpoints'
import type { StreamController, StreamEvent } from '@/api/sse'
import type { RunResponse } from '@/api/types'
import { ACT_DEFS, narrationFor, phaseReady, type ActDef, type CardKey, type PhaseKey } from '@/composables/useTimeline'

export type RunStatus = 'idle' | 'submitting' | 'running' | 'done' | 'error'
export type DockState = 'input' | 'running' | 'plan'
export type SignalState = 'idle' | 'connecting' | 'open' | 'closed' | 'error'
export type PlanTab = 'stage_generation' | 'plan_comparison'
export type RunMode = 'stream' | 'batch'

// 流控制器保存在模块作用域，避免进入响应式系统。
let controller: StreamController | null = null

const PHASE_LABEL: Record<PhaseKey, string> = {
  intent: '问题理解',
  diagnosis: '指标诊断',
  cause: '成因分析',
  strategy: '策略生成',
  plan: '方案生成',
}

interface State {
  status: RunStatus
  mode: RunMode
  dock: DockState
  signal: SignalState
  waiting: boolean
  computingPhase: PhaseKey | null
  userInput: string
  traceId: string | null
  response: RunResponse | null
  acts: ActDef[]
  currentAct: number
  revealedActs: number[]
  planTab: PlanTab
  fullscreen: boolean
  rollbackBanner: string | null
  toast: string | null
  errorMsg: string | null
  autoPlay: boolean
}

export const usePresentationStore = defineStore('presentation', {
  state: (): State => ({
    status: 'idle',
    mode: 'stream',
    dock: 'input',
    signal: 'idle',
    waiting: false,
    computingPhase: null,
    userInput: DEMO_INPUT,
    traceId: null,
    response: null,
    acts: ACT_DEFS,
    currentAct: -1,
    revealedActs: [],
    planTab: 'stage_generation',
    fullscreen: false,
    rollbackBanner: null,
    toast: null,
    errorMsg: null,
    autoPlay: true,
  }),

  getters: {
    ticket: (s) => s.response?.diagnosis_ticket ?? null,
    intent: (s) => s.response?.phases?.intent ?? null,
    diagnosis: (s) => s.response?.phases?.diagnosis ?? null,
    cause: (s) => s.response?.phases?.cause ?? null,
    strategy: (s) => s.response?.phases?.strategy ?? null,
    plan: (s) => s.response?.plan ?? null,
    phaseResults: (s) => s.response?.phase_results ?? [],
    pipelineComplete: (s) => s.response?.pipeline_complete ?? false,
    activeAct: (s): ActDef | null => s.acts[s.currentAct] ?? null,
    activeNarration(s): string[] {
      const act = s.acts[s.currentAct]
      return act ? narrationFor(act, s.response) : []
    },
    isRevealed: (s) => (i: number) => s.revealedActs.includes(i),
    lastActIndex: (s) => s.acts.length - 1,
    computingLabel: (s) => (s.computingPhase ? PHASE_LABEL[s.computingPhase] : ''),
  },

  actions: {
    /** 默认走流式；失败自动降级到单次 JSON。 */
    startRun(input?: string) {
      const userInput = (input ?? this.userInput).trim()
      if (!userInput) return
      this.reset(false)
      this.userInput = userInput
      this.mode = 'stream'
      this.status = 'running'
      this.dock = 'running'
      this.signal = 'connecting'
      this.waiting = true
      this.computingPhase = 'intent'

      controller?.close()
      controller = runAgentStream(userInput, {
        onStatus: (s) => {
          if (s === 'open') this.signal = 'open'
          else if (s === 'error') this.signal = 'error'
          else if (s === 'connecting') this.signal = 'connecting'
        },
        onEvent: (ev) => this.onStreamEvent(ev),
        onFail: () => this.fallbackToBatch(userInput),
      })
    },

    onStreamEvent(ev: StreamEvent) {
      const data = ev.data as Record<string, unknown>
      if (ev.event === 'phase_start') {
        this.computingPhase = (data.phase as PhaseKey) ?? this.computingPhase
      } else if (ev.event === 'phase_done') {
        const snap = data.snapshot as RunResponse | undefined
        if (snap) this.applySnapshot(snap)
        if (data.success === false) return
        this.resumeIfReady()
      } else if (ev.event === 'pipeline_complete') {
        const snap = data.snapshot as RunResponse | undefined
        if (snap) this.applySnapshot(snap)
        this.signal = 'open'
        this.resumeIfReady()
      } else if (ev.event === 'error') {
        this.status = 'error'
        this.signal = 'error'
        this.waiting = false
        this.errorMsg = String((data.errors as string[])?.[0] ?? '流式执行失败')
        this.toast = `推演在「${this.computingLabel || '某阶段'}」中断：${this.errorMsg}`
      }
    },

    applySnapshot(snap: RunResponse) {
      this.response = snap
      if (snap.trace_id) this.traceId = snap.trace_id
    },

    /** 快照更新后，尝试从等待态进入下一（或首）幕。 */
    resumeIfReady() {
      if (this.currentAct === -1) {
        if (phaseReady(this.response, 'intent')) {
          this.waiting = false
          this.computingPhase = null
          this.currentAct = 0
        }
        return
      }
      if (this.waiting && this.currentAct < this.lastActIndex) {
        const next = this.acts[this.currentAct + 1]
        if (next && phaseReady(this.response, next.phase)) {
          this.waiting = false
          this.computingPhase = null
          this.currentAct += 1
        }
      }
    },

    async fallbackToBatch(userInput: string) {
      this.mode = 'batch'
      this.toast = '流式连接不可用，已切换为单次加载模式。'
      const res = await runAgent(userInput)
      if (isApiError(res)) {
        this.status = 'error'
        this.signal = 'error'
        this.errorMsg = res.reason
        this.toast = `请求失败（${res.reason}）。`
        return
      }
      this.applySnapshot(res)
      this.status = 'running'
      this.signal = 'open'
      this.waiting = false
      this.computingPhase = null
      this.currentAct = 0
    },

    /** 当前幕旁白打字完成：揭示证据卡，并按门控推进。 */
    onActTyped(index: number) {
      const act = this.acts[index]
      if (!act) return
      if (act.reveal && !this.revealedActs.includes(index)) this.revealedActs.push(index)
      if (act.id === 'act8_plan') this.dock = 'plan'
    },

    /** 打字完成后请求推进：下一幕 phase 未就绪则进入等待态。 */
    tryAdvance() {
      if (this.currentAct >= this.lastActIndex) {
        this.status = 'done'
        return
      }
      const next = this.acts[this.currentAct + 1]
      if (this.mode === 'batch' || phaseReady(this.response, next.phase)) {
        this.currentAct += 1
      } else {
        this.waiting = true
        this.computingPhase = next.phase
      }
    },

    goToAct(index: number) {
      if (index < 0 || index >= this.acts.length) return
      // 仅允许跳到已就绪 phase 的幕（流式）；batch 全就绪
      if (this.mode === 'stream' && !phaseReady(this.response, this.acts[index].phase)) return
      this.waiting = false
      this.currentAct = index
    },

    revealCard(_key: CardKey) {},
    setPlanTab(tab: PlanTab) {
      this.planTab = tab
    },
    toggleFullscreen() {
      this.fullscreen = !this.fullscreen
    },
    setSignal(s: SignalState) {
      this.signal = s
    },
    showRollback(msg: string) {
      this.rollbackBanner = msg
    },
    clearRollback() {
      this.rollbackBanner = null
    },
    clearToast() {
      this.toast = null
    },

    async accept(planId: string) {
      if (!this.traceId) return
      await submitDecision({
        trace_id: this.traceId,
        plan_id: planId,
        decision: 'accept',
        plan_snapshot: this.plan?.recommended ?? undefined,
        diagnosis_ticket: this.ticket ?? undefined,
      })
      // 接受并下发后回到主页（输入态）
      this.reset(true)
      this.toast = '方案已接受并下发，已返回主页。'
    },

    async reject(planId: string, reason: string, restartFrom = 'plan_generation') {
      if (!this.traceId) return
      await submitDecision({
        trace_id: this.traceId,
        plan_id: planId,
        decision: 'reject',
        rejection_reason: reason,
        diagnosis_ticket: this.ticket ?? undefined,
      })
      this.toast = '已拒绝，开始按修改意见再生成…'
      const res = await regeneratePlan({
        trace_id: this.traceId,
        user_input: reason,
        task: { artifacts: {} },
        restart_from: restartFrom,
      })
      if (!isApiError(res)) {
        this.applySnapshot(res)
        this.toast = '方案已按修改意见再生成。'
      }
    },

    reset(toInput = true) {
      controller?.close()
      controller = null
      this.status = 'idle'
      this.mode = 'stream'
      this.signal = 'idle'
      this.response = null
      this.currentAct = -1
      this.revealedActs = []
      this.waiting = false
      this.computingPhase = null
      this.rollbackBanner = null
      this.errorMsg = null
      this.planTab = 'stage_generation'
      if (toInput) this.dock = 'input'
    },
  },
})

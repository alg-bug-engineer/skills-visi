import { defineStore } from 'pinia'
import { isApiError } from '@/api/client'
import { runAgent, regeneratePlan, submitDecision, DEMO_INPUT } from '@/api/endpoints'
import type { RunResponse } from '@/api/types'
import { buildActs, type ActDef, type CardKey } from '@/composables/useTimeline'

export type RunStatus = 'idle' | 'submitting' | 'running' | 'done' | 'error'
export type DockState = 'input' | 'running' | 'plan'
export type SignalState = 'idle' | 'connecting' | 'open' | 'closed' | 'error'
export type PlanTab = 'stage_generation' | 'plan_comparison'

interface State {
  status: RunStatus
  dock: DockState
  signal: SignalState
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
    dock: 'input',
    signal: 'idle',
    userInput: DEMO_INPUT,
    traceId: null,
    response: null,
    acts: [],
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
    isRevealed: (s) => (i: number) => s.revealedActs.includes(i),
    lastActIndex: (s) => s.acts.length - 1,
  },

  actions: {
    async startRun(input?: string) {
      const userInput = (input ?? this.userInput).trim()
      if (!userInput) return
      this.reset(false)
      this.userInput = userInput
      this.status = 'submitting'
      this.dock = 'running'
      this.signal = 'connecting'

      const res = await runAgent(userInput)
      if (isApiError(res)) {
        this.status = 'error'
        this.signal = 'error'
        this.errorMsg = res.reason
        this.toast = `请求失败（${res.reason}）。可切换预置演示数据（Mock）继续。`
        return
      }
      this.applyResponse(res)
      this.status = 'running'
      this.signal = 'open'
      this.currentAct = 0
    },

    applyResponse(res: RunResponse) {
      this.response = res
      this.traceId = res.trace_id
      this.acts = buildActs(res)
    },

    /** 当前幕旁白打字完成：揭示证据卡，并按需推进。 */
    onActTyped(index: number) {
      const act = this.acts[index]
      if (!act) return
      if (act.reveal && !this.revealedActs.includes(index)) {
        this.revealedActs.push(index)
      }
      if (act.id === 'act8_plan') {
        this.dock = 'plan'
      }
    },

    goToAct(index: number) {
      if (index < 0 || index >= this.acts.length) return
      this.currentAct = index
    },

    advance() {
      if (this.currentAct < this.acts.length - 1) {
        this.currentAct += 1
      } else {
        this.status = 'done'
      }
    },

    revealCard(_key: CardKey) {
      // 预留：手动揭示（当前由 onActTyped 驱动）
    },

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
      this.toast = '方案已接受并下发，进入执行监测。'
      this.status = 'done'
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
        this.applyResponse(res)
        this.toast = '方案已按修改意见再生成。'
      }
    },

    reset(toInput = true) {
      this.status = 'idle'
      this.response = null
      this.acts = []
      this.currentAct = -1
      this.revealedActs = []
      this.rollbackBanner = null
      this.errorMsg = null
      this.planTab = 'stage_generation'
      if (toInput) this.dock = 'input'
    },
  },
})

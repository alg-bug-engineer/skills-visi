import { defineStore } from 'pinia'
import { isApiError } from '@/api/client'
import {
  runAgent,
  runAgentStream,
  regeneratePlan,
  submitDecision,
  solidifySkill,
  listExperiences,
  listCases,
  listStructuredCatalog,
  DEMO_INPUT,
  type StoredExperience,
  type CaseItem,
  type StructuredCatalogItem,
} from '@/api/endpoints'
import type { StreamController, StreamEvent } from '@/api/sse'
import type { RunResponse, UserExperience, CaseCard, SkillSolidificationResult, PlanCandidate } from '@/api/types'
import type { VoiceCue } from '@/types/voice'
import { ACT_DEFS, narrationFor, phaseReady, type ActDef, type CardKey, type PhaseKey } from '@/composables/useTimeline'

export type RunStatus = 'idle' | 'submitting' | 'running' | 'done' | 'error'
export type DockState = 'input' | 'running' | 'plan'
export type SignalState = 'idle' | 'connecting' | 'open' | 'closed' | 'error'
export type RunMode = 'stream' | 'batch'
/** 方案下发后的技能固化子流程状态机。 */
export type SolidifyPhase = 'idle' | 'prompt' | 'absorbing' | 'building' | 'completed'

// 流控制器保存在模块作用域，避免进入响应式系统。
let controller: StreamController | null = null
let voiceBarrier: (() => Promise<void>) | null = null
let voiceInterrupt: (() => void) | null = null
let voiceEnqueue: ((cue: VoiceCue) => void) | null = null
let stepResumeResolve: (() => void) | null = null
const stepResumeWaiters: Array<() => void> = []

const PHASE_LABEL: Record<PhaseKey, string> = {
  intent: '问题理解',
  diagnosis: '指标诊断',
  cause: '成因分析',
  strategy: '策略生成',
  plan: '方案生成',
}

/** SSE skill phase → 用户可见阶段名（error 事件 phase 为 skill_id）。 */
const SKILL_PHASE_LABEL: Record<string, string> = {
  intent_understanding: '问题理解',
  data_analysis_diagnosis: '指标诊断',
  cause_analysis: '成因分析',
  strategy_generation: '策略生成',
  plan_generation: '方案生成',
}

/** 后端 skill phase → 前端幕门控 phase。 */
const SKILL_TO_PHASE: Record<string, PhaseKey> = {
  intent_understanding: 'intent',
  data_analysis_diagnosis: 'diagnosis',
  cause_analysis: 'cause',
  strategy_generation: 'strategy',
  plan_generation: 'plan',
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
  fullscreen: boolean
  planMinimized: boolean
  rollbackBanner: string | null
  toast: string | null
  errorMsg: string | null
  autoPlay: boolean
  /** 步骤间暂停：为 true 时阻塞幕切换（tryAdvance / resumeIfReady），不打断当前幕打字/语音/地图。 */
  stepPaused: boolean
  /** 幕末推进因暂停被推迟，恢复后需补一次 tryAdvance。 */
  stepAdvancePending: boolean
  mapResetSeq: number
  solidifyPhase: SolidifyPhase
  skillResult: SkillSolidificationResult | null
  pendingSolidifyPlanId: string | null
  precip: PrecipState
}

/** 历史沉淀（全量经验 + 行业/路口案例），独立于本轮推演。 */
interface PrecipState {
  loaded: boolean
  loading: boolean
  experiences: {
    cognitive: StoredExperience[]
    diagnostic: StoredExperience[]
    solution: StoredExperience[]
  }
  interCases: CaseItem[]
  industryCases: StructuredCatalogItem[]
  meta: Record<string, unknown> | null
}

/** 全量经验条目：历史沉淀 + 本轮新吸收标记。 */
export interface PanelExperience extends StoredExperience {
  fresh?: boolean
  structured_tags?: Record<string, string[]>
}

/** 全量路口案例条目：历史沉淀 + 本轮新确认标记。 */
export interface PanelInterCase extends CaseItem {
  fresh?: boolean
  structured_tags?: Record<string, string[]>
}

const EMPTY_PRECIP = (): PrecipState => ({
  loaded: false,
  loading: false,
  experiences: { cognitive: [], diagnostic: [], solution: [] },
  interCases: [],
  industryCases: [],
  meta: null,
})

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
    fullscreen: false,
    planMinimized: false,
    rollbackBanner: null,
    toast: null,
    errorMsg: null,
    autoPlay: true,
    stepPaused: false,
    stepAdvancePending: false,
    mapResetSeq: 0,
    solidifyPhase: 'idle',
    skillResult: null,
    pendingSolidifyPlanId: null,
    precip: EMPTY_PRECIP(),
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
    /** 按类型分桶的用户经验（认知/诊断/方案） */
    experiencesByType(s): { cognitive: UserExperience[]; diagnostic: UserExperience[]; solution: UserExperience[] } {
      const all: UserExperience[] = [
        ...(s.response?.diagnosis_ticket?.user_experiences ?? []),
        ...(s.response?.phases?.intent?.user_experiences ?? []),
      ]
      const seen = new Set<string>()
      const unique = all.filter((e) => {
        const key = `${e.experience_type}:${e.content}`
        if (seen.has(key)) return false
        seen.add(key)
        return true
      })
      const cognitive = unique.filter((e) => e.experience_type === 'cognitive')
      const diagnostic = unique.filter((e) => e.experience_type === 'diagnostic')
      const solution = unique.filter((e) => e.experience_type === 'solution')
      // 诊断经验补充：成因分析
      const cause = s.response?.phases?.cause
      if (cause?.cause_analysis?.primary_cause) {
        diagnostic.push({
          experience_type: 'diagnostic',
          content: cause.cause_analysis.primary_cause,
          source_span: '成因分析',
        })
      }
      for (const r of cause?.cause_ranking ?? []) {
        if (r.cause && r.cause !== cause?.cause_analysis?.primary_cause) {
          diagnostic.push({
            experience_type: 'diagnostic',
            content: String(r.cause),
            source_span: r.role ?? '成因排序',
          })
        }
      }
      return { cognitive, diagnostic, solution }
    },
    /** 已有案例（相似检索结果） */
    existingCases(s): CaseCard[] {
      const cards = s.response?.phases?.cause?.case_cards?.cards ?? []
      const similar = (s.response?.phases?.cause as { similar_cases?: CaseCard[] } | undefined)?.similar_cases ?? []
      const merged = [...cards]
      for (const sc of similar) {
        if (!merged.some((c) => c.case_id === sc.case_id && c.title === sc.title)) merged.push(sc)
      }
      return merged
    },
    /** 全量历史沉淀经验（按类型），本轮新吸收置顶并标记 fresh。 */
    precipExperiencesByType(): {
      cognitive: PanelExperience[]
      diagnostic: PanelExperience[]
      solution: PanelExperience[]
    } {
      const runMap = this.experiencesByType
      const state = this.precip
      const build = (type: 'cognitive' | 'diagnostic' | 'solution'): PanelExperience[] => {
        const runItems = runMap[type] ?? []
        const runKeys = new Set(runItems.map((e) => e.content))
        const map = new Map<string, PanelExperience>()
        for (const e of state.experiences[type] ?? []) {
          if (!e.content) continue
          if (!map.has(e.content)) map.set(e.content, { ...e, fresh: runKeys.has(e.content) })
        }
        for (const e of runItems) {
          if (!e.content) continue
          if (!map.has(e.content)) {
            map.set(e.content, {
              experience_type: type,
              content: e.content,
              source_span: e.source_span ?? null,
              tags: e.tags,
              fresh: true,
            })
          }
        }
        return [...map.values()].sort((a, b) => Number(!!b.fresh) - Number(!!a.fresh))
      }
      return {
        cognitive: build('cognitive'),
        diagnostic: build('diagnostic'),
        solution: build('solution'),
      }
    },
    /**
     * 全量路口案例：本轮闭环检索到的相似案例（右侧「参考依据」跳转目标，置顶 fresh）
     * + 历史全量确认/风险沉淀案例。按 case_id 去重。
     */
    precipInterCases(s): PanelInterCase[] {
      const currentTrace = s.traceId
      const seen = new Set<string>()
      const out: PanelInterCase[] = []
      // 本轮成因分析检索到的相似案例（使用环节的可视化，跳转定位目标）。
      for (const c of this.existingCases) {
        const key = c.case_id ?? c.title ?? ''
        if (!key || seen.has(key)) continue
        seen.add(key)
        out.push({ ...(c as PanelInterCase), fresh: true })
      }
      // 历史全量沉淀（确认 + 风险）。
      for (const c of s.precip.interCases) {
        const key = c.case_id ?? `${c.inter_id ?? ''}:${c.title ?? ''}`
        if (!key || seen.has(key)) continue
        seen.add(key)
        out.push({ ...c, fresh: !!currentTrace && c.trace_id === currentTrace })
      }
      return out.sort((a, b) => Number(!!b.fresh) - Number(!!a.fresh))
    },
    precipIndustryCases(s): StructuredCatalogItem[] {
      return s.precip.industryCases
    },
    precipLoaded: (s) => s.precip.loaded,
    precipLoading: (s) => s.precip.loading,
    experienceReady: (s) => phaseReady(s.response, 'intent'),
    casesReady: (s) => phaseReady(s.response, 'cause'),
    /** 健康核验：诊断判定路口无问题，闭环在溢出核验幕后正常收尾。 */
    isHealthy: (s) => s.response?.phases?.diagnosis?.healthy === true,
  },

  actions: {
    /**
     * 拉取离线结构化沉淀（行业/路口/经验），独立于本轮推演。
     * 优先 GET /agent/structured-catalog；失败时降级旧 listExperiences/listCases。
     */
    async loadPrecipitation(force = false) {
      if (this.precip.loading) return
      if (this.precip.loaded && !force) return
      this.precip.loading = true
      try {
        const catalog = await listStructuredCatalog()
        if (!isApiError(catalog)) {
          const g = catalog.experiences ?? {}
          this.precip.experiences = {
            cognitive: (g.cognitive ?? []) as StoredExperience[],
            diagnostic: (g.diagnostic ?? []) as StoredExperience[],
            solution: (g.solution ?? []) as StoredExperience[],
          }
          this.precip.interCases = (catalog.intersection_cases ?? []) as CaseItem[]
          this.precip.industryCases = catalog.industry_cases ?? []
          this.precip.meta = catalog.meta ?? null
          this.precip.loaded = true
          return
        }

        const [expRes, caseRes] = await Promise.all([
          listExperiences(),
          listCases({ category: 'recommended', limit: 100 }),
        ])
        if (!isApiError(expRes)) {
          const g = expRes.experiences ?? {}
          this.precip.experiences = {
            cognitive: g.cognitive ?? [],
            diagnostic: g.diagnostic ?? [],
            solution: g.solution ?? [],
          }
        }
        const riskRes = await listCases({ category: 'risk', limit: 100 })
        const recommended = !isApiError(caseRes) ? caseRes.cases ?? [] : []
        const risk = !isApiError(riskRes) ? riskRes.cases ?? [] : []
        this.precip.interCases = [...recommended, ...risk]
        this.precip.industryCases = []
        this.precip.meta = null
        this.precip.loaded = true
      } finally {
        this.precip.loading = false
      }
    },

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
      this.stepPaused = false
      this.stepAdvancePending = false
      stepResumeResolve?.()
      stepResumeResolve = null
      stepResumeWaiters.length = 0
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
        const raw = String(data.phase ?? '')
        this.computingPhase = SKILL_TO_PHASE[raw] ?? (data.phase as PhaseKey) ?? this.computingPhase
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
        const skillPhase = String(data.phase ?? '')
        const phaseLabel =
          SKILL_PHASE_LABEL[skillPhase] || this.computingLabel || PHASE_LABEL[skillPhase as PhaseKey] || '某阶段'
        const errors = (data.errors as string[]) ?? []
        let msg = String(errors[0] ?? '流式执行失败')
        if (msg.includes('护栏校验')) {
          const details = (this.response?.plan?.candidates ?? [])
            .flatMap((c) => c.validation_errors ?? [])
            .filter(Boolean)
            .slice(0, 2)
          if (details.length) msg += `：${details.join('；')}`
        }
        this.waiting = false
        // 演示幕已开始：技能阶段失败仅记日志，不弹 toast、不改运行态，避免打断汇报节奏。
        if (this.currentAct >= 0) {
          console.warn(`[stream] ${phaseLabel} 未完成：${msg}`)
          return
        }
        this.status = 'error'
        this.signal = 'error'
        this.errorMsg = msg
        this.toast = `推演在「${phaseLabel}」中断：${msg}`
      }
    },

    applySnapshot(snap: RunResponse) {
      this.response = snap
      if (snap.trace_id) this.traceId = snap.trace_id
    },

    /** 快照更新后，尝试从等待态进入下一（或首个）阶段。 */
    resumeIfReady() {
      if (this.currentAct === -1) {
        if (phaseReady(this.response, 'intent')) {
          this.waiting = false
          this.computingPhase = null
          this.currentAct = 0
        }
        return
      }
      if (this.stepPaused) return
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

    /** 当前阶段说明打字完成：揭示证据卡，并按门控推进。 */
    onActTyped(index: number) {
      const act = this.acts[index]
      if (!act) return
      if (act.reveal && !this.revealedActs.includes(index)) this.revealedActs.push(index)
      if (act.id === 'act9_plan') {
        this.dock = 'plan'
        this.planMinimized = false
      }
    },

    togglePlanMinimized() {
      this.planMinimized = !this.planMinimized
    },

    /** 打字完成后请求推进：下一阶段 phase 未就绪则进入等待态。 */
    tryAdvance() {
      if (this.stepPaused) {
        this.stepAdvancePending = true
        return
      }
      this.stepAdvancePending = false
      if (this.currentAct >= this.lastActIndex) {
        this.status = 'done'
        return
      }
      // 健康核验：路口无问题时，闭环在「证据核验」幕后正常收尾，
      // 不再进入归因/下游承接/策略/方案等治理幕。
      if (this.isHealthy && this.acts[this.currentAct]?.id === 'act3_overflow') {
        this.waiting = false
        this.computingPhase = null
        this.status = 'done'
        return
      }
      const next = this.acts[this.currentAct + 1]
      if (this.mode === 'batch' || phaseReady(this.response, next.phase)) {
        this.currentAct += 1
      } else if (this.response?.pipeline_complete) {
        // 典型 Case 截断产物（仅诊断）或健康收尾后缺少后续幕：正常结束，避免空等。
        this.waiting = false
        this.computingPhase = null
        this.status = 'done'
      } else {
        this.waiting = true
        this.computingPhase = next.phase
      }
    },

    goToAct(index: number) {
      if (index < 0 || index >= this.acts.length) return
      // 仅允许跳到已就绪 phase 的阶段（流式）；batch 全就绪
      if (this.mode === 'stream' && !phaseReady(this.response, this.acts[index].phase)) return
      this.waiting = false
      this.currentAct = index
    },

    revealCard(_key: CardKey) {},
    setVoiceBarrier(fn: (() => Promise<void>) | null) {
      voiceBarrier = fn
    },
    setVoiceInterrupt(fn: (() => void) | null) {
      voiceInterrupt = fn
    },
    setVoiceEnqueue(fn: ((cue: VoiceCue) => void) | null) {
      voiceEnqueue = fn
    },
    enqueueVoice(cue: VoiceCue | null | undefined) {
      if (cue) voiceEnqueue?.(cue)
    },
    /** 等待当前语音队列真正播完；不得以固定超时穿透，否则会造成文字/地图跨幕。 */
    waitForVoiceBarrier(): Promise<void> {
      if (!voiceBarrier) return Promise.resolve()
      return voiceBarrier()
    },
    /** 步骤间暂停门控：暂停态下等待空格恢复后再推进。 */
    waitForStepResume(): Promise<void> {
      if (!this.stepPaused) return Promise.resolve()
      return new Promise((resolve) => {
        stepResumeWaiters.push(resolve)
      })
    },
    /** 可暂停的等待（用于幕间停留）。 */
    async pauseAwareSleep(ms: number) {
      if (ms <= 0) {
        await this.waitForStepResume()
        return
      }
      const end = Date.now() + ms
      while (Date.now() < end) {
        await this.waitForStepResume()
        const remaining = end - Date.now()
        if (remaining <= 0) break
        await new Promise<void>((r) => window.setTimeout(r, Math.min(50, remaining)))
      }
    },
    toggleStepPause() {
      if (this.stepPaused) {
        this.stepPaused = false
        stepResumeResolve?.()
        stepResumeResolve = null
        while (stepResumeWaiters.length) stepResumeWaiters.shift()?.()
        if (this.stepAdvancePending) this.tryAdvance()
        this.resumeIfReady()
      } else {
        this.stepPaused = true
      }
    },
    interruptVoice() {
      voiceInterrupt?.()
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

    async accept(planId: string, planSnapshot?: PlanCandidate) {
      if (!this.traceId) return
      const res = await submitDecision({
        trace_id: this.traceId,
        plan_id: planId,
        decision: 'accept',
        plan_snapshot: planSnapshot ?? this.plan?.recommended ?? undefined,
        diagnosis_ticket: this.ticket ?? undefined,
      })
      // 下发失败：提示并回到主页，不进入固化流程
      if (isApiError(res)) {
        this.toast = `方案下发失败：${res.reason}`
        this.reset(true)
        return
      }
      // 历史响应可能把真正的试运行配时放在 proposed_timing；确认后统一保存本次实际下发快照。
      if (planSnapshot && this.response?.plan) {
        this.response.plan.recommended = planSnapshot
        this.response.plan.recommended_plan_id = planSnapshot.plan_id
        this.response.plan.plan_status = String(planSnapshot.plan_status ?? 'trial_ready')
        this.response.plan.executable = planSnapshot.executable !== false
      }
      // 下发成功：不 reset，保留 response 快照，进入技能固化确认弹窗
      this.pendingSolidifyPlanId = planId
      this.dock = 'running'
      this.planMinimized = false
      this.solidifyPhase = 'prompt'
      // 新确认方案已沉淀到反馈库，刷新路口案例全量呈现。
      void this.loadPrecipitation(true)
    },

    /** 暂不固化：直接返回主页（输入态），清理固化态。 */
    declineSolidify() {
      this.solidifyPhase = 'idle'
      this.skillResult = null
      this.reset(true)
      this.toast = '方案已下发，已返回主页。'
    },

    /** 确认固化：透传真实快照调用后端，成功后由 overlay 驱动吸收→构建→完成。 */
    async confirmSolidify() {
      if (!this.traceId) return
      this.solidifyPhase = 'absorbing'
      const res = await solidifySkill({
        trace_id: this.traceId,
        plan_id: this.pendingSolidifyPlanId ?? '',
        diagnosis_ticket: this.ticket ?? undefined,
        plan_snapshot: this.plan?.recommended ?? undefined,
        strategy: this.strategy ?? undefined,
      })
      if (isApiError(res)) {
        this.toast = `技能固化失败：${res.reason}`
        this.solidifyPhase = 'idle'
        this.reset(true)
        return
      }
      // 请求在途期间若被重置（重置/新一轮），丢弃过期结果，避免写入陈旧态。
      if (this.solidifyPhase !== 'absorbing') return
      // 保留 absorbing 阶段：overlay 消费 skillResult 驱动可视化推进。
      this.skillResult = res
    },

    /** overlay 编排推进：absorbing→building→completed。 */
    setSolidifyPhase(phase: SolidifyPhase) {
      this.solidifyPhase = phase
    },

    /** 完成：技能已入库，返回主页（输入态）。 */
    finishSolidify() {
      this.solidifyPhase = 'idle'
      this.skillResult = null
      // 技能已入库，刷新路口案例以出现下载入口。
      void this.loadPrecipitation(true)
      this.reset(true)
      this.toast = '技能已固化并入库，已返回主页。'
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
      this.toast = '已记录修改意见，正在按意见再生成…'
      const res = await regeneratePlan({
        trace_id: this.traceId,
        user_input: reason,
        task: { artifacts: {} },
        restart_from: restartFrom,
      })
      if (!isApiError(res)) {
        this.applySnapshot(res)
        this.toast = '方案已按修改意见再生成，已返回主页。'
        this.reset(true)
      }
    },

    reset(toInput = true) {
      controller?.close()
      controller = null
      this.interruptVoice()
      this.mapResetSeq += 1
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
      this.solidifyPhase = 'idle'
      this.skillResult = null
      this.pendingSolidifyPlanId = null
      this.planMinimized = false
      this.stepPaused = false
      this.stepAdvancePending = false
      stepResumeResolve?.()
      stepResumeResolve = null
      stepResumeWaiters.length = 0
      if (toInput) this.dock = 'input'
    },
  },
})

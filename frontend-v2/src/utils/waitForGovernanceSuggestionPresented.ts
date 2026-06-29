import { STEP_INDICES } from '../constants'
import type { FlowTimingGovernance } from '../types/evidence'
import type { GovernanceSuggestionPayload } from '../types/presentation'
import { hasSuggestionCardContent } from './channelizationCopy'

export interface GovernanceSuggestionPresentationGate {
  whenQueueIdle: () => Promise<void>
  whenSettled: () => Promise<void>
  getFocusStepIndex: () => number
  getSuggestion: () => GovernanceSuggestionPayload | null
  getFlowTimingGovernance: () => FlowTimingGovernance | null
  /** 已在 analysisQueue 任务内调用时跳过 whenQueueIdle，避免自等待死锁 */
  skipQueueIdle?: boolean
  pollMs?: number
  timeoutMs?: number
}

function isSuggestionCardReady(gate: GovernanceSuggestionPresentationGate): boolean {
  return (
    gate.getFocusStepIndex() >= STEP_INDICES.SUGGESTION &&
    hasSuggestionCardContent(gate.getSuggestion(), gate.getFlowTimingGovernance())
  )
}

/** 等待地图叙事卡「治理建议」揭示完成，再进入分析终态。 */
export async function waitForGovernanceSuggestionPresented(
  gate: GovernanceSuggestionPresentationGate,
): Promise<boolean> {
  const pollMs = gate.pollMs ?? 50
  const deadline = Date.now() + (gate.timeoutMs ?? 120_000)

  while (Date.now() < deadline) {
    if (!gate.skipQueueIdle) {
      await gate.whenQueueIdle()
    }
    if (isSuggestionCardReady(gate)) {
      await gate.whenSettled()
      return true
    }
    await new Promise((resolve) => window.setTimeout(resolve, pollMs))
  }

  return isSuggestionCardReady(gate)
}

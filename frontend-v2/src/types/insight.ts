import type {
  CorridorContext,
  ExternalEvidence,
  FlowTimingGovernance,
  ProblemEvidence,
  QuantitativeConstraints,
  TimingProfile,
} from './evidence'

export interface DataInsightMetric {
  label: string
  value: string
  severity?: string
}

export interface DataInsight {
  title: string
  icon?: string
  metrics: DataInsightMetric[]
}

export type InsightCardEntry =
  | { id: string; kind: 'data'; insight: DataInsight }
  | { id: string; kind: 'evidence'; evidence: ProblemEvidence }
  | { id: string; kind: 'constraints'; constraints: QuantitativeConstraints }
  | { id: string; kind: 'granularity'; evidence: ProblemEvidence }
  | { id: string; kind: 'timing'; profile: TimingProfile }
  | { id: string; kind: 'corridor'; context: CorridorContext }
  | { id: string; kind: 'external'; external: ExternalEvidence }
  | { id: string; kind: 'chronic'; evidence: ProblemEvidence }
  | { id: string; kind: 'governance'; governance: FlowTimingGovernance }

export function createInsightCards(): InsightCardEntry[] {
  return []
}

/** @deprecated use insightCards list */
export type InsightCardKey = 'data' | 'evidence' | 'constraints'

/** @deprecated use insightCards list */
export interface RevealedCards {
  data: boolean
  evidence: boolean
  constraints: boolean
}

/** @deprecated use insightCards list */
export function createRevealedCards(): RevealedCards {
  return { data: false, evidence: false, constraints: false }
}

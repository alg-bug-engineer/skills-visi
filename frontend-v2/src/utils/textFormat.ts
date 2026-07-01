/** Strip markdown bold markers for plain UI display. */
export function stripMarkdown(text: string | null | undefined): string {
  if (!text) return ''
  return text.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\s+/g, ' ').trim()
}

export function cognitionDisplaySummary(item: {
  structured?: { summary?: string }
  text: string
}): string {
  return item.structured?.summary?.trim() || item.text
}

export function solutionDisplayText(solution: {
  solution_summary?: string | null
  solution_measure?: string | null
  qualitative?: string | null
}): string {
  return (
    stripMarkdown(solution.solution_summary) ||
    stripMarkdown(solution.solution_measure) ||
    stripMarkdown(solution.qualitative) ||
    ''
  )
}

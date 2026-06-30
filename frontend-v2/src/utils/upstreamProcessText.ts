import type { UpstreamStoryboard, UpstreamTreeNode } from '../types/map'
import { formatUpstreamTurnSplit } from './upstreamTurnSplit'

function formatUpstreamNode(node: UpstreamTreeNode, hopIndex: number): string {
  const name = (node.name ?? node.inter_id ?? '上游路口').trim()
  const sat = node.saturation
  const split = formatUpstreamTurnSplit(node.turn_split)
  const prefix = `上游${hopIndex} `
  const details: string[] = []
  if (typeof sat === 'number' && sat > 0.01) {
    details.push(`饱和 ${sat.toFixed(2)}`)
  }
  if (split) {
    details.push(split)
  }
  if (details.length) {
    return `${prefix}${name}（${details.join('，')}）`
  }
  return `${prefix}${name}`
}

/**
 * 理解过程「原因诊断」步骤：流量溯源事实陈述（不含治理结论）。
 * `targetLabel` 为用户指定的目标进口/转向（如「西左转」），用于首行点题。
 */
export function buildUpstreamProcessText(
  sb: UpstreamStoryboard | null | undefined,
  targetLabel?: string | null,
): string {
  if (!sb?.trees?.length) return ''

  const lines: string[] = []
  for (const tree of sb.trees) {
    const approach = (targetLabel || tree.approach || tree.tree_id || '').trim()
    const chain = tree.nodes
      .filter((n) => n.role === 'upstream' || n.role === 'governance')
      .sort((a, b) => (a.hop ?? 0) - (b.hop ?? 0))
      .map((n, i) => formatUpstreamNode(n, i + 1))
    if (!chain.length) {
      lines.push(`流量溯源：${approach} 沿干线向上游追溯来车。`)
      continue
    }
    lines.push(`流量溯源：${approach} 沿干线追溯上游来车。`)
    lines.push(`${approach} → ${chain.join(' → ')}`)
  }
  return lines.join('\n')
}

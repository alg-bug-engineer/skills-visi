import type { UpstreamStoryboard, UpstreamTreeNode } from '../types/map'

function formatUpstreamNode(node: UpstreamTreeNode): string {
  const name = (node.name ?? node.inter_id ?? '上游路口').trim()
  const sat = node.saturation
  if (typeof sat === 'number' && sat > 0.01) {
    return `${name}（饱和 ${sat.toFixed(2)}）`
  }
  return name
}

/** 理解过程「原因诊断」步骤：流量溯源事实陈述（不含治理结论）。 */
export function buildUpstreamProcessText(sb: UpstreamStoryboard | null | undefined): string {
  if (!sb?.trees?.length) return ''

  const lines: string[] = ['流量溯源：沿进口道干线追溯上游来车。']
  for (const tree of sb.trees) {
    const approach = tree.approach || tree.tree_id
    const chain = tree.nodes
      .filter((n) => n.role === 'upstream' || n.role === 'governance')
      .sort((a, b) => (a.hop ?? 0) - (b.hop ?? 0))
      .map(formatUpstreamNode)
    if (!chain.length) {
      lines.push(`${approach}：沿干线向上游追溯。`)
      continue
    }
    lines.push(`${approach}：${chain.join(' → ')}`)
  }
  return lines.join('\n')
}

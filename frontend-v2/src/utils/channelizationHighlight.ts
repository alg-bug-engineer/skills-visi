/** 解析证据/叙事中的转向标签，如「东进口·左转」→ { dir4: '东', turn: '左' } */
export function parseTurnLabel(label: string): { dir4: string; turn: string } | null {
  const m = label.match(/([东南西北]+).*?(左|直|右|调)/)
  if (!m) return null
  return { dir4: m[1], turn: m[2] }
}

export function turnHighlightKey(dir4: string, turn: string): string {
  return `${dir4}:${turn}`
}

export function turnKeysFromLabels(labels: string[]): string[] {
  const keys: string[] = []
  for (const label of labels) {
    const parsed = parseTurnLabel(label)
    if (parsed) keys.push(turnHighlightKey(parsed.dir4, parsed.turn))
  }
  return keys
}

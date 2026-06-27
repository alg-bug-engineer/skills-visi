/** Split streamed terminal log text into logical lines (handles missing \\n before \"> \"). */
export function splitTerminalLines(text: string): string[] {
  if (!text) return []
  const normalized = text.replace(/(?<=[^\n])> /g, '\n> ')
  return normalized
    .split('\n')
    .map((line) => line.trimEnd())
    .filter((line) => line.length > 0)
}

export function parseTerminalLine(line: string): { prompt: string; body: string } {
  if (line.startsWith('> ')) {
    return { prompt: '> ', body: line.slice(2) }
  }
  if (line.startsWith('· ')) {
    return { prompt: '· ', body: line.slice(2) }
  }
  return { prompt: '', body: line }
}

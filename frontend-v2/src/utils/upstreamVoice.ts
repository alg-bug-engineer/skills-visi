/** 上游溯源 TTS：只陈述上游路口事实，不播报治理结论或汇总。 */

/** 是否值得为该帧生成口播。 */
export function shouldVoiceUpstreamFrame(text: string | null | undefined): boolean {
  const t = text?.trim() ?? ''
  if (!t) return false
  if (/进口共溯\s*\d+/.test(t)) return false
  if (t.includes('上游普遍过饱和')) return false
  if (t.includes('治理落点')) return false
  if (t.includes('单点信控优化空间有限')) return false
  if (t.includes('过饱和，沿干线')) return false
  if (t.includes('抬升视角')) return false
  if (t.includes('沿') && t.includes('干线向上游蔓延')) return false
  return t.startsWith('上游')
}

/** 压缩为一句事实陈述：路口名 + 可选饱和度。 */
export function summarizeUpstreamVoice(text: string): string {
  const t = text.trim()
  if (!t || !t.startsWith('上游')) return ''

  const name = t.match(/^上游([^：:]+)/)?.[1]?.trim()
  if (!name) return ''

  const sat = t.match(/饱和\s*([\d.]+)/)?.[1]
  if (sat) {
    return `${name}，饱和度 ${sat}。`
  }
  return `${name}。`
}

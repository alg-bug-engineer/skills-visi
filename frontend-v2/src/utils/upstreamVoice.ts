/** 上游溯源 TTS：只播报核心步骤与结论，不朗读完整分镜文案。 */

/** 是否值得为该帧生成口播（跳过低信息过渡帧）。 */
export function shouldVoiceUpstreamFrame(text: string | null | undefined): boolean {
  const t = text?.trim() ?? ''
  if (!t) return false
  if (t.includes('过饱和，沿干线')) return true
  if (t.includes('单点信控优化空间有限')) return true
  // 汇总收束帧仅口播节点结论，不朗读「共溯 N 个路口」类字幕
  if (/进口共溯\s*\d+/.test(t)) return false
  if (t.includes('治理落点') && !t.startsWith('上游')) return false
  if (t.startsWith('上游')) return true
  if (t.includes('上游普遍过饱和')) return true
  return false
}

/** 压缩分镜叙事为一句口播要点。 */
export function summarizeUpstreamVoice(text: string): string {
  const t = text.trim()
  if (!t) return ''

  if (t.includes('过饱和，沿干线')) {
    const approach = t.split('过饱和')[0]?.trim()
    return approach ? `${approach}过饱和，开始向上游追溯。` : '开始向上游追溯。'
  }

  if (t.includes('上游普遍过饱和')) {
    return '溯源上游路口普遍过饱和，单点信控优化空间有限，需协调控流或扩容手段。'
  }

  if (t.includes('共溯')) {
    const m = t.match(/(共溯\s*\d+\s*个上游路口[^。；]*)/)
    if (m) return m[1].replace(/\s+/g, '')
    return t.split(/[。；]/)[0].slice(0, 48)
  }

  const name = t.match(/^上游([^：:]+)/)?.[1]?.trim()
  const sat = t.match(/饱和\s*([\d.]+)/)?.[1]
  if (name) {
    if (t.includes('单点信控优化空间有限') || t.includes('上游亦过饱和')) {
      return `${name}亦过饱和，单点信控优化空间有限。`
    }
    if (t.includes('治理落点') || t.includes('有信控空间')) {
      const satPart = sat ? `，饱和度${sat}` : ''
      return `${name}${satPart}，可作治理落点。`
    }
    if (sat) {
      return `${name}，饱和度${sat}。`
    }
  }

  return t.split(/[，。；]/)[0].slice(0, 48)
}

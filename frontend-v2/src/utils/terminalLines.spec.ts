import { describe, expect, it } from 'vitest'
import { parseTerminalLine, splitTerminalLines } from './terminalLines'

describe('splitTerminalLines', () => {
  it('splits on explicit newlines', () => {
    const text = '> 第一行\n> 第二行'
    expect(splitTerminalLines(text)).toEqual(['> 第一行', '> 第二行'])
  })

  it('inserts breaks when streamed chunks omit newline before prompt', () => {
    const text = '> 承载 no_spillback 约束与八大规则\n> 记录 saturation 等诊断问题类> 关联 dws_weekday_pattern 查数口径'
    expect(splitTerminalLines(text)).toEqual([
      '> 承载 no_spillback 约束与八大规则',
      '> 记录 saturation 等诊断问题类',
      '> 关联 dws_weekday_pattern 查数口径',
    ])
  })

  it('preserves bullet lines', () => {
    expect(splitTerminalLines('· 规则诊断\n· 生成建议')).toEqual(['· 规则诊断', '· 生成建议'])
  })
})

describe('parseTerminalLine', () => {
  it('parses terminal prompt lines', () => {
    expect(parseTerminalLine('> 写入 SKILL.md')).toEqual({
      prompt: '> ',
      body: '写入 SKILL.md',
    })
  })
})

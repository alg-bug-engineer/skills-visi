import { describe, expect, it } from 'vitest'
// @ts-expect-error 纯 Node .mjs 脚本，无类型声明
import { parseExpertKnowledge } from '../../scripts/parse-expert-knowledge.mjs'
import generated from '../../src/data/expertKnowledge.json'

const SAMPLE = `# 交通治理专家经验库

## 总览

| 场景 | 案例数 | 典型问题数 |
|------|--------|------------|
| 主干道干线绿波协调 | 189 | 8 |

---

## 主干道干线绿波协调

**场景 ID**: \`arterial_green_wave\`  
**案例数**: 189

沿城市主干道布设连续多个信控路口，以提升车辆通行连续性为目标。

### 典型问题: 停车频繁

- 出现频次: 28
- 典型表现:
  - 停车次数多
  - 启停频繁

#### 治理方案: 双向绿波

- 频次: 33
- 关键措施:
  - 双向绿波
- 适用条件: 主干道双向车流均衡、上下游协调条件良好时
- 注意事项: 需同步优化双向相位差与带宽，避免单向绿波成功但反向延误加剧
- 代表案例:
  - [#35] 专题 | 2021年汕头市交通精细化管理十大路口: 汕头市金砂路主干道（贯穿金平区与龙湖区），金砂-天山路口周边有医院、大型住宅区、办公区、公园等，早高峰车流激增，排队频繁回溢至上游路口。...

---

## 附录：场景-问题-方案索引

### 快查场景
- **停车频繁** → 双向绿波, 统一周期
- **周期不一** → 统一周期, 搭接相位
`

describe('parseExpertKnowledge', () => {
  it('parses scenario metadata, problems, schemes and cases', () => {
    const result = parseExpertKnowledge(SAMPLE)

    expect(result).toHaveLength(1)
    const scene = result[0]
    expect(scene.scene).toBe('主干道干线绿波协调')
    expect(scene.sceneId).toBe('arterial_green_wave')
    expect(scene.caseCount).toBe(189)
    expect(scene.desc).toContain('沿城市主干道')

    expect(scene.problems).toHaveLength(1)
    const problem = scene.problems[0]
    expect(problem.name).toBe('停车频繁')
    expect(problem.freq).toBe(28)
    expect(problem.symptoms).toEqual(['停车次数多', '启停频繁'])

    expect(problem.schemes).toHaveLength(1)
    const scheme = problem.schemes[0]
    expect(scheme.name).toBe('双向绿波')
    expect(scheme.freq).toBe(33)
    expect(scheme.measures).toEqual(['双向绿波'])
    expect(scheme.applicable).toContain('主干道双向车流均衡')
    expect(scheme.caution).toContain('相位差与带宽')

    expect(scheme.cases).toHaveLength(1)
    const c = scheme.cases[0]
    expect(c.id).toBe('35')
    expect(c.title).toBe('专题 | 2021年汕头市交通精细化管理十大路口')
    expect(c.snippet).toContain('汕头市金砂路主干道')
    expect(c.snippet).not.toContain('...')
    expect(c.snippet.length).toBeLessThanOrEqual(120)
  })

  it('does not treat trailing quick-lookup ### blocks as problems', () => {
    const result = parseExpertKnowledge(SAMPLE)
    const allProblemNames = result.flatMap((s: { problems: { name: string }[] }) =>
      s.problems.map((p) => p.name)
    )
    // 附录「快查场景」里的 `- **停车频繁** → ...` 不应被当作典型问题
    expect(allProblemNames).toEqual(['停车频繁'])
    // 场景总数只有 1（附录无场景 ID，被过滤）
    expect(result).toHaveLength(1)
  })
})

describe('generated expertKnowledge.json', () => {
  it('contains all 19 scenarios with non-empty scene and problems array', () => {
    expect(Array.isArray(generated)).toBe(true)
    expect(generated).toHaveLength(19)
    for (const scene of generated as Array<{ scene: string; problems: unknown }>) {
      expect(typeof scene.scene).toBe('string')
      expect(scene.scene.length).toBeGreaterThan(0)
      expect(Array.isArray(scene.problems)).toBe(true)
    }
  })
})

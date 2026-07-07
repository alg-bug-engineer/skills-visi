---
name: cause-analysis
description: 形成主因判断并引入相似案例增强可信度。Use when phase is cause_analysis.
metadata:
  skill_id: cause_analysis
  display_name: 成因分析
  phase: cause_analysis
  version: "0.1.0"
  enabled: true
  handler_class: CauseAnalysisSkill
  script_files:
    - scripts/build_evidence.py
  reference_files:
    - references/rules.md
    - references/cause_ranking.md
  resource_files:
    system: resources/prompts/system.txt
  execution_steps:
    - step_id: build_evidence
      title: 组装证据链
      script: scripts/build_evidence.py
      function: build_evidence
    - step_id: rank_causes
      title: 主因排序
      instruction: 结合 LLM 与案例库输出主因、次因、诱因排序。
---

# 成因分析

## 作用

承接数据分析结果，形成主因判断，并检索 `knowledge_qa.jsonl` 中的相似案例作为佐证。

## 输出约束

- 必须输出 `cause_ranking` 与 `evidence_summary`
- 需标注 `arterial_coordination_needed` 当下游接不住且上游来车强度高

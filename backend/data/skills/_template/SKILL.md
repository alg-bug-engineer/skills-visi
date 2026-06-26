---
name: skill-template
description: 路口拥堵诊断 Skill 包结构模板。固化时会按此结构生成 SKILL.md、reference.md 与 scripts/。
---

# Skill 包结构说明

每个固化的路口拥堵诊断 Skill 是一个独立目录：

```
congestion-{inter_id}-{time-period}/
├── SKILL.md                 # 标准 Agent Skill（YAML frontmatter + 执行流程）
├── skill.meta.json          # 机器可读索引（匹配、快路径加载）
├── reference.md             # 规则、结论、数据窗口说明
└── scripts/
    ├── fetch_traffic_data.py   # 可执行查数脚本
    └── fetch_traffic_data.sql  # PostgreSQL 查询参考
```

固化后可直接被 Cursor Agent 加载，也可被后端快路径检索。

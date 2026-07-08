# BUG-005：流量溯源「太短 + 方向错」（单一上游收敛 + 每路口 link 过滤）

## 基本信息

- **Bug ID**：BUG-005
- **发现日期**：2026-07-08
- **修复日期**：2026-07-08
- **严重程度**：P1（演示可视化效果严重退化）
- **状态**：已修复
- **关联需求/计划**：needs/23 · plans/23（`20260708210700-23-流量溯源进口道转向约束复刻`）
- **对照基准**：`references/流量溯源/`（`sniff/flow-trace-links-sniff.html`、`correlate_sniff_map_service.py`）

## 问题描述

对照参考 `flow-trace-links-sniff.html`，项目运行时的 link 流量溯源效果明显退化：

1. **太短**：来向溯源只画「目标 + 1 个上游」，每路口仅 1~2 条 link。
2. **方向有问题**：走廊方向与真实进口道走廊不一致。

## 根因（commit `67b0e19`「流量溯源单一上游收敛」引入的退化）

`app/trace/map_scene.py::build_flow_trace_links_sniff_map_scene`：

1. `_select_primary_upstream` 把来向多路口**塌缩为单一上游** → 走廊只剩 1 跳。
2. `_filter_turn_links` 把每个路口的真实进/出口 link **裁到进口 dir8 / 出口单条** → 无完整「十字」。
3. `_correlate_peers` 来向分支对 peer **跨 `cor_turn` 求和**、未以「进口道+转向」约束 correlate 行 → peer 选取偏离真实走廊，方向失真。
4. 去向 `trace_type` 一刀切映射 `UPSTREAM`，未区分去向左/右应为 `DOWNSTREAM`。

BUG-002 修复后曾复现「西直行来向 rendered=19(18+目标)」与参考一致，随后的单一上游收敛把它压回 1，即本次「太短」的直接来源。

## 修复方案（对齐参考 correlate_sniff_map_service.py 口径）

1. 删除 `_select_primary_upstream` 与单点塌缩：来向/去向均渲染**完整多跳走廊链**。
2. 删除 `_filter_turn_links`：target 与每个 peer 渲染其**真实进/出口 link 全集**（十字）。
3. 新增 `_row_in_corridor`：以**进口道(dir8)+转向(turn)** 行级约束 correlate 走廊
   （来向/去向直行 `cor_f_dir8==dir8 且 cor_turn==2`；去向左/右为垂直出口走廊，排除进口直行 OD）。
4. 新增 `_scene_trace_type`：来向=DOWNSTREAM；去向直行=UPSTREAM、去向左/右/掉头=DOWNSTREAM。
5. `_correlate_peers` 改为单时段(period)+目标 movement 下每 peer 取占比最大行，不跨转向求和。

## 验证（真实 PG 端到端，奥体西路与经十路路口 · 西向东直行 · 18:10-18:30）

| 溯源 | 渲染路口 | link 总数 | 主走廊跳 | 方向 |
|------|----------|-----------|----------|------|
| 来向 upstream | 13 | 95 | 12 | 向西（转山西路→洪山路→浆水泉→二环东路→燕子山） |
| 去向 downstream | 8 | 68 | 7 | 向东（奥体中路→草山岭→凤山→雪山） |

- 后端 `.venv/bin/python -m pytest tests/ -q` → **155 passed**。
- 前端 `npm test` → **119 passed**、`npm run build` 通过。
- 临时探针 `scripts/_probe_sniff_18.py` 复核后已删除。

## 经验教训

- 「收敛/降噪」优化不可牺牲真实走廊结构：溯源应保留进口道+转向约束下的完整多跳链与每路口 link 十字。
- `trace_type` 与来/去向的映射随转向反转，须按 进口×转向 查表，禁止一刀切。
- 可视化效果类改动须以真实 PG 端到端复核（对照 references 归档基准）。

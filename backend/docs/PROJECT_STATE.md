# 项目状态快照 · 语音步骤同步 + 饱和度口径

> 日期：2026-06-27  
> 分支：`main`  
> 单测：backend **119** passed · frontend vitest **24** passed

---

## 1. 本阶段新增 / 修复

| 能力 | 状态 | 说明 |
|------|------|------|
| 语音步骤同步 | ✅ | `voice_narration.json` + `onStepStart` 与理解过程对齐 |
| 饱和度小数口径 | ✅ | 前后端统一 0.92 格式，语音模板同步 |
| 约束 delta 裁剪 | ✅ | 先裁剪再生成建议，clip_note 写入 narrative |
| 干线扫描 | ✅ | 道路级拥堵发现、PG 排名、Top3 引导 |
| 意图 LLM 分类 | ✅ | 首轮二分类 + 规则兜底，禁 thinking |
| Qwen-TTS Realtime | ✅ | PCM 流式 + 源追踪 drain + cue 间隔 |

---

## 2. 关键文档

| 文档 | 内容 |
|------|------|
| [干线扫描功能说明](../../docs/plans/2026-06-27-干线扫描与路口发现.md) | 流程、状态机、模块索引 |
| [CHANGELOG.md](CHANGELOG.md) | 变更记录 |
| [PROJECT_LOGIC.md](PROJECT_LOGIC.md) | 总体逻辑（含干线分支） |
| [PROJECT_OVERVIEW.md](../../docs/PROJECT_OVERVIEW.md) | 根仓库索引 |

---

## 3. 快速启动

```bash
bash scripts/dev-v2.sh          # 8011 + 5568
cd backend && pytest -q         # 119 项
cd frontend-v2 && npm run test  # 24 项
```

环境：`backend/.env` 参考 `.env.example`（`MOCK_LLM=0` + PG 可查真实干线）

---

## 4. 验证用例

1. 开启语音开关 → 理解过程每步首次出现时播放对应引导语（与面板同步）  
2. 证据卡 / 地图 marker 饱和度显示为 `0.92` 而非 `92%`  
3. 约束「绿灯增加不能超过 5 秒」→ 建议 delta 被裁剪且 narrative 含说明  
4. 点「暂不固化」→ 不重启分析流水线，会话重置  
5. 「奥体西路有哪些拥堵路口在早高峰」→ 干线扫描 + 左侧列表  

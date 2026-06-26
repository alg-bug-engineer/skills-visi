基于 Qwen 的 API，设计一个智能体系统，整体思路如下：
交警输入：xx 路口 xx 时间上xx 问题，比如奥体西与经十路交叉口，下午四点经常发生拥堵，（应该绿灯更长一点） 智能体流程： 1、问题理解：路口、时段、问题、（建议） 2、基于数据，对提出的问题进行分析判断

* 业务规则判断，信控、流量、渠化、拥堵延迟指数等
   * 成立：生成治理建议，比如绿灯±x 秒
   * 不成立：根据数据给出委婉的分析结论【暂不考虑】
* 结果反馈和呈现
* 询问用户是否固化为该路口的 Skills
   * 是：则创建
   * 否，退出
* 

1、是前后端分离的，我们先讨论后端
2、用户发送文字内容，比如第一轮交互输入问题，触发理解、数据获取、诊断、治理建议结果反馈，然后反问的流程；然后用户二次输入是否，完整的交互；
3、理解的输入和大模型输出、从大模型输出到数据库数据获取、业务规则诊断、生成治理建议（目前只考虑绿灯相位变化）、然后反馈结果，这个完整的流程，如果业务规则Skills诊断使用 yaml 的规则进行判断，比如业务判断是 指标 a&指标 b；
4、用户回答是、可以、确认等肯定输入的时候，要将上述的完整过程，沉淀为一个该路口的 Skills，下次再问这个问题的时候，能够直接使用这个整合的 Skills
针对这个过程，进行逐步骤的讨论。


这是一个设计精良的智能体系统，我们先用一张流程图把整体架构确定下来，然后逐步讨论每个环节的设计细节。流程图中每个节点都可以点击展开讨论。下面逐步骤展开设计细节。

---

## 整体会话状态机

后端维护每个 `session` 的状态，驱动两轮交互：

```
IDLE → PROCESSING（第一轮输入触发）
     → AWAITING_CONFIRM（结果已反馈，等待用户确认）
     → DONE（否定或 Skill 创建完毕）
```

---

## 步骤①：NLU 理解

**目标**：把自然语言转成结构化 JSON，后续所有步骤都依赖这个输出。

Prompt 设计的核心是约束输出格式，并做时段归一化（"下午四点" → `16:00–18:00` 晚高峰）：

```python
NLU_SYSTEM_PROMPT = """
你是交通信号控制专家助手。从交警描述中提取结构化信息，只输出 JSON，不要任何解释。

字段规范：
- intersection: 路口全称，标准化为"X路与Y路交叉口"格式
- time_period: {"start":"HH:MM","end":"HH:MM","label":"早高峰|晚高峰|平峰|夜间"}
- problem_type: congestion | signal_timing | channelization | other
- directions: 受影响方向列表，如 ["南北向","东进口"]，无法判断则为 []
- user_suggestion: 用户提到的改善方向，无则为 null
"""

def nlu_understand(user_input: str) -> dict:
    resp = qwen_chat(system=NLU_SYSTEM_PROMPT, user=user_input)
    return json.loads(resp)  # 带 try/catch，失败则追问
```

**输出示例**：

```json
{
  "intersection": "奥体西路与经十路交叉口",
  "time_period": { "start": "16:00", "end": "18:00", "label": "晚高峰" },
  "problem_type": "congestion",
  "directions": ["南北向"],
  "user_suggestion": "绿灯延长"
}
```

---

## 步骤②：数据获取

**目标**：根据 NLU 输出，从数据库拉取诊断所需的 4 类数据。

```python
def fetch_intersection_data(nlu: dict) -> dict:
    iid = db.resolve_intersection(nlu["intersection"])  # 模糊匹配路口ID
    tp  = nlu["time_period"]

    return {
        "signal_plan": db.query("""
            SELECT phase, green_time, cycle_length, green_ratio
            FROM signal_plans
            WHERE intersection_id=? AND peak_type=?
        """, iid, tp["label"]),

        "traffic_flow": db.query("""
            SELECT direction, volume, saturation_rate, avg_queue_len
            FROM traffic_flow_stats
            WHERE intersection_id=? AND hour BETWEEN ? AND ?
        """, iid, tp["start"][:2], tp["end"][:2]),

        "channelization": db.query("""
            SELECT direction, lane_count, turn_types
            FROM channelization WHERE intersection_id=?
        """, iid),

        "congestion_index": db.query("""
            SELECT direction, delay_index, los_grade
            FROM congestion_index
            WHERE intersection_id=? AND peak_type=?
        """, iid, tp["label"]),
    }
```

关键设计：`resolve_intersection` 做模糊匹配（"奥体西与经十路" 能命中标准名），避免 NLU 提取微小差异导致查询失败。

---

## 步骤③：YAML 规则诊断

这是核心。规则文件把业务判断从代码里解耦出来，交通工程师可以直接维护。

**规则文件** `rules/traffic_rules.yaml`：

```yaml
rules:
  - id: rule_green_insufficient
    name: 绿灯时长不足导致拥堵
    problem_type: congestion
    conditions:
      - metric: congestion_index.delay_index
        operator: ">"
        threshold: 1.5
      - metric: signal_plan.green_ratio
        operator: "<"
        threshold: 0.35
    logic: AND          # 两条件同时成立
    conclusion: 绿灯配时不足是主因
    action:
      type: green_light_adjustment
      direction: increase
      # delta = min(饱和流量×15%, 上限秒数)
      formula: "min(traffic_flow.saturation_rate * cycle * 0.15, 20)"
    confidence: 0.85

  - id: rule_channelization_conflict
    name: 渠化设计与信号相位冲突
    problem_type: congestion
    conditions:
      - metric: channelization.turn_types
        operator: contains
        value: "混合左转"
      - metric: signal_plan.green_ratio
        operator: "<"
        threshold: 0.30
    logic: AND
    conclusion: 渠化与配时存在冲突
    action:
      type: green_light_adjustment
      direction: increase
      formula: "10"   # 固定建议 10 秒
    confidence: 0.70
```

**规则引擎执行器**：

```python
def run_rules(data: dict, problem_type: str) -> dict:
    rules = yaml.safe_load(open("rules/traffic_rules.yaml"))
    matched = []

    for rule in rules["rules"]:
        if rule["problem_type"] != problem_type:
            continue

        results = [eval_condition(c, data) for c in rule["conditions"]]

        passed = all(results) if rule["logic"] == "AND" else any(results)
        if passed:
            matched.append(rule)

    return {"matched_rules": matched, "diagnosed": len(matched) > 0}

def eval_condition(cond: dict, data: dict) -> bool:
    # 支持 > < >= <= == contains
    value = resolve_metric(cond["metric"], data)  # "signal_plan.green_ratio" → 0.32
    op    = cond["operator"]
    thr   = cond.get("threshold") or cond.get("value")
    ops   = {">": lambda a,b: a>b, "<": lambda a,b: a<b, "contains": lambda a,b: b in a}
    return ops[op](value, thr)
```

---

## 步骤④：建议生成

规则命中后计算具体调整量，再用 Qwen 生成自然语言报告：

```python
def generate_suggestion(rule: dict, data: dict) -> dict:
    delta = eval(rule["action"]["formula"], {"traffic_flow": data["traffic_flow"],
                                              "signal_plan": data["signal_plan"]})
    delta = round(delta)

    # Qwen 生成可读文案
    prompt = f"""
根据以下诊断结果，生成一段简洁的治理建议（不超过100字）：
- 路口：{data['meta']['intersection']}
- 问题：{rule['conclusion']}
- 建议：{rule['action']['direction']}绿灯时长 {delta} 秒
- 数据支撑：饱和度 {data['traffic_flow']['saturation_rate']:.0%}，
  延迟指数 {data['congestion_index']['delay_index']}，
  当前绿灯占比 {data['signal_plan']['green_ratio']:.0%}
"""
    narrative = qwen_chat(user=prompt)
    return {"delta_seconds": delta, "direction": rule["action"]["direction"],
            "narrative": narrative, "confidence": rule["confidence"]}
```

---

## 步骤⑤：结果反馈 + 固化询问

两轮交互的分界点，第一轮回复结构：

```python
def build_response(suggestion: dict, nlu: dict) -> str:
    return f"""
**诊断结果** · {nlu['intersection']} · {nlu['time_period']['label']}

{suggestion['narrative']}

📋 建议措施：将主要方向绿灯时长**{'+' if suggestion['direction']=='increase' else '-'}{suggestion['delta_seconds']} 秒**
📊 置信度：{suggestion['confidence']:.0%}

---
是否将此分析固化为该路口的专属 Skill？下次同类问题可直接给出结论。
回复「是」确认，回复「否」结束。
"""
```

---

## 步骤⑥：Skill 固化

用户确认后，将完整的处理流程打包为一个 Skill 实体落库：

```python
CONFIRM_WORDS = {"是", "可以", "确认", "好", "行", "ok", "yes", "好的"}

def is_confirm(text: str) -> bool:
    return text.strip().lower() in CONFIRM_WORDS or any(w in text for w in CONFIRM_WORDS)

def create_skill(session: dict) -> dict:
    skill = {
        "id": f"skill_{hash(session['nlu']['intersection'] + session['nlu']['problem_type'])}",
        "intersection": session["nlu"]["intersection"],
        "problem_type": session["nlu"]["problem_type"],
        "time_period": session["nlu"]["time_period"]["label"],
        # 记录匹配关键词（供下次命中用）
        "match_keywords": extract_keywords(session["raw_input"]),
        # 固化数据查询规格
        "data_queries": build_query_spec(session["nlu"]),
        # 固化命中的规则 ID
        "rule_ids": [r["id"] for r in session["diagnosis"]["matched_rules"]],
        # 固化建议公式
        "suggestion_formula": session["diagnosis"]["matched_rules"][0]["action"]["formula"],
        "created_at": datetime.now().isoformat(),
    }
    db.save_skill(skill)
    return skill
```

Skill 存储后，下次同类输入走快速路径：`Skill检测 → 调用已有Skill → 直接结果反馈`，跳过 NLU、数据获取、规则诊断三步，显著降低延迟和成本。

---

## 接下来可以深入讨论哪个步骤？

每个环节都有值得细化的地方，建议按以下顺序展开：

**A. Skill 检测机制** — 如何用路口名 + 问题类型做精确/模糊命中，防止误触发  
**B. YAML 规则扩展** — 如果有多条规则同时命中，优先级和组合逻辑怎么设计  
**C. Session 管理** — FastAPI 的会话状态存储（Redis/内存）和接口契约设计  
**D. NLU 鲁棒性** — 用户输入不规范时（路口名拼写、时段模糊）的容错处理  

你想先从哪个角度继续？


1、用户问题可能不太标准，这时候复杂点，需要支持追问补全信息，比如没有时间段，或者没有方向没有问题只说了一个路口等，缺少建议可以不追问通过数据诊断给出治理建议；为了满足这个NLU 的需求，最终检查完整的 json 结构体后，触发数据获取，通过完备的提示词？还是设计一个 Skills？
2、数据获取过程，是通过python 读取 postgresql 数据库，这时候有两种可能，一种是获取到数据了，然后进入处理，一种是没有获取到数据，这时候要如何处理，反问用户确认路名？还是变体路口查询？
3、没有 Skills 的时候，规则、治理建议的生成，都是通过提示工程完成是嘛？还是说将上面整个过程写成Skills？如果写成 Skills 会不会和用户固化 Skills 的逻辑冲突了。



三个问题很关键，让我逐一讨论清楚。

---

## Q1：NLU 追问补全 — 用提示词还是 Skill？

**结论：用提示词 + 字段完整性检查状态机，不用 Skill。**

这里要先把两类"Skill"的概念分开：

- **系统内置处理链**（Agent Pipeline）：NLU、数据获取、规则诊断、建议生成 → 这是框架本身，是"工厂"
- **用户固化路口Skill**：特定路口+问题+诊断+建议的快照 → 这是"工厂产出的产品"

NLU 追问属于前者，不应该让用户去管它，用结构化提示词处理即可。

**字段完整性设计**：

```python
REQUIRED = {"intersection", "time_period", "problem_type"}
OPTIONAL = {"directions", "user_suggestion"}  # 不追问，从数据推断或跳过

FOLLOW_UP_TEMPLATES = {
    "intersection":   "您描述的是哪个路口？（如：奥体西路与经十路交叉口）",
    "time_period":    "这个问题是什么时间段比较明显？（如：晚高峰、早上八点）",
    "problem_type":   "请问主要是哪类问题？（拥堵 / 信号配时 / 车道问题）",
}

def nlu_with_completion(history: list[dict]) -> dict:
    # 将所有轮次合并，重新提取（上下文累积）
    full_context = "\n".join(m["content"] for m in history if m["role"] == "user")
    result = nlu_extract(full_context)  # Qwen API 调用

    missing = [f for f in REQUIRED if not result.get(f)]
    if not missing:
        return {"status": "complete", "data": result}

    # 一次只追问一个字段（优先级：路口 > 时段 > 问题类型）
    field = missing[0]
    return {
        "status": "incomplete",
        "partial": result,
        "follow_up": FOLLOW_UP_TEMPLATES[field]
    }
```

关键设计：**每轮追问后不是"追加"解析，而是把所有用户消息合并重新提取**，这样 Qwen 能利用完整上下文，避免字段拼接错误。`directions` 和 `user_suggestion` 缺失时直接跳过，不追问。

---

## Q2：数据获取失败 — 三级降级策略

PostgreSQL 查询失败分两种情况处理方式不同。

```python
async def fetch_with_fallback(intersection_name: str, peak: str) -> FetchResult:
    
    # 第一级：精确匹配
    iid = await db.exact_match(intersection_name)
    if iid:
        return FetchResult(data=await db.fetch(iid, peak), source="exact")

    # 第二级：Qwen 规范化 + 变体查询
    # 处理"经十路和奥体西"/"奥体西/经十"等口语变体
    variants = await qwen_normalize(intersection_name)
    # 返回如：["奥体西路与经十路交叉口", "经十路与奥体西路交叉口", "奥体西路经十路路口"]
    for v in variants:
        iid = await db.fuzzy_match(v, threshold=0.82)
        if iid:
            return FetchResult(data=await db.fetch(iid, peak), source="variant", matched_name=v)

    # 第三级：相似候选 + 反问用户
    candidates = await db.search_similar(intersection_name, top_k=3)
    # 返回 DB 中最接近的3个路口
    if candidates:
        return FetchResult(
            data=None,
            source="not_found",
            follow_up=f"未能找到该路口的数据，您说的是以下路口之一吗？\n" +
                      "\n".join(f"· {c}" for c in candidates)
        )
    
    return FetchResult(data=None, source="unknown",
                       follow_up="该路口暂无数据，请确认路口名称或联系数据管理员。")
```

`fuzzy_match` 在 PostgreSQL 侧用 `pg_trgm` 扩展的 `similarity()` 函数实现，避免 Python 层遍历。第二级命中后应告知用户"已自动匹配为 XX 路口"，让用户知道发生了替换。

---

## Q3：规则/建议生成的分层架构

这里容易混淆，画清三层边界就不冲突了：

```
┌──────────────────────────────────────────────────────┐
│  用户路口 Skills（用户创建，路口专属）                  │
│  奥体西路×经十路-晚高峰-拥堵-信号优化 Skill           │
│  存储：路口ID + 规则ID + 数据查询规格 + 建议公式       │
├──────────────────────────────────────────────────────┤
│  YAML 规则引擎（系统共享，交通工程师维护）              │
│  rule_green_insufficient / rule_channelization_conflict│
│  → 确定性判断，不走 LLM                               │
├──────────────────────────────────────────────────────┤
│  Qwen 提示工程（系统内置）                            │
│  NLU 理解 / 建议文案生成 / 追问生成                   │
│  → LLM 负责"理解"和"表达"，不负责"判断"              │
└──────────────────────────────────────────────────────┘
```

**关键区分**：规则诊断是确定性的 YAML 引擎，Qwen 只负责两件事——**输入端理解**（NLU）和**输出端表达**（把规则结论转成自然语言建议）。用户固化的路口 Skill 不是重写整个流程，而是**把这次诊断的参数快照存下来**（用哪个规则、查哪些表、用什么公式），下次直接带参数走同一条流水线，跳过"探索"阶段。所以完全不冲突。

---

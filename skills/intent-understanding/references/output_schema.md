# 诊断工单输出字段

- object_type
- intersection_name
- intersection_name_candidates
- time_range（HH:MM-HH:MM）
- period（早高峰 | 晚高峰 | 平峰，与 flow_correlate.period_type 三档对齐）
- direction（东向西 | 西向东 | 南向北 | 北向南）
- movement（左转 | 直行 | 右转 | 掉头）
- problem_type
- constraints
- diagnosis_scope
- governance_goal
- user_experiences

字段约束与 DB 映射见 `app/data/intersection_config/ticket_nlu_schema.yaml`。

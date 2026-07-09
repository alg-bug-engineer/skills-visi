# 六路口全量数据明细报告 / Six-Intersection Full Data Report

生成时间 Generated: 2026-07-09T17:25:38.641464

> **重要修订（2026-07-09）**：排队长度、进口道长度、溢流比例请以 **`data/six_intersections_supplement.md`** 为准（计算口径对齐 `analysis/溢流路口统计优化.sql` 的 `direction_spacing` CTE）。本报告中基于 `rid_length_m` / `f_dist_m` 的排队比数值已作废。

数据源 Source: PostgreSQL `road6` + `xianchang` | 时间粒度 Time grain: 5-min `step_index` (day_of_week profile)

## 指标中英对照 / Metric Glossary

| 字段 Field | 中文 | English |
| --- | --- | --- |
| inter_id | 路口ID | Intersection ID |
| inter_name | 路口名称 | Intersection name |
| is_signalized | 是否信控 | Signalized (1=yes) |
| dir8_code / f_dir_8 | 八方向进口编码 | 8-direction approach code (0=N…6=W) |
| turn_dir_no | 转向编码 | Turn code (1=left, 2=through, 3=right, 0=aggregate) |
| step_index | 5分钟槽位 | 5-min slot index (×5 = minutes from midnight) |
| day_of_week | 星期 | Day of week (1=Mon…7=Sun) |
| turn_saturation | 转向饱和度 | Turn saturation (demand/capacity) |
| saturation_max | 路口最大饱和度 | Intersection max saturation |
| unbalance_index | 失衡指数 | Imbalance index |
| green_utilization | 绿灯利用率 | Green utilization (low→empty release) |
| queue_len_max | 最大排队长度(m) | Max queue length (m) |
| rid_length_m / f_dist_m | 进口道长度(m) | Approach storage length (m) |
| queue_ratio | 排队比/溢流风险 | Queue ratio = queue/storage (≥0.8 warning, ≥1.0 spillback) |
| turn_flow_total | 转向流量 | Turn flow (5-min total) |
| level_of_service | 服务水平 | Level of service (A–F) |
| cycle_len_sec | 周期(s) | Cycle length (s) |
| offset_sec | 相位差(s) | Offset (s) |
| green_sec | 绿灯(s) | Green time (s) |
| yellow_sec | 黄灯(s) | Yellow time (s) |
| all_red_sec | 全红(s) | All-red clearance (s) |
| flow_share_ratio | 溯源流量占比 | Flow correlation share ratio |


## 路口索引 / Intersection Index

| 查询别名 Alias | 库内名称 DB name | inter_id | 峰值槽位 Peak slot (Mon) |
| --- | --- | --- | --- |
| 坤顺路与奥体西路 | 坤顺路与奥体西路路口 | 011wwe28fty00001 | step 221 (18:25) |
| 解放东路与奥体西路 | 奥体西路与解放东路路口 | 011wwe28fmc00001 | step 287 (23:55) |
| 经十路与奥体西路 | 奥体西路与经十路路口 | 011wwe28ctu00001 | step 83 (06:55) |
| 奥体中路与坤顺路 | 坤顺路与奥体中路路口 | 011wwe294sq00001 | step 93 (07:45) |
| 奥体中路与解放东路 | 解放东路与奥体中路路口 | 011wwe294k300001 | step 87 (07:15) |
| 奥体中路与经十路 | 奥体中路与经十路路口 | 011wwe291ey00001 | n/a |


## 动态表覆盖对比 / Dynamic Table Coverage

| 路口 | 转向饱和度 Turn saturation | 路口评价 Inter evaluation | 绿灯利用率 Green util | 转向运行 Turn perf | DWD运行明细 DWD perf | 转向流量 Turn flow | 流量溯源 Flow correlate | 配时方案 Plan cfg |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 坤顺路与奥体西路 | 14894 | 2009 | 14894 | 22469 | 23233 | 14951 | 3105 | 15 |
| 解放东路与奥体西路 | 11520 | 1440 | 11520 | 0 | 0 | 11520 | 3323 | 16 |
| 经十路与奥体西路 | 14067 | 2009 | 14067 | 0 | 11794 | 13952 | 3327 | 28 |
| 奥体中路与坤顺路 | 11638 | 2006 | 11638 | 16837 | 16846 | 11694 | 3150 | 14 |
| 奥体中路与解放东路 | 9377 | 2009 | 9377 | 22452 | 25680 | 10817 | 1281 | 10 |
| 奥体中路与经十路 | 498 | 498 | 498 | 11244 | 15064 | 0 | 1054 | 28 |


---

## 坤顺路与奥体西路 → 坤顺路与奥体西路路口 (`011wwe28fty00001`)

### 1. 静态信息 / Static

#### 1.1 路口基础 / Basic

| 字段 Field | 值 Value |
| --- | --- |
| inter_id | 011wwe28fty00001 |
| inter_name / 路口名称 | 坤顺路与奥体西路路口 |
| is_signalized / 信控 | 1 |
| inter_type / 类型 | inter |
| inter_proto / 原型 | 1 |
| entr_cnt / 进口数 | None |
| entr_dir8 / 八方向进口掩码 | None |
| version_id | None |

#### 1.2 渠化 / Channelization (`road6.dwd_tfc_rltn_wide_inter_ft_link`)

| 方向 Direction | role | lanes | turn_move | seq |
| --- | --- | --- | --- | --- |
|  | entrance | 4 | 12|11|11|13 | 1 |
|  | exit | 4 | 32|11|11|13 | 2 |
|  | entrance | 3 | 12|11|22 | 3 |
|  | exit | 2 | 21|22 | 4 |
|  | entrance | 4 | 12|11|11|13 | 5 |
|  | exit | 4 | 12|11|11|13 | 6 |
|  | entrance | 2 | 21|22 | 7 |
|  | exit | 2 | 21|22 | 8 |

#### 1.3 相邻路口与进口道 / Adjacent & Approach (`adjacent_spacing`)

| 进口 Approach | length_m | road_level | adjacent | relation | lanes |
| --- | --- | --- | --- | --- | --- |
|  | 126.25 | None | 坤顺路与无名道路路口 | upstream | None |
|  | 374.64 | None | 安成街与奥体西路路口 | upstream | None |
|  | 195.68 | 4 | 坤顺路与坤顺路路口 | upstream | 3.0 |
|  | 112.76 | 4 | 坤顺路与无名道路路口 | upstream | 2.0 |
|  | 215.7 | 3 | 奥体西路与解放东路路口 | upstream | 4.0 |
|  | 357.21 | 3 | 安成街与奥体西路路口 | upstream | 4.0 |

#### 1.4 车道明细 / Lane detail (`dim_inter_lane_detail`)

| lane_no | dir8 | turn | lane_id |
| --- | --- | --- | --- |
| 1 | 南进口 | 12 | 13wwe28fmwwe28ft |
| 2 | 南进口 | 11 | 13wwe28fmwwe28ft |
| 3 | 南进口 | 11 | 13wwe28fmwwe28ft |
| 4 | 南进口 | 13 | 13wwe28fmwwe28ft |
| 1 | 西进口 | 21 | 13wwe28fswwe28ft |
| 2 | 西进口 | 22 | 13wwe28fswwe28ft |
| 1 | 南出口 | 12 | 13wwe28ftwwe28fm |
| 2 | 南出口 | 11 | 13wwe28ftwwe28fm |
| 3 | 南出口 | 11 | 13wwe28ftwwe28fm |
| 4 | 南出口 | 13 | 13wwe28ftwwe28fm |
| 1 | 西出口 | 21 | 13wwe28ftwwe28fs |
| 2 | 西出口 | 22 | 13wwe28ftwwe28fs |
| 1 | 北出口 | 32 | 13wwe28ftwwe28gm |
| 2 | 北出口 | 11 | 13wwe28ftwwe28gm |
| 3 | 北出口 | 11 | 13wwe28ftwwe28gm |
| … | +10 more |  |  |

### 2. 动态与聚合 / Dynamic & Aggregated (Monday profile)

#### 2.1 峰值评价槽位 / Peak evaluation slots

| step | time | sat_max | unbalance | LOS |
| --- | --- | --- | --- | --- |
| 221 | 18:25 | 1.501 | 0.4024 | F |
| 213 | 17:45 | 1.4845 | 0.4017 | F |
| 209 | 17:25 | 1.4458 | 0.3023 | F |

#### 2.2 峰值转向明细 / Peak turn movements

| dir | turn | saturation | green_util | queue_max_m | storage_m | queue_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| 北 | 直行 | 1.501 | None | None | None | None |
| 北 | 直行 | 1.2839 | None | None | None | None |
| 北 | 左转 | 0.8172 | None | None | None | None |
| 北 | 直行 | 0.6915 | None | None | None | None |
| 北 | 左转 | 0.5305 | None | None | None | None |
| 北 | 左转 | 0.4436 | None | None | None | None |
| 北 | 直行 | 0.3327 | None | None | None | None |
| 北 | 左转 | 0.0927 | None | None | None | None |

#### 2.3 任务聚合指标 / Task-level metrics

| metric | value |
| --- | --- |
| saturation_max | None |
| imbalance_index / 失衡 | 0.4024 |
| queue_length_m / 排队 | None |
| storage_length_m / 进口道长 | None |
| green_utilization / 绿灯利用率 | 0.642 |
| volume_vph / 流量 | None |
| capacity_vph / 能力 | None |

### 3. 配时信息 / Signal Timing

#### 3.1 日计划调度 / Day plan schedule (`dwd_ctl_inter_day_plan_schedule_cfg`)

| day_type | start | end | plan_no | plan_name |
| --- | --- | --- | --- | --- |
| None | 00:00:00 | 06:00:00 | None | None |
| None | 06:00:00 | 07:00:00 | None | None |
| None | 07:00:00 | 07:30:00 | None | None |
| None | 07:30:00 | 08:30:00 | None | None |
| None | 08:30:00 | 09:30:00 | None | None |
| None | 09:30:00 | 11:30:00 | None | None |
| None | 11:30:00 | 13:30:00 | None | None |
| None | 13:30:00 | 16:30:00 | None | None |
| None | 16:30:00 | 17:10:00 | None | None |
| None | 17:10:00 | 18:40:00 | None | None |
| None | 18:40:00 | 19:30:00 | None | None |
| None | 19:30:00 | 21:00:00 | None | None |
| … | +80 |  |  |  |

#### 3.2 配时方案 / Plans (`dwd_ctl_inter_plan_cfg` + `stage_timing`)


**方案 Plan 1** — 坤顺路与奥体西路路口方案1 | cycle=60s | offset=7s | stages=2

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 27 | 3 | 0 | 14 | 60 |
| 2 | 2 | 27 | 3 | 0 | 14 | 60 |


**方案 Plan 10** — 坤顺路与奥体西路路口方案10 | cycle=150s | offset=43s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | 69 | 3 | 3 | 20 | 60 |
| 2 | 4 | 32 | 3 | 0 | 23 | 40 |
| 3 | 1 | 37 | 3 | 0 | 30 | 50 |


**方案 Plan 12** — 坤顺路与奥体西路路口方案12 | cycle=160s | offset=63s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | 64 | 3 | 3 | 20 | 60 |
| 2 | 4 | 37 | 3 | 0 | 23 | 40 |
| 3 | 1 | 47 | 3 | 0 | 30 | 50 |


**方案 Plan 13** — 坤顺路与奥体西路路口方案13 | cycle=160s | offset=63s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | 64 | 3 | 3 | 20 | 60 |
| 2 | 4 | 37 | 3 | 0 | 23 | 40 |
| 3 | 1 | 47 | 3 | 0 | 30 | 50 |


**方案 Plan 14** — 坤顺路与奥体西路路口方案14 | cycle=160s | offset=63s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 3 | 64 | 3 | 3 | 20 | 60 |
| 2 | 4 | 37 | 3 | 0 | 23 | 40 |
| 3 | 1 | 47 | 3 | 0 | 30 | 50 |


_另有 10 个方案未展开 / 10 more plans omitted_

#### 3.3 阶段配置 / Stage cfg (`dwd_ctl_inter_stage_cfg`)

| stage_no | stage_name | phase_cnt | remark |
| --- | --- | --- | --- |
| 1 | 东直、东左、西直、西左、北行人、南行人 | None |  |
| 2 | 北直、北左、南直、南左、西行人、东行人 | None |  |
| 3 | 北直、南直、西行人、东行人 | None |  |
| 4 | 南左、北左 | None |  |
| 5 | 南直、南左、东行人 | None |  |
| 6 | 南直、东行人 | None |  |
| 7 | 北左、南左 | None |  |
| 8 | 西直、西左、南行人 | None |  |
| 9 | 东直、东左、北行人 | None |  |
| 10 | 空阶段10 | None | 源数据未解析出交通流组合 |

#### 3.4 最小绿 / Min green (`dwd_ctl_inter_min_green_cfg`)

| stage_no | min_green_sec | ped_min_green_sec |
| --- | --- | --- |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |

### 4. 流量溯源样本 / Flow correlate sample

| period | dir_turn | cor_inter | share | trace |
| --- | --- | --- | --- | --- |
| EVENING_PEAK | 0/1 | 坤顺路与无名道路路口 | 80.94 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 规划一号路与齐川路路口 | 55.74 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 书昌街与齐音路路口 | 55.12 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | None | 53.69 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 甸新东路与解放路路口 | 51.43 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 燕子山小区东路与解放路路口 | 49.18 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 解放路辅路与解放路辅路路口 | 49.18 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | None | 42.83 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 规划一号路与齐川路路口 | 15.57 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 泉城路与解放路路口 | 15.37 | DOWNSTREAM |


---

## 解放东路与奥体西路 → 奥体西路与解放东路路口 (`011wwe28fmc00001`)

### 1. 静态信息 / Static

#### 1.1 路口基础 / Basic

| 字段 Field | 值 Value |
| --- | --- |
| inter_id | 011wwe28fmc00001 |
| inter_name / 路口名称 | 奥体西路与解放东路路口 |
| is_signalized / 信控 | 1 |
| inter_type / 类型 | inter |
| inter_proto / 原型 | 1 |
| entr_cnt / 进口数 | None |
| entr_dir8 / 八方向进口掩码 | None |
| version_id | None |

#### 1.2 渠化 / Channelization (`road6.dwd_tfc_rltn_wide_inter_ft_link`)

| 方向 Direction | role | lanes | turn_move | seq |
| --- | --- | --- | --- | --- |
|  | entrance | 4 | 12|11|11|13 | 1 |
|  | exit | 4 | 12|11|11|13 | 2 |
|  | entrance | 4 | 12|11|11|22 | 3 |
|  | exit | 3 | 11|11|22 | 4 |
|  | entrance | 4 | 12|11|11|13 | 5 |
|  | exit | 5 | 12|12|11|11|13 | 6 |
|  | entrance | 4 | 40|12|11|22 | 7 |
|  | exit | 4 | 12|40|11|22 | 8 |

#### 1.3 相邻路口与进口道 / Adjacent & Approach (`adjacent_spacing`)

| 进口 Approach | length_m | road_level | adjacent | relation | lanes |
| --- | --- | --- | --- | --- | --- |
|  | 356.63 | None | 坤顺路与奥体西路路口 | upstream | None |
|  | 311.13 | None | 解放东路与齐川路路口 | upstream | None |
|  | 197.59 | 3 | 岔口 | upstream | 4.0 |
|  | 252.9 | 3 | 解放东路与齐川路路口 | upstream | 4.0 |
|  | 368.43 | 3 | 奥体西路与经十路路口 | upstream | 4.0 |
|  | 215.68 | 3 | 坤顺路与奥体西路路口 | upstream | 4.0 |

#### 1.4 车道明细 / Lane detail (`dim_inter_lane_detail`)

| lane_no | dir8 | turn | lane_id |
| --- | --- | --- | --- |
| 1 | 南进口 | 12 | 13wwe28ctwwe28fm |
| 2 | 南进口 | 11 | 13wwe28ctwwe28fm |
| 3 | 南进口 | 11 | 13wwe28ctwwe28fm |
| 4 | 南进口 | 13 | 13wwe28ctwwe28fm |
| 1 | 西进口 | 40 | 13wwe28f7wwe28fm |
| 2 | 西进口 | 12 | 13wwe28f7wwe28fm |
| 3 | 西进口 | 11 | 13wwe28f7wwe28fm |
| 4 | 西进口 | 22 | 13wwe28f7wwe28fm |
| 1 | 南出口 | 12 | 13wwe28fmwwe28ct |
| 2 | 南出口 | 12 | 13wwe28fmwwe28ct |
| 3 | 南出口 | 11 | 13wwe28fmwwe28ct |
| 4 | 南出口 | 11 | 13wwe28fmwwe28ct |
| 5 | 南出口 | 13 | 13wwe28fmwwe28ct |
| 1 | 西出口 | 12 | 13wwe28fmwwe28f7 |
| 2 | 西出口 | 40 | 13wwe28fmwwe28f7 |
| … | +17 more |  |  |

### 2. 动态与聚合 / Dynamic & Aggregated (Monday profile)

#### 2.1 峰值评价槽位 / Peak evaluation slots

| step | time | sat_max | unbalance | LOS |
| --- | --- | --- | --- | --- |
| 287 | 23:55 | 0.0 | 0.1699 | A |
| 286 | 23:50 | 0.0 | 0.1699 | A |
| 285 | 23:45 | 0.0 | 0.1699 | A |

#### 2.2 峰值转向明细 / Peak turn movements

| dir | turn | saturation | green_util | queue_max_m | storage_m | queue_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| 北 | 直行 | 0.0 | None | None | None | None |
| 北 | 直行 | 0.0 | None | None | None | None |
| 北 | 左转 | 0.0 | None | None | None | None |
| 北 | 左转 | 0.0 | None | None | None | None |
| 北 | 左转 | 0.0 | None | None | None | None |
| 北 | 直行 | 0.0 | None | None | None | None |
| 北 | 左转 | 0.0 | None | None | None | None |
| 北 | 直行 | 0.0 | None | None | None | None |

#### 2.3 任务聚合指标 / Task-level metrics

| metric | value |
| --- | --- |
| saturation_max | None |
| imbalance_index / 失衡 | 0.0887 |
| queue_length_m / 排队 | None |
| storage_length_m / 进口道长 | None |
| green_utilization / 绿灯利用率 | 0.5561 |
| volume_vph / 流量 | None |
| capacity_vph / 能力 | None |

### 3. 配时信息 / Signal Timing

#### 3.1 日计划调度 / Day plan schedule (`dwd_ctl_inter_day_plan_schedule_cfg`)

| day_type | start | end | plan_no | plan_name |
| --- | --- | --- | --- | --- |
| None | 00:00:00 | 06:00:00 | None | None |
| None | 06:00:00 | 07:00:00 | None | None |
| None | 07:00:00 | 08:10:00 | None | None |
| None | 08:10:00 | 09:30:00 | None | None |
| None | 09:30:00 | 11:30:00 | None | None |
| None | 11:30:00 | 13:30:00 | None | None |
| None | 13:30:00 | 16:30:00 | None | None |
| None | 16:30:00 | 17:00:00 | None | None |
| None | 17:00:00 | 19:00:00 | None | None |
| None | 19:00:00 | 19:30:00 | None | None |
| None | 19:30:00 | 21:00:00 | None | None |
| None | 21:00:00 | 23:59:00 | None | None |
| … | +64 |  |  |  |

#### 3.2 配时方案 / Plans (`dwd_ctl_inter_plan_cfg` + `stage_timing`)


**方案 Plan 10** — 奥体西路与解放东路路口方案10 | cycle=160s | offset=127s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 43 | 3 | 0 | 14 | 60 |
| 2 | 2 | 27 | 3 | 0 | 14 | 60 |
| 3 | 3 | 42 | 3 | 0 | 14 | 60 |
| 4 | 5 | 16 | 3 | 0 | 14 | 60 |
| 5 | 4 | 17 | 3 | 0 | 7 | 60 |


**方案 Plan 11** — 奥体西路与解放东路路口方案11 | cycle=150s | offset=118s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 42 | 3 | 0 | 14 | 60 |
| 2 | 2 | 25 | 3 | 0 | 14 | 60 |
| 3 | 3 | 41 | 3 | 0 | 14 | 60 |
| 4 | 5 | 8 | 3 | 0 | 14 | 60 |
| 5 | 4 | 19 | 3 | 0 | 7 | 60 |


**方案 Plan 12** — 奥体西路与解放东路路口方案12 | cycle=150s | offset=118s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 42 | 3 | 0 | 14 | 60 |
| 2 | 2 | 25 | 3 | 0 | 14 | 60 |
| 3 | 3 | 40 | 3 | 0 | 14 | 60 |
| 4 | 5 | 8 | 3 | 0 | 14 | 60 |
| 5 | 4 | 20 | 3 | 0 | 7 | 60 |


**方案 Plan 13** — 奥体西路与解放东路路口方案13 | cycle=150s | offset=118s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 42 | 3 | 0 | 14 | 60 |
| 2 | 2 | 25 | 3 | 0 | 14 | 60 |
| 3 | 3 | 40 | 3 | 0 | 14 | 60 |
| 4 | 5 | 8 | 3 | 0 | 14 | 60 |
| 5 | 4 | 20 | 3 | 0 | 7 | 60 |


**方案 Plan 14** — 奥体西路与解放东路路口方案14 | cycle=150s | offset=118s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 44 | 3 | 0 | 14 | 60 |
| 2 | 2 | 28 | 3 | 0 | 14 | 60 |
| 3 | 3 | 41 | 3 | 0 | 14 | 60 |
| 4 | 5 | 2 | 3 | 0 | 14 | 60 |
| 5 | 4 | 20 | 3 | 0 | 7 | 60 |


_另有 11 个方案未展开 / 11 more plans omitted_

#### 3.3 阶段配置 / Stage cfg (`dwd_ctl_inter_stage_cfg`)

| stage_no | stage_name | phase_cnt | remark |
| --- | --- | --- | --- |
| 1 | 西直、东直、东右、南行人、北行人 | None |  |
| 2 | 东左、西左、东右 | None |  |
| 3 | 北直、南直、东右、西行人、东行人 | None |  |
| 4 | 南左、北左、东右 | None |  |
| 5 | 南左、南直、东右、东行人 | None |  |
| 6 | 北直、北左、南直、南左、东右、西行人、东行人 | None |  |
| 7 | 南直、东右、南左、东行人 | None |  |
| 8 | 北左、东右、南左 | None |  |
| 9 | 西直、东直、南行人、北行人 | None |  |
| 10 | 东左、西左 | None |  |
| 11 | 南直、南左、东行人 | None |  |
| 12 | 北直、南直、西行人、东行人 | None |  |
| 13 | 北左、南左 | None |  |

#### 3.4 最小绿 / Min green (`dwd_ctl_inter_min_green_cfg`)

| stage_no | min_green_sec | ped_min_green_sec |
| --- | --- | --- |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |

### 4. 流量溯源样本 / Flow correlate sample

| period | dir_turn | cor_inter | share | trace |
| --- | --- | --- | --- | --- |
| EVENING_PEAK | 0/1 | 解放东路与齐川路路口 | 86.29 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 茂岭山三号路与解放东路路口 | 70.22 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 解放东路与解放东路路口 | 69.88 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | None | 69.88 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 姚家东路与茂岭二号路路口 | 47.04 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 华阳路与解放东路路口 | 45.35 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 解放东路与文博西路路口 | 45.18 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 浆水泉路与解放东路路口 | 41.62 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 解放东路与解放东路路口 | 41.46 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 茂岭山路与解放东路路口 | 40.95 | DOWNSTREAM |


---

## 经十路与奥体西路 → 奥体西路与经十路路口 (`011wwe28ctu00001`)

### 1. 静态信息 / Static

#### 1.1 路口基础 / Basic

| 字段 Field | 值 Value |
| --- | --- |
| inter_id | 011wwe28ctu00001 |
| inter_name / 路口名称 | 奥体西路与经十路路口 |
| is_signalized / 信控 | 1 |
| inter_type / 类型 | inter |
| inter_proto / 原型 | 1 |
| entr_cnt / 进口数 | None |
| entr_dir8 / 八方向进口掩码 | None |
| version_id | None |

#### 1.2 渠化 / Channelization (`road6.dwd_tfc_rltn_wide_inter_ft_link`)

| 方向 Direction | role | lanes | turn_move | seq |
| --- | --- | --- | --- | --- |
|  | entrance | 8 | 12|12|12|11|11|11|11|11|11|11 | 1 |
|  | entrance | 5 | 12|12|11|11|13 | 1 |
|  | exit | 4 | 12|11|11|13 | 2 |
|  | entrance | 3 | 11|13 | 3 |
|  | exit | 6 | 11|11|11|11|11|11|11 | 5 |
|  | entrance | 4 | 32|12|11|22 | 6 |
|  | exit | 4 | 12|12|12|11 | 7 |
|  | entrance | 9 | 12|12|11|11|11|11|11|13|13 | 8 |
|  | exit | 7 | 12|12|11|11|11|11|11 | 9 |
|  | exit | 1 | 11 | 10 |

#### 1.3 相邻路口与进口道 / Adjacent & Approach (`adjacent_spacing`)

| 进口 Approach | length_m | road_level | adjacent | relation | lanes |
| --- | --- | --- | --- | --- | --- |
|  | 656.19 | None | 经十路与转山西路路口 | upstream | None |
|  | 668.66 | None | 经十路与转山西路路口 | upstream | None |
|  | 215.68 | None | 奥体西路与解放东路路口 | upstream | None |
|  | 367.89 | 3 | 奥体西路与解放东路路口 | upstream | 5.0 |
|  | 264.42 | 3 | 岔口 | upstream | 4.0 |
|  | 877.68 | 3 | 经十路与转山西路路口 | upstream | 9.0 |
|  | 714.45 | 3 | 奥体中路与经十路路口 | upstream | 8.0 |
|  | 1893.16 | 4 | 奥体中路与经十路路口 | upstream | 3.0 |

#### 1.4 车道明细 / Lane detail (`dim_inter_lane_detail`)

| lane_no | dir8 | turn | lane_id |
| --- | --- | --- | --- |
| 1 | 西进口 | 12 | 13wwe289qwwe28ct |
| 2 | 西进口 | 12 | 13wwe289qwwe28ct |
| 3 | 西进口 | 11 | 13wwe289qwwe28ct |
| 4 | 西进口 | 11 | 13wwe289qwwe28ct |
| 5 | 西进口 | 11 | 13wwe289qwwe28ct |
| 6 | 西进口 | 11 | 13wwe289qwwe28ct |
| 7 | 西进口 | 11 | 13wwe289qwwe28ct |
| 8 | 西进口 | 13 | 13wwe289qwwe28ct |
| 9 | 西进口 | 13 | 13wwe289qwwe28ct |
| 1 | 南进口 | 32 | 13wwe28cnwwe28ct |
| 2 | 南进口 | 12 | 13wwe28cnwwe28ct |
| 3 | 南进口 | 11 | 13wwe28cnwwe28ct |
| 4 | 南进口 | 22 | 13wwe28cnwwe28ct |
| 1 | 西出口 | 12 | 13wwe28ctwwe289q |
| 2 | 西出口 | 12 | 13wwe28ctwwe289q |
| … | +38 more |  |  |

### 2. 动态与聚合 / Dynamic & Aggregated (Monday profile)

#### 2.1 峰值评价槽位 / Peak evaluation slots

| step | time | sat_max | unbalance | LOS |
| --- | --- | --- | --- | --- |
| 83 | 06:55 | 5.0943 | 1.589 | F |
| 86 | 07:10 | 4.9057 | 1.5236 | F |
| 91 | 07:35 | 3.9429 | 1.245 | F |

#### 2.2 峰值转向明细 / Peak turn movements

| dir | turn | saturation | green_util | queue_max_m | storage_m | queue_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| 北 | 左转 | 5.0943 | None | None | None | None |
| 北 | 左转 | 1.5085 | None | None | None | None |
| 北 | 直行 | 1.3468 | None | None | None | None |
| 北 | 直行 | 0.8487 | None | None | None | None |
| 北 | 左转 | 0.7605 | None | None | None | None |
| 北 | 直行 | 0.4867 | None | None | None | None |
| 北 | 直行 | 0.0 | None | None | None | None |
| 北 | 左转 | 0.0 | None | None | None | None |

#### 2.3 任务聚合指标 / Task-level metrics

| metric | value |
| --- | --- |
| saturation_max | None |
| imbalance_index / 失衡 | 1.589 |
| queue_length_m / 排队 | None |
| storage_length_m / 进口道长 | None |
| green_utilization / 绿灯利用率 | 0.7999 |
| volume_vph / 流量 | None |
| capacity_vph / 能力 | None |

### 3. 配时信息 / Signal Timing

#### 3.1 日计划调度 / Day plan schedule (`dwd_ctl_inter_day_plan_schedule_cfg`)

| day_type | start | end | plan_no | plan_name |
| --- | --- | --- | --- | --- |
| None | 00:00:00 | 05:00:00 | None | None |
| None | 05:00:00 | 06:50:00 | None | None |
| None | 06:50:00 | 07:05:00 | None | None |
| None | 07:05:00 | 07:15:00 | None | None |
| None | 07:15:00 | 07:40:00 | None | None |
| None | 07:40:00 | 08:15:00 | None | None |
| None | 08:15:00 | 09:00:00 | None | None |
| None | 09:00:00 | 11:00:00 | None | None |
| None | 11:00:00 | 13:30:00 | None | None |
| None | 13:30:00 | 16:00:00 | None | None |
| None | 16:00:00 | 17:20:00 | None | None |
| None | 17:20:00 | 19:00:00 | None | None |
| … | +140 |  |  |  |

#### 3.2 配时方案 / Plans (`dwd_ctl_inter_plan_cfg` + `stage_timing`)


**方案 Plan 1** — 奥体西路与经十路路口方案1 | cycle=130s | offset=10s | stages=4

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 41 | 3 | 3 | 14 | 60 |
| 2 | 2 | 18 | 3 | 0 | 7 | 60 |
| 3 | 3 | 41 | 3 | 0 | 14 | 60 |
| 4 | 4 | 15 | 3 | 0 | 7 | 60 |


**方案 Plan 10** — 奥体西路与经十路路口方案10 | cycle=180s | offset=18s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 56 | 3 | 0 | 14 | 60 |
| 2 | 5 | 12 | 3 | 0 | 14 | 60 |
| 3 | 2 | 26 | 3 | 0 | 7 | 60 |
| 4 | 3 | 41 | 3 | 0 | 14 | 60 |
| 5 | 4 | 30 | 3 | 0 | 7 | 60 |


**方案 Plan 11** — 奥体西路与经十路路口方案11 | cycle=220s | offset=200s | stages=8

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 59 | 3 | 0 | 14 | 60 |
| 2 | 5 | 10 | 3 | 0 | 14 | 60 |
| 3 | 2 | 29 | 3 | 0 | 7 | 60 |
| 4 | 3 | 57 | 3 | 0 | 14 | 60 |
| 5 | 9 | 0 | 3 | 0 | 14 | 60 |
| 6 | 4 | 46 | 3 | 0 | 7 | 60 |
| 7 | 10 | 0 | 3 | 0 | 7 | 60 |
| 8 | 11 | 1 | 0 | 0 | 2 | 60 |


**方案 Plan 12** — 奥体西路与经十路路口方案12 | cycle=200s | offset=30s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 61 | 3 | 0 | 14 | 60 |
| 2 | 5 | 19 | 3 | 0 | 14 | 60 |
| 3 | 2 | 21 | 3 | 0 | 7 | 60 |
| 4 | 3 | 47 | 3 | 0 | 14 | 60 |
| 5 | 4 | 37 | 3 | 0 | 7 | 60 |


**方案 Plan 13** — 奥体西路与经十路路口方案13 | cycle=220s | offset=200s | stages=7

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 57 | 3 | 0 | 14 | 60 |
| 2 | 5 | 12 | 3 | 0 | 14 | 60 |
| 3 | 2 | 27 | 3 | 0 | 7 | 60 |
| 4 | 3 | 57 | 3 | 0 | 14 | 60 |
| 5 | 9 | 0 | 3 | 0 | 14 | 60 |
| 6 | 4 | 47 | 3 | 0 | 7 | 60 |
| 7 | 11 | 2 | 0 | 0 | 2 | 60 |


_另有 23 个方案未展开 / 23 more plans omitted_

#### 3.3 阶段配置 / Stage cfg (`dwd_ctl_inter_stage_cfg`)

| stage_no | stage_name | phase_cnt | remark |
| --- | --- | --- | --- |
| 1 | 西直、东直、南行人、北行人 | None |  |
| 2 | 东左、西左 | None |  |
| 3 | 北直、南直、西行人、东行人 | None |  |
| 4 | 南左、北左 | None |  |
| 5 | 西直、西左、南行人 | None |  |
| 6 | 南左、南直、东行人 | None |  |
| 7 | 西直、东直、北行人、南行人 | None |  |
| 8 | 西直、西左 | None |  |
| 9 | 北直、西行人 | None |  |
| 10 | 南左 | None |  |
| 11 | 空阶段11 | None | 源数据未解析出交通流组合 |

#### 3.4 最小绿 / Min green (`dwd_ctl_inter_min_green_cfg`)

| stage_no | min_green_sec | ped_min_green_sec |
| --- | --- | --- |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |

### 4. 流量溯源样本 / Flow correlate sample

| period | dir_turn | cor_inter | share | trace |
| --- | --- | --- | --- | --- |
| EVENING_PEAK | 0/1 | 经十路与转山西路路口 | 71.72 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 经十路辅路与洪山路路口 | 45.31 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 浆水泉路与经十路路口 | 22.81 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 二环东路辅路与经十路路口 | 20.39 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 二环东路辅路与经十路路口 | 18.75 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 燕子山中路与经十路路口 | 17.89 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 燕子山路与经十路路口 | 17.89 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 山大路与燕子山西路路口 | 13.59 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 环山路与经十路路口 | 12.97 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 山师东路与经十路路口 | 12.27 | DOWNSTREAM |


---

## 奥体中路与坤顺路 → 坤顺路与奥体中路路口 (`011wwe294sq00001`)

### 1. 静态信息 / Static

#### 1.1 路口基础 / Basic

| 字段 Field | 值 Value |
| --- | --- |
| inter_id | 011wwe294sq00001 |
| inter_name / 路口名称 | 坤顺路与奥体中路路口 |
| is_signalized / 信控 | 1 |
| inter_type / 类型 | inter |
| inter_proto / 原型 | 1 |
| entr_cnt / 进口数 | None |
| entr_dir8 / 八方向进口掩码 | None |
| version_id | None |

#### 1.2 渠化 / Channelization (`road6.dwd_tfc_rltn_wide_inter_ft_link`)

| 方向 Direction | role | lanes | turn_move | seq |
| --- | --- | --- | --- | --- |
|  | exit | 3 | 40|11|11|11|11 | 1 |
|  | entrance | 3 | 12|11|22 | 2 |
|  | exit | 2 | 12|24|13 | 3 |
|  | entrance | 3 | 40|32|11|11|23 | 4 |
|  | exit | 4 | 40|12|11|11|13 | 5 |
|  | entrance | 3 | 21|11|13 | 6 |
|  | exit | 1 | 21|22 | 7 |
|  | entrance | 5 | 40|32|11|11|13 | 8 |

#### 1.3 相邻路口与进口道 / Adjacent & Approach (`adjacent_spacing`)

| 进口 Approach | length_m | road_level | adjacent | relation | lanes |
| --- | --- | --- | --- | --- | --- |
|  | None | None | 解放东路与奥体中路路口 | upstream | None |
|  | None | None | 坤顺路与重德路路口 | upstream | None |
|  | 313.02 | None | 奥体中路与奥体中路路口 | upstream | None |
|  | 212.23 | 4 | 岔口 | upstream | 3.0 |
|  | 168.88 | 3 | 奥体中路与奥体中路路口 | upstream | 5.0 |
|  | 231.6 | 3 | 解放东路与奥体中路路口 | upstream | 3.0 |
|  | 245.51 | 4 | 坤顺路与重德路路口 | upstream | 3.0 |

#### 1.4 车道明细 / Lane detail (`dim_inter_lane_detail`)

| lane_no | dir8 | turn | lane_id |
| --- | --- | --- | --- |
| 1 | 西进口 | 21 | 13wwe294dwwe294s |
| 2 | 西进口 | 11 | 13wwe294dwwe294s |
| 3 | 西进口 | 13 | 13wwe294dwwe294s |
| 1 | 西北进口 | 40 | 13wwe294gwwe294s |
| 2 | 西北进口 | 32 | 13wwe294gwwe294s |
| 3 | 西北进口 | 11 | 13wwe294gwwe294s |
| 4 | 西北进口 | 11 | 13wwe294gwwe294s |
| 5 | 西北进口 | 13 | 13wwe294gwwe294s |
| 1 | 南进口 | 40 | 13wwe294kwwe294s |
| 2 | 南进口 | 32 | 13wwe294kwwe294s |
| 3 | 南进口 | 11 | 13wwe294kwwe294s |
| 4 | 南进口 | 11 | 13wwe294kwwe294s |
| 5 | 南进口 | 23 | 13wwe294kwwe294s |
| 1 | 西出口 | 21 | 13wwe294swwe294e |
| 2 | 西出口 | 22 | 13wwe294swwe294e |
| … | +16 more |  |  |

### 2. 动态与聚合 / Dynamic & Aggregated (Monday profile)

#### 2.1 峰值评价槽位 / Peak evaluation slots

| step | time | sat_max | unbalance | LOS |
| --- | --- | --- | --- | --- |
| 93 | 07:45 | 1.9634 | 0.5714 | F |
| 92 | 07:40 | 1.9634 | 0.4963 | F |
| 216 | 18:00 | 1.9343 | 0.5705 | F |

#### 2.2 峰值转向明细 / Peak turn movements

| dir | turn | saturation | green_util | queue_max_m | storage_m | queue_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| 北 | 直行 | 1.9634 | None | None | None | None |
| 北 | 左转 | 0.748 | None | None | None | None |
| 北 | 左转 | 0.7407 | None | None | None | None |
| 北 | 左转 | 0.5658 | None | None | None | None |
| 北 | 直行 | 0.5556 | None | None | None | None |
| 北 | 直行 | 0.3961 | None | None | None | None |

#### 2.3 任务聚合指标 / Task-level metrics

| metric | value |
| --- | --- |
| saturation_max | None |
| imbalance_index / 失衡 | 0.4963 |
| queue_length_m / 排队 | None |
| storage_length_m / 进口道长 | None |
| green_utilization / 绿灯利用率 | 0.5412 |
| volume_vph / 流量 | None |
| capacity_vph / 能力 | None |

### 3. 配时信息 / Signal Timing

#### 3.1 日计划调度 / Day plan schedule (`dwd_ctl_inter_day_plan_schedule_cfg`)

| day_type | start | end | plan_no | plan_name |
| --- | --- | --- | --- | --- |
| None | 00:00:00 | 06:00:00 | None | None |
| None | 06:00:00 | 07:00:00 | None | None |
| None | 07:00:00 | 07:30:00 | None | None |
| None | 07:30:00 | 08:30:00 | None | None |
| None | 08:30:00 | 10:00:00 | None | None |
| None | 10:00:00 | 11:30:00 | None | None |
| None | 11:30:00 | 13:30:00 | None | None |
| None | 13:30:00 | 16:30:00 | None | None |
| None | 16:30:00 | 17:30:00 | None | None |
| None | 17:30:00 | 18:30:00 | None | None |
| None | 18:30:00 | 19:30:00 | None | None |
| None | 19:30:00 | 21:00:00 | None | None |
| … | +69 |  |  |  |

#### 3.2 配时方案 / Plans (`dwd_ctl_inter_plan_cfg` + `stage_timing`)


**方案 Plan 10** — 坤顺路与奥体中路路口方案10 | cycle=150s | offset=55s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 6 | 71 | 3 | 0 | 70 | 100 |
| 2 | 3 | 30 | 3 | 0 | 30 | 60 |
| 3 | 4 | 37 | 3 | 3 | 32 | 60 |


**方案 Plan 11** — 坤顺路与奥体中路路口方案11 | cycle=100s | offset=50s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 45 | 3 | 0 | 14 | 60 |
| 2 | 7 | 11 | 3 | 9 | 14 | 60 |
| 3 | 4 | 24 | 3 | 0 | 14 | 60 |


**方案 Plan 12** — 坤顺路与奥体中路路口方案12 | cycle=130s | offset=43s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 59 | 3 | 9 | 14 | 60 |
| 2 | 3 | 19 | 3 | 0 | 14 | 60 |
| 3 | 4 | 29 | 3 | 0 | 14 | 60 |


**方案 Plan 13** — 坤顺路与奥体中路路口方案13 | cycle=160s | offset=52s | stages=4

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 73 | 3 | 0 | 14 | 60 |
| 2 | 2 | 10 | 3 | 0 | 14 | 60 |
| 3 | 3 | 24 | 3 | 0 | 14 | 60 |
| 4 | 4 | 33 | 3 | 0 | 14 | 60 |


**方案 Plan 15** — 坤顺路与奥体中路路口方案15 | cycle=180s | offset=110s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 82 | 3 | 9 | 14 | 60 |
| 2 | 3 | 26 | 3 | 0 | 14 | 60 |
| 3 | 8 | 10 | 0 | 0 | 14 | 60 |
| 4 | 4 | 17 | 3 | 0 | 14 | 60 |
| 5 | 9 | 19 | 3 | 0 | 14 | 60 |


_另有 9 个方案未展开 / 9 more plans omitted_

#### 3.3 阶段配置 / Stage cfg (`dwd_ctl_inter_stage_cfg`)

| stage_no | stage_name | phase_cnt | remark |
| --- | --- | --- | --- |
| 1 | 北直、南直、东行人、西行人 | None |  |
| 2 | 北直、南直 | None |  |
| 3 | 南左、北左 | None |  |
| 4 | 西直、西左、东直、东左、南行人、北行人 | None |  |
| 5 | 空阶段5 | None | 源数据未解析出交通流组合 |
| 6 | 北直、南直、西行人、东行人 | None |  |
| 7 | 南左、北左、东行人、西行人 | None |  |
| 8 | 西直、西左、南行人 | None |  |
| 9 | 东直、东左、北行人 | None |  |
| 10 | 南直、东行人、西行人 | None |  |

#### 3.4 最小绿 / Min green (`dwd_ctl_inter_min_green_cfg`)

| stage_no | min_green_sec | ped_min_green_sec |
| --- | --- | --- |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |

### 4. 流量溯源样本 / Flow correlate sample

| period | dir_turn | cor_inter | share | trace |
| --- | --- | --- | --- | --- |
| EVENING_PEAK | 0/1 | 坤顺路与重德路路口 | 81.33 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 坤顺路与礼耕路路口 | 48.0 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 坤顺路与奥体西路路口 | 20.0 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 坤顺路与奥体西路路口 | 16.0 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 安成街与奥体西路路口 | 12.0 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 礼耕路与解放东路路口 | 10.67 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 坤顺路与礼耕路路口 | 10.67 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 坤顺路与无名道路路口 | 10.67 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 坤顺路与奥体西路路口 | 9.33 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 奥体西路与新泺大街路口 | 8.0 | DOWNSTREAM |


---

## 奥体中路与解放东路 → 解放东路与奥体中路路口 (`011wwe294k300001`)

### 1. 静态信息 / Static

#### 1.1 路口基础 / Basic

| 字段 Field | 值 Value |
| --- | --- |
| inter_id | 011wwe294k300001 |
| inter_name / 路口名称 | 解放东路与奥体中路路口 |
| is_signalized / 信控 | 1 |
| inter_type / 类型 | inter |
| inter_proto / 原型 | 1 |
| entr_cnt / 进口数 | None |
| entr_dir8 / 八方向进口掩码 | None |
| version_id | None |

#### 1.2 渠化 / Channelization (`road6.dwd_tfc_rltn_wide_inter_ft_link`)

| 方向 Direction | role | lanes | turn_move | seq |
| --- | --- | --- | --- | --- |
|  | entrance | 4 | 40|12|11|11|13 | 1 |
|  | exit | 3 | 40|32|11|11|23 | 2 |
|  | entrance | 5 | 12|11|11|22|13 | 3 |
|  | exit | 4 | 12|12|12|13 | 4 |
|  | entrance | 4 | 12|12|24|13 | 5 |
|  | exit | 3 | 11|11|22 | 6 |

#### 1.3 相邻路口与进口道 / Adjacent & Approach (`adjacent_spacing`)

| 进口 Approach | length_m | road_level | adjacent | relation | lanes |
| --- | --- | --- | --- | --- | --- |
|  | 234.69 | 3 | 坤顺路与奥体中路路口 | upstream | 4.0 |
|  | 336.16 | 3 | 奥体中路与经十路路口 | upstream | 5.0 |
|  | 241.22 | 3 | 解放东路与重德路路口 | upstream | 4.0 |

#### 1.4 车道明细 / Lane detail (`dim_inter_lane_detail`)

| lane_no | dir8 | turn | lane_id |
| --- | --- | --- | --- |
| 1 | 南进口 | 12 | 13wwe291uwwe294k |
| 2 | 南进口 | 11 | 13wwe291uwwe294k |
| 3 | 南进口 | 11 | 13wwe291uwwe294k |
| 4 | 南进口 | 22 | 13wwe291uwwe294k |
| 5 | 南进口 | 13 | 13wwe291uwwe294k |
| 1 | 西进口 | 12 | 13wwe2946wwe294k |
| 2 | 西进口 | 12 | 13wwe2946wwe294k |
| 3 | 西进口 | 24 | 13wwe2946wwe294k |
| 4 | 西进口 | 13 | 13wwe2946wwe294k |
| 1 | 南出口 | 12 | 13wwe294kwwe291e |
| 2 | 南出口 | 12 | 13wwe294kwwe291e |
| 3 | 南出口 | 12 | 13wwe294kwwe291e |
| 4 | 南出口 | 13 | 13wwe294kwwe291e |
| 1 | 西出口 | 11 | 13wwe294kwwe2946 |
| 2 | 西出口 | 11 | 13wwe294kwwe2946 |
| … | +11 more |  |  |

### 2. 动态与聚合 / Dynamic & Aggregated (Monday profile)

#### 2.1 峰值评价槽位 / Peak evaluation slots

| step | time | sat_max | unbalance | LOS |
| --- | --- | --- | --- | --- |
| 87 | 07:15 | 2.7365 | 0.913 | F |
| 89 | 07:25 | 2.7074 | 0.8029 | F |
| 95 | 07:55 | 2.6783 | 0.8247 | F |

#### 2.2 峰值转向明细 / Peak turn movements

| dir | turn | saturation | green_util | queue_max_m | storage_m | queue_ratio |
| --- | --- | --- | --- | --- | --- | --- |
| 北 | 直行 | 2.7365 | None | None | None | None |
| 北 | 左转 | 1.4658 | None | None | None | None |
| 北 | 左转 | 0.8511 | None | None | None | None |
| 北 | 直行 | 0.5062 | None | None | None | None |
| 北 | 左转 | 0.0 | None | None | None | None |

#### 2.3 任务聚合指标 / Task-level metrics

| metric | value |
| --- | --- |
| saturation_max | None |
| imbalance_index / 失衡 | 0.913 |
| queue_length_m / 排队 | None |
| storage_length_m / 进口道长 | None |
| green_utilization / 绿灯利用率 | 0.8708 |
| volume_vph / 流量 | None |
| capacity_vph / 能力 | None |

### 3. 配时信息 / Signal Timing

#### 3.1 日计划调度 / Day plan schedule (`dwd_ctl_inter_day_plan_schedule_cfg`)

| day_type | start | end | plan_no | plan_name |
| --- | --- | --- | --- | --- |
| None | 00:00:00 | 06:00:00 | None | None |
| None | 06:00:00 | 07:00:00 | None | None |
| None | 07:00:00 | 08:30:00 | None | None |
| None | 08:30:00 | 09:30:00 | None | None |
| None | 09:30:00 | 10:00:00 | None | None |
| None | 10:00:00 | 11:30:00 | None | None |
| None | 11:30:00 | 13:30:00 | None | None |
| None | 13:30:00 | 16:30:00 | None | None |
| None | 16:30:00 | 19:30:00 | None | None |
| None | 19:30:00 | 21:00:00 | None | None |
| None | 21:00:00 | 23:59:00 | None | None |
| None | 00:00:00 | 06:00:00 | None | None |
| … | +59 |  |  |  |

#### 3.2 配时方案 / Plans (`dwd_ctl_inter_plan_cfg` + `stage_timing`)


**方案 Plan 10** — 解放东路与奥体中路路口方案10 | cycle=150s | offset=0s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 18 | 3 | 0 | 14 | 60 |
| 2 | 2 | 39 | 3 | 0 | 14 | 60 |
| 3 | 3 | 47 | 3 | 0 | 14 | 60 |
| 4 | 4 | 4 | 3 | 0 | 14 | 60 |
| 5 | 5 | 20 | 3 | 0 | 14 | 60 |


**方案 Plan 11** — 解放东路与奥体中路路口方案11 | cycle=130s | offset=0s | stages=4

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 6 | 42 | 3 | 0 | 14 | 60 |
| 2 | 3 | 47 | 3 | 0 | 14 | 60 |
| 3 | 4 | 4 | 3 | 0 | 14 | 60 |
| 4 | 5 | 21 | 3 | 0 | 14 | 60 |


**方案 Plan 12** — 解放东路与奥体中路路口方案12 | cycle=160s | offset=0s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 22 | 3 | 0 | 14 | 60 |
| 2 | 2 | 36 | 3 | 0 | 14 | 60 |
| 3 | 3 | 47 | 3 | 0 | 14 | 60 |
| 4 | 4 | 10 | 3 | 0 | 14 | 60 |
| 5 | 5 | 23 | 3 | 0 | 14 | 60 |


**方案 Plan 13** — 解放东路与奥体中路路口方案13 | cycle=100s | offset=20s | stages=3

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 6 | 27 | 3 | 0 | 14 | 60 |
| 2 | 3 | 46 | 3 | 0 | 14 | 60 |
| 3 | 7 | 14 | 3 | 0 | 14 | 60 |


**方案 Plan 15** — 解放东路与奥体中路路口方案15 | cycle=160s | offset=0s | stages=6

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 19 | 3 | 0 | 14 | 60 |
| 2 | 8 | 1 | 3 | 0 | 14 | 60 |
| 3 | 9 | 36 | 3 | 0 | 14 | 60 |
| 4 | 3 | 47 | 3 | 0 | 14 | 60 |
| 5 | 4 | 3 | 3 | 0 | 14 | 60 |
| 6 | 5 | 28 | 3 | 0 | 14 | 60 |


_另有 5 个方案未展开 / 5 more plans omitted_

#### 3.3 阶段配置 / Stage cfg (`dwd_ctl_inter_stage_cfg`)

| stage_no | stage_name | phase_cnt | remark |
| --- | --- | --- | --- |
| 1 | 东直左、北行人 | None |  |
| 2 | 西直左、南行人、北行人 | None |  |
| 3 | 北直、南直、东行人、西行人 | None |  |
| 4 | 北直、南直 | None |  |
| 5 | 南左、北左 | None |  |
| 6 | 东直左、西直左、南行人、北行人 | None |  |
| 7 | 南左、北左、东行人、西行人 | None |  |
| 8 | 东直左、北行人、南行人 | None |  |
| 9 | 西直左、北行人、南行人 | None |  |
| 10 | 南左、南直 | None |  |

#### 3.4 最小绿 / Min green (`dwd_ctl_inter_min_green_cfg`)

| stage_no | min_green_sec | ped_min_green_sec |
| --- | --- | --- |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |

### 4. 流量溯源样本 / Flow correlate sample

| period | dir_turn | cor_inter | share | trace |
| --- | --- | --- | --- | --- |
| EVENING_PEAK | 0/1 | 解放东路与重德路路口 | 95.47 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 礼耕路与解放东路路口 | 94.26 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 奥体西路与解放东路路口 | 82.48 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 解放东路与齐川路路口 | 78.55 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 茂岭山三号路与解放东路路口 | 55.89 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 解放东路与解放东路路口 | 55.59 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | None | 55.59 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 姚家东路与茂岭二号路路口 | 42.9 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 华阳路与解放东路路口 | 40.79 | DOWNSTREAM |
| EVENING_PEAK | 0/1 | 解放东路与文博西路路口 | 40.48 | DOWNSTREAM |


---

## 奥体中路与经十路 → 奥体中路与经十路路口 (`011wwe291ey00001`)

### 1. 静态信息 / Static

#### 1.1 路口基础 / Basic

| 字段 Field | 值 Value |
| --- | --- |
| inter_id | 011wwe291ey00001 |
| inter_name / 路口名称 | 奥体中路与经十路路口 |
| is_signalized / 信控 | 1 |
| inter_type / 类型 | inter |
| inter_proto / 原型 | 1 |
| entr_cnt / 进口数 | None |
| entr_dir8 / 八方向进口掩码 | None |
| version_id | None |

#### 1.2 渠化 / Channelization (`road6.dwd_tfc_rltn_wide_inter_ft_link`)

| 方向 Direction | role | lanes | turn_move | seq |
| --- | --- | --- | --- | --- |
|  | exit | 8 | 12|12|12|11|11|11|11|11|11|11 | 1 |
|  | entrance | 4 | 12|12|12|13 | 1 |
|  | entrance | 2 | 11|99 | 2 |
|  | entrance | 5 | 11|11|11|11|11 | 3 |
|  | exit | 3 | 11|13 | 5 |

#### 1.3 相邻路口与进口道 / Adjacent & Approach (`adjacent_spacing`)

| 进口 Approach | length_m | road_level | adjacent | relation | lanes |
| --- | --- | --- | --- | --- | --- |
|  | 740.68 | None | 经十路辅路与草山岭西路路口 | upstream | None |
|  | 567.76 | None | 奥体中路与经十路路口 | upstream | None |
|  | 348.28 | 3 | 解放东路与奥体中路路口 | upstream | 4.0 |
|  | 118.64 | 4 | 奥体中路与经十路路口 | upstream | 2.0 |
|  | 116.18 | 3 | 奥体中路与经十路路口 | upstream | 5.0 |

#### 1.4 车道明细 / Lane detail (`dim_inter_lane_detail`)

| lane_no | dir8 | turn | lane_id |
| --- | --- | --- | --- |
| 1 | 西出口 | 12 | 13wwe291ewwe28ct |
| 2 | 西出口 | 12 | 13wwe291ewwe28ct |
| 3 | 西出口 | 12 | 13wwe291ewwe28ct |
| 4 | 西出口 | 11 | 13wwe291ewwe28ct |
| 5 | 西出口 | 11 | 13wwe291ewwe28ct |
| 6 | 西出口 | 11 | 13wwe291ewwe28ct |
| 7 | 西出口 | 11 | 13wwe291ewwe28ct |
| 8 | 西出口 | 11 | 13wwe291ewwe28ct |
| 9 | 西出口 | 11 | 13wwe291ewwe28ct |
| 10 | 西出口 | 11 | 13wwe291ewwe28ct |
| 1 | 西出口 | 11 | 13wwe291ewwe28ct |
| 2 | 西出口 | 13 | 13wwe291ewwe28ct |
| 1 | 东进口 | 11 | 13wwe291swwe291e |
| 2 | 东进口 | 11 | 13wwe291swwe291e |
| 3 | 东进口 | 11 | 13wwe291swwe291e |
| … | +8 more |  |  |

### 2. 动态与聚合 / Dynamic & Aggregated (Monday profile)

#### 2.1 峰值评价槽位 / Peak evaluation slots

_（无数据 / No data）_

#### 2.2 峰值转向明细 / Peak turn movements

_（无数据 / No data）_

#### 2.3 任务聚合指标 / Task-level metrics

| metric | value |
| --- | --- |
| saturation_max | None |
| imbalance_index / 失衡 | 0.0 |
| queue_length_m / 排队 | None |
| storage_length_m / 进口道长 | None |
| green_utilization / 绿灯利用率 | 0.0 |
| volume_vph / 流量 | None |
| capacity_vph / 能力 | None |

### 3. 配时信息 / Signal Timing

#### 3.1 日计划调度 / Day plan schedule (`dwd_ctl_inter_day_plan_schedule_cfg`)

| day_type | start | end | plan_no | plan_name |
| --- | --- | --- | --- | --- |
| None | 00:00:00 | 05:00:00 | None | None |
| None | 05:00:00 | 06:50:00 | None | None |
| None | 06:50:00 | 07:15:00 | None | None |
| None | 07:15:00 | 07:40:00 | None | None |
| None | 07:40:00 | 08:30:00 | None | None |
| None | 08:30:00 | 09:00:00 | None | None |
| None | 09:00:00 | 11:00:00 | None | None |
| None | 11:00:00 | 13:30:00 | None | None |
| None | 13:30:00 | 16:00:00 | None | None |
| None | 16:00:00 | 17:30:00 | None | None |
| None | 17:30:00 | 18:30:00 | None | None |
| None | 18:30:00 | 19:00:00 | None | None |
| … | +82 |  |  |  |

#### 3.2 配时方案 / Plans (`dwd_ctl_inter_plan_cfg` + `stage_timing`)


**方案 Plan 1** — 奥体中路与经十路路口方案1 | cycle=130s | offset=45s | stages=4

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 54 | 3 | 0 | 14 | 60 |
| 2 | 2 | 15 | 0 | 0 | 14 | 60 |
| 3 | 3 | 9 | 3 | 0 | 14 | 60 |
| 4 | 4 | 34 | 3 | 0 | 14 | 60 |


**方案 Plan 10** — 奥体中路与经十路路口方案10 | cycle=200s | offset=70s | stages=6

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 52 | 3 | 0 | 14 | 60 |
| 2 | 1 | 37 | 3 | 0 | 14 | 60 |
| 3 | 6 | 18 | 0 | 0 | 14 | 60 |
| 4 | 7 | 11 | 3 | 0 | 14 | 60 |
| 5 | 8 | 7 | 3 | 0 | 14 | 60 |
| 6 | 4 | 54 | 3 | 0 | 14 | 60 |


**方案 Plan 11** — 奥体中路与经十路路口方案11 | cycle=220s | offset=95s | stages=5

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 57 | 3 | 0 | 14 | 60 |
| 2 | 1 | 45 | 3 | 0 | 14 | 60 |
| 3 | 6 | 16 | 3 | 0 | 14 | 60 |
| 4 | 8 | 27 | 3 | 0 | 14 | 60 |
| 5 | 4 | 54 | 3 | 0 | 14 | 60 |


**方案 Plan 12** — 奥体中路与经十路路口方案12 | cycle=200s | offset=70s | stages=6

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 64 | 3 | 0 | 14 | 60 |
| 2 | 1 | 34 | 3 | 0 | 14 | 60 |
| 3 | 6 | 18 | 0 | 0 | 14 | 60 |
| 4 | 7 | 12 | 3 | 0 | 14 | 60 |
| 5 | 8 | 7 | 3 | 0 | 14 | 60 |
| 6 | 4 | 44 | 3 | 0 | 14 | 60 |


**方案 Plan 13** — 奥体中路与经十路路口方案13 | cycle=220s | offset=215s | stages=6

| seq | stage_no | green | yellow | all_red | min_g | max_g |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 5 | 57 | 3 | 0 | 14 | 60 |
| 2 | 1 | 42 | 3 | 0 | 14 | 60 |
| 3 | 6 | 20 | 0 | 0 | 14 | 60 |
| 4 | 7 | 17 | 3 | 0 | 14 | 60 |
| 5 | 8 | 9 | 3 | 0 | 14 | 60 |
| 6 | 4 | 54 | 3 | 0 | 14 | 60 |


_另有 23 个方案未展开 / 23 more plans omitted_

#### 3.3 阶段配置 / Stage cfg (`dwd_ctl_inter_stage_cfg`)

| stage_no | stage_name | phase_cnt | remark |
| --- | --- | --- | --- |
| 1 | 东直、西直、东直、北出行、北入行 | None |  |
| 2 | 东直、西左、西直、北入行 | None |  |
| 3 | 东直、东掉、西左、西直、北入行 | None |  |
| 4 | 北左、西左、西直、西行人 | None |  |
| 5 | 西直、东直、西左、北入行 | None |  |
| 6 | 东直、东直、西直、北出行、北入行 | None |  |
| 7 | 东直、东直、东掉、西直、北出行、北入行 | None |  |
| 8 | 东掉、西左、西直、西行人 | None |  |

#### 3.4 最小绿 / Min green (`dwd_ctl_inter_min_green_cfg`)

| stage_no | min_green_sec | ped_min_green_sec |
| --- | --- | --- |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |
| None | None | None |

### 4. 流量溯源样本 / Flow correlate sample

| period | dir_turn | cor_inter | share | trace |
| --- | --- | --- | --- | --- |
| EVENING_PEAK | 2/2 | 奥体中路与经十路路口 | 80.89 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 经十路辅路与草山岭西路路口 | 74.84 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 草山岭中路与草山岭南路路口 | 71.22 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 经十路与舜华路路口 | 50.94 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 凤凰路与经十路路口 | 40.98 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 凤山路与经十路路口 | 27.69 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 凤岐路与经十路路口 | 26.37 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 奥体中路与经十路路口 | 18.46 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 解放东路与奥体中路路口 | 16.0 | DOWNSTREAM |
| EVENING_PEAK | 2/2 | 经十路与雪山路路口 | 14.91 | DOWNSTREAM |

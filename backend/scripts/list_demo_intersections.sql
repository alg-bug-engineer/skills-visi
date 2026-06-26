-- 演示路口筛选：数据完备、可跑问题验证证据 + 约束量化全链路
-- 用法：psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE -f scripts/list_demo_intersections.sql
SET search_path TO road6, xianchang, public;

-- 全库日历边界（筛选前先看）
SELECT
  'dwd_perf' AS source,
  MIN(stat_time::date) AS date_from,
  MAX(stat_time::date) AS date_to,
  COUNT(DISTINCT inter_id) AS inter_cnt
FROM xianchang.dwd_tfc_inter_dir_perf_5min
WHERE is_deleted = 0
UNION ALL
SELECT
  'lane_flow',
  TO_DATE(MIN(dt), 'YYYYMMDD'),
  TO_DATE(MAX(dt), 'YYYYMMDD'),
  COUNT(DISTINCT inter_id)
FROM xianchang.dwd_tfc_lane_roadcross_flow_5mi
WHERE is_deleted = 0;

-- 完备度评分（晚高峰 step 192-215 = 16:00-18:00）
WITH dwd AS (
  SELECT inter_id,
         COUNT(*) AS dwd_cnt,
         MIN(stat_time::date) AS dwd_date_from,
         MAX(stat_time::date) AS dwd_date_to,
         COUNT(DISTINCT stat_time::date) AS dwd_days,
         MAX(queue_len_max) AS max_queue
  FROM xianchang.dwd_tfc_inter_dir_perf_5min
  WHERE is_deleted = 0
  GROUP BY inter_id
),
dws_dir AS (
  SELECT inter_id,
         COUNT(*) AS dws_dir_cnt,
         COUNT(DISTINCT f_dir_8_label) AS dir_labels
  FROM xianchang.dws_inter_dir_turn_perf_5min_mm
  WHERE is_deleted = 0
  GROUP BY inter_id
),
dws_eval AS (
  SELECT inter_id,
         COUNT(*) AS eval_cnt,
         AVG(saturation_max) AS avg_sat_max,
         AVG(unbalance_index) AS avg_imbalance
  FROM xianchang.dws_inter_evaluation_5min_mm
  WHERE is_deleted = 0
    AND step_index BETWEEN 192 AND 215
  GROUP BY inter_id
),
flow AS (
  SELECT inter_id,
         COUNT(*) AS flow_cnt,
         MIN(dt) AS flow_dt_from,
         MAX(dt) AS flow_dt_to
  FROM xianchang.dwd_tfc_lane_roadcross_flow_5mi
  WHERE is_deleted = 0
  GROUP BY inter_id
),
ctl AS (
  SELECT inter_id, COUNT(*) AS ctl_cnt
  FROM xianchang.dwd_ctl_inter_plan_cfg
  WHERE is_deleted = 0
  GROUP BY inter_id
),
scored AS (
  SELECT i.inter_id,
         i.inter_name,
         d.dwd_cnt,
         d.dwd_date_from,
         d.dwd_date_to,
         d.max_queue,
         dd.dws_dir_cnt,
         dd.dir_labels,
         e.eval_cnt,
         ROUND(e.avg_sat_max::numeric, 3) AS avg_sat_max,
         ROUND(e.avg_imbalance::numeric, 3) AS avg_imbalance,
         f.flow_cnt,
         c.ctl_cnt,
         (CASE WHEN d.dwd_cnt > 0 THEN 40 ELSE 0 END
          + CASE WHEN dd.dws_dir_cnt > 0 THEN 25 ELSE 0 END
          + CASE WHEN e.eval_cnt > 0 THEN 15 ELSE 0 END
          + CASE WHEN f.flow_cnt > 0 THEN 10 ELSE 0 END
          + CASE WHEN c.ctl_cnt > 0 THEN 10 ELSE 0 END
          + CASE WHEN d.max_queue >= 100 THEN 5 ELSE 0 END
          + CASE WHEN e.avg_sat_max >= 0.8 THEN 5 ELSE 0 END
         ) AS completeness_score
  FROM road6.dim_inter_info i
  LEFT JOIN dwd d ON i.inter_id = d.inter_id
  LEFT JOIN dws_dir dd ON i.inter_id = dd.inter_id
  LEFT JOIN dws_eval e ON i.inter_id = e.inter_id
  LEFT JOIN flow f ON i.inter_id = f.inter_id
  LEFT JOIN ctl c ON i.inter_id = c.inter_id
  WHERE i.version_id = '20260501'
    AND i.is_signalized = 1
)
SELECT *
FROM scored
WHERE dwd_cnt > 0
  AND dws_dir_cnt > 0
  AND eval_cnt > 0
ORDER BY completeness_score DESC, dwd_cnt DESC
LIMIT 20;

-- 常发性拥堵（晚高峰 >=4 日超标）
WITH daily AS (
  SELECT inter_id,
         stat_time::date AS d,
         AVG(stop_time) AS avg_stop,
         MAX(queue_len_max) AS max_q
  FROM xianchang.dwd_tfc_inter_dir_perf_5min
  WHERE is_deleted = 0
    AND stat_time::time >= '16:00'
    AND stat_time::time < '18:00'
  GROUP BY 1, 2
)
SELECT c.inter_id,
       i.inter_name,
       c.congested_days,
       c.total_days,
       c.peak_queue
FROM (
  SELECT inter_id,
         COUNT(*) FILTER (WHERE avg_stop >= 60 OR max_q >= 100) AS congested_days,
         COUNT(*) AS total_days,
         MAX(max_q) AS peak_queue
  FROM daily
  GROUP BY inter_id
  HAVING COUNT(*) FILTER (WHERE avg_stop >= 60 OR max_q >= 100) >= 4
) c
JOIN road6.dim_inter_info i
  ON i.inter_id = c.inter_id AND i.version_id = '20260501'
ORDER BY congested_days DESC, peak_queue DESC
LIMIT 15;

-- 单路口自检（替换路口名）
SELECT i.inter_id,
       i.inter_name,
       EXISTS (SELECT 1 FROM xianchang.dwd_tfc_inter_dir_perf_5min d
               WHERE d.inter_id = i.inter_id AND d.is_deleted = 0) AS has_dwd,
       EXISTS (SELECT 1 FROM xianchang.dws_inter_dir_turn_perf_5min_mm s
               WHERE s.inter_id = i.inter_id AND s.is_deleted = 0) AS has_dws_dir,
       EXISTS (SELECT 1 FROM xianchang.dws_inter_evaluation_5min_mm e
               WHERE e.inter_id = i.inter_id AND e.is_deleted = 0) AS has_eval,
       EXISTS (SELECT 1 FROM xianchang.dwd_tfc_lane_roadcross_flow_5mi f
               WHERE f.inter_id = i.inter_id AND f.is_deleted = 0) AS has_flow,
       EXISTS (SELECT 1 FROM xianchang.dwd_ctl_inter_plan_cfg c
               WHERE c.inter_id = i.inter_id AND c.is_deleted = 0) AS has_ctl
FROM road6.dim_inter_info i
WHERE i.version_id = '20260501'
  AND i.inter_name LIKE '%奥体中路%新泺大街%';

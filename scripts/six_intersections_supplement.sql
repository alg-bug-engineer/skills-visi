-- =========================================================================
-- 六路口补充统计 SQL（排队/进口道长度口径对齐 溢流路口统计优化.sql）
-- 覆盖：相邻路口间距、排队、溢流比例、分时段态势指标
-- 禁止直接读取 rid_length_m / f_dist_m 作为进口道长度
-- =========================================================================

-- 公共 CTE：进口方向物理间距（相邻路口间距 adjacent_inter_spacing_m）
-- 逻辑来源：analysis/溢流路口统计优化.sql
WITH direction_spacing AS (
    SELECT
        w.inter_id,
        (CAST(w.dir8_code AS INTEGER) + 1) AS eight_direction,
        MIN(l.length_m) AS adjacent_inter_spacing_m
    FROM road6.dwd_tfc_rltn_wide_inter_ft_link w
    JOIN road6.dim_link_info l
      ON w.link_id = l.link_id
     AND l.version_id = w.version_id
    WHERE LOWER(w.link_role) = 'entrance'
    GROUP BY w.inter_id, w.dir8_code
    HAVING MIN(l.length_m) >= 50.0
),
target_inters AS (
    SELECT unnest(ARRAY[
        '011wwe28fty00001', -- 坤顺路与奥体西路
        '011wwe28fmc00001', -- 奥体西路与解放东路
        '011wwe28ctu00001', -- 奥体西路与经十路
        '011wwe294sq00001', -- 坤顺路与奥体中路
        '011wwe294k300001', -- 解放东路与奥体中路
        '011wwe291ey00001'  -- 奥体中路与经十路
    ]) AS inter_id
)

-- 1) 进口道长度（相邻路口间距）静态锚定
SELECT
    ds.inter_id,
    di.inter_name,
    ds.eight_direction,
    ds.adjacent_inter_spacing_m AS approach_spacing_m
FROM direction_spacing ds
JOIN target_inters ti ON ti.inter_id = ds.inter_id
LEFT JOIN road6.dim_inter_info di
  ON di.inter_id = ds.inter_id
 AND di.version_id = '20260501'
ORDER BY ds.inter_id, ds.eight_direction;

-- 2) 排队 + 溢流比例（DWD 时序 × direction_spacing）
-- queue_len_avg / adjacent_inter_spacing_m = overflow_risk_ratio
SELECT
    d.inter_id,
    di.inter_name,
    d.eight_direction,
    d.turn_dir_no,
    d.stat_time,
    d.queue_len_avg,
    ds.adjacent_inter_spacing_m,
    ds.adjacent_inter_spacing_m * 0.8 AS overflow_threshold_m,
    d.queue_len_avg / ds.adjacent_inter_spacing_m AS overflow_risk_ratio
FROM xianchang.dwd_tfc_inter_dir_perf_5min d
JOIN direction_spacing ds
  ON d.inter_id = ds.inter_id
 AND d.eight_direction = ds.eight_direction
JOIN target_inters ti ON ti.inter_id = d.inter_id
LEFT JOIN road6.dim_inter_info di
  ON di.inter_id = d.inter_id
 AND di.version_id = '20260501'
WHERE d.is_deleted = 0
  AND d.turn_dir_no != 0;

-- 3) DWS 态势指标分时段（5min 槽位，周内典型日 day_of_week 1-7）
-- 早高峰 07:00-09:00 => step_index [84,108)
-- 白平峰 10:00-16:00 => step_index [120,192)
-- 晚高峰 17:00-19:00 => step_index [204,228)

"""MySQL 建表 DDL。"""

from __future__ import annotations

TABLE_ODS_RAW = "ods_ctl_inter_manual_survey_issue_raw"
TABLE_DWD_ISSUE = "dwd_ctl_inter_manual_survey_issue"

CREATE_ODS_RAW_DDL = """
CREATE TABLE IF NOT EXISTS `ods_ctl_inter_manual_survey_issue_raw` (
    `record_key`           VARCHAR(32)   NOT NULL COMMENT 'md5(survey_point_id|time_period|problem_primary|problem_desc)',
    `survey_batch`         VARCHAR(32)   NOT NULL DEFAULT 'jinan_2025' COMMENT '调查批次/版本，导入参数',
    `survey_point_id`      VARCHAR(32)   NOT NULL COMMENT 'HTML id，如 路口-1',
    `inter_name_raw`       VARCHAR(128)  NOT NULL COMMENT '调查表路口名称 name',
    `time_period`          VARCHAR(16)   NOT NULL COMMENT '早高峰/晚高峰/平峰/夜间',
    `problem_primary`      VARCHAR(32)   NOT NULL COMMENT '筛选主问题 problem',
    `problem_full_text`    VARCHAR(128)  NOT NULL COMMENT '完整问题组合 full_problem',
    `problem_desc`         VARCHAR(512)  NOT NULL COMMENT '问题描述 desc',
    `lon`                  DOUBLE        NOT NULL,
    `lat`                  DOUBLE        NOT NULL,
    `coord_srs`            VARCHAR(16)   NOT NULL DEFAULT 'gcj02',
    `display_color`        VARCHAR(16)   NULL     COMMENT '地图展示色 color',
    `source_file`          VARCHAR(256)  NULL,
    `ingest_time`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`record_key`),
    INDEX `idx_survey_batch` (`survey_batch`),
    INDEX `idx_survey_point_id` (`survey_point_id`),
    INDEX `idx_inter_name_raw` (`inter_name_raw`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信控路口人工调查问题贴源（HTML pointData）'
""".strip()

CREATE_DWD_ISSUE_DDL = """
CREATE TABLE IF NOT EXISTS `dwd_ctl_inter_manual_survey_issue` (
    `source_key`           VARCHAR(32)  NOT NULL COMMENT 'inter_id 或 survey_point_id',
    `inter_id`             VARCHAR(16)  NULL     COMMENT 'PG 路网 16 位路口编码',
    `inter_name`           VARCHAR(128) NOT NULL COMMENT '路网标准路口名或调查原名',
    `survey_batch`         VARCHAR(32)  NOT NULL DEFAULT 'jinan_2025',
    `time_period`          VARCHAR(16)  NOT NULL COMMENT '早高峰/晚高峰/平峰/夜间',
    `problem_type`         VARCHAR(32)  NOT NULL COMMENT '从 full_problem 拆分后的单一类型',
    `problem_primary_flag` TINYINT      NOT NULL DEFAULT 0 COMMENT '是否同时为主问题 problem_primary',
    `issue_record_cnt`     INT          NOT NULL DEFAULT 1 COMMENT '聚合的 ODS 行数',
    `problem_desc`         VARCHAR(1024) NOT NULL COMMENT '去重合并后的 desc，分号连接',
    `survey_point_ids`     JSON         NULL     COMMENT '关联的 survey_point_id 列表',
    `inter_name_raw`       VARCHAR(128)  NULL     COMMENT '调查表原始路口名',
    `survey_lon`           DOUBLE       NULL,
    `survey_lat`           DOUBLE       NULL,
    `match_method`         VARCHAR(32)  NULL,
    `match_status`         VARCHAR(16)  NOT NULL DEFAULT 'pending',
    `match_distance_m`     DOUBLE       NULL,
    `roadnet_lon`          DOUBLE       NULL,
    `roadnet_lat`          DOUBLE       NULL,
    `source_file`          VARCHAR(256)  NULL,
    `create_time`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `is_deleted`           TINYINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (`survey_batch`, `time_period`, `problem_type`, `source_key`),
    INDEX `idx_inter_id` (`inter_id`),
    INDEX `idx_problem_type` (`problem_type`),
    INDEX `idx_match_status` (`match_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='信控路口人工调查问题融合表（DWD）'
""".strip()

ALL_DDL = (
    CREATE_ODS_RAW_DDL,
    CREATE_DWD_ISSUE_DDL,
)

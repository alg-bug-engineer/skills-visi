"""MySQL 建表 DDL。"""

from __future__ import annotations

TABLE_REPORT_RAW = "ods_tfc_complaint_location_report_raw"
TABLE_GEOCODE_RAW = "ods_tfc_complaint_location_geocode_raw"
TABLE_DWD_ISSUE = "dwd_tfc_complaint_inter_issue"

CREATE_REPORT_RAW_DDL = """
CREATE TABLE IF NOT EXISTS `ods_tfc_complaint_location_report_raw` (
    `location_key`      VARCHAR(32)   NOT NULL COMMENT 'md5(district|location|stat_period)',
    `stat_period`       VARCHAR(32)   NOT NULL DEFAULT '2025' COMMENT '统计时段',
    `report_seq`        SMALLINT      NOT NULL COMMENT 'docx 序号',
    `district_name`     VARCHAR(32)   NOT NULL,
    `location_text`     VARCHAR(256)  NOT NULL COMMENT '原始地点描述',
    `complaint_count`   INT           NOT NULL COMMENT '该点位投诉总件数',
    `summary_text`      TEXT          NOT NULL COMMENT 'docx 完整正文',
    `issue_items_json`  JSON          NULL     COMMENT '分项 [{seq_cn, topic_raw, count, text}]',
    `source_file`       VARCHAR(256)  NULL,
    `ingest_time`       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`location_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='投诉点位年报贴源（docx）'
""".strip()

CREATE_GEOCODE_RAW_DDL = """
CREATE TABLE IF NOT EXISTS `ods_tfc_complaint_location_geocode_raw` (
    `location_key`      VARCHAR(32)   NOT NULL,
    `stat_period`       VARCHAR(32)   NOT NULL DEFAULT '2025',
    `location_text`     VARCHAR(256)  NOT NULL,
    `district_name`     VARCHAR(32)   NULL,
    `complaint_count`   INT           NOT NULL,
    `summary_text`      TEXT          NULL COMMENT 'HTML 短摘要，审计用',
    `geocode_name`      VARCHAR(256)  NULL,
    `geocode_method`    VARCHAR(32)   NULL,
    `lon`               DOUBLE        NULL,
    `lat`               DOUBLE        NULL,
    `coord_srs`         VARCHAR(16)   NOT NULL DEFAULT 'gcj02',
    `source_file`       VARCHAR(256)  NULL,
    `ingest_time`       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`location_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='投诉点位地图坐标贴源（HTML）'
""".strip()

CREATE_DWD_ISSUE_DDL = """
CREATE TABLE IF NOT EXISTS `dwd_tfc_complaint_inter_issue` (
    `source_key`         VARCHAR(32)  NOT NULL COMMENT 'inter_id 或 location_key',
    `inter_id`           VARCHAR(16)  NULL     COMMENT '路网 16 位路口编码',
    `inter_name`         VARCHAR(128) NOT NULL COMMENT '路网标准路口名称',
    `stat_period`        VARCHAR(32)  NOT NULL DEFAULT '2025' COMMENT '统计时段',
    `complaint_type`     VARCHAR(64)  NOT NULL COMMENT '12 类标准投诉类型',
    `complaint_count`    INT          NOT NULL DEFAULT 0 COMMENT '该类型投诉条数',
    `core_problem_desc`  VARCHAR(512) NOT NULL COMMENT '核心问题描述（LLM 或规则提炼）',
    `district_name`      VARCHAR(32)  NULL,
    `location_text`      VARCHAR(256) NULL,
    `location_key`       VARCHAR(32)  NULL,
    `match_method`       VARCHAR(32)  NULL,
    `match_status`       VARCHAR(16)  NOT NULL DEFAULT 'pending',
    `source_summary`     TEXT         NULL     COMMENT 'docx 该类型原始描述',
    `create_time`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `is_deleted`         TINYINT      NOT NULL DEFAULT 0,
    PRIMARY KEY (`stat_period`, `complaint_type`, `source_key`),
    INDEX `idx_inter_id` (`inter_id`),
    INDEX `idx_complaint_type` (`complaint_type`),
    INDEX `idx_match_status` (`match_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='路口投诉问题融合表（DWD）'
""".strip()

ALL_DDL = (
    CREATE_REPORT_RAW_DDL,
    CREATE_GEOCODE_RAW_DDL,
    CREATE_DWD_ISSUE_DDL,
)

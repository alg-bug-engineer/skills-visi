"""MySQL 建表 DDL。"""

from __future__ import annotations

TABLE_ODS_ISSUE = "ods_tfc_field_survey_issue_raw"
TABLE_ODS_IMAGE = "ods_tfc_field_survey_image_raw"
TABLE_ODS_RECOMMENDATION = "ods_tfc_field_survey_recommendation_raw"
TABLE_ODS_MATRIX = "ods_tfc_field_survey_matrix_raw"
TABLE_DWD_ISSUE = "dwd_tfc_field_survey_inter_issue"

CREATE_ODS_ISSUE_DDL = """
CREATE TABLE IF NOT EXISTS `ods_tfc_field_survey_issue_raw` (
    `issue_key`            VARCHAR(32)   NOT NULL COMMENT 'md5(report_batch|section_no|inter_seq|issue_seq|issue_type)',
    `report_batch`         VARCHAR(32)   NOT NULL DEFAULT 'jinan_20260609',
    `section_no`           VARCHAR(8)    NULL,
    `section_name`         VARCHAR(32)   NULL,
    `inter_seq`            VARCHAR(16)   NULL,
    `inter_name_raw`       VARCHAR(256)  NOT NULL,
    `inter_alias`          VARCHAR(128)  NULL,
    `issue_seq`            SMALLINT      NOT NULL,
    `issue_category`       VARCHAR(16)   NOT NULL,
    `issue_type`           VARCHAR(64)   NOT NULL,
    `issue_desc`           TEXT          NULL,
    `recommendation_text`  TEXT          NULL,
    `source_page_start`    SMALLINT      NULL,
    `source_page_end`      SMALLINT      NULL,
    `source_file`          VARCHAR(512)  NULL,
    `ingest_time`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`issue_key`),
    INDEX `idx_report_batch` (`report_batch`),
    INDEX `idx_inter_seq` (`inter_seq`),
    INDEX `idx_inter_name_raw` (`inter_name_raw`(64)),
    INDEX `idx_issue_type` (`issue_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交通组织调研问题贴源'
""".strip()

CREATE_ODS_IMAGE_DDL = """
CREATE TABLE IF NOT EXISTS `ods_tfc_field_survey_image_raw` (
    `image_key`            VARCHAR(32)   NOT NULL COMMENT 'md5(report_batch|local_path)',
    `report_batch`         VARCHAR(32)   NOT NULL DEFAULT 'jinan_20260609',
    `issue_key`            VARCHAR(32)   NULL,
    `inter_name_raw`       VARCHAR(256)  NULL,
    `page_no`              SMALLINT      NOT NULL,
    `image_seq`            SMALLINT      NOT NULL,
    `caption_text`         VARCHAR(512)  NULL,
    `local_path`           VARCHAR(512)  NOT NULL,
    `local_url`            VARCHAR(512)  NULL,
    `minio_bucket`         VARCHAR(64)   NULL,
    `minio_object_key`     VARCHAR(512)  NULL,
    `image_url`            VARCHAR(1024) NULL,
    `width`                INT           NULL,
    `height`               INT           NULL,
    `file_size`            INT           NULL,
    `match_status`         VARCHAR(16)   NOT NULL DEFAULT 'linked',
    `source_file`          VARCHAR(512)  NULL,
    `ingest_time`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`image_key`),
    INDEX `idx_report_batch` (`report_batch`),
    INDEX `idx_issue_key` (`issue_key`),
    INDEX `idx_inter_name_raw` (`inter_name_raw`(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交通组织调研图片贴源'
""".strip()

CREATE_ODS_RECOMMENDATION_DDL = """
CREATE TABLE IF NOT EXISTS `ods_tfc_field_survey_recommendation_raw` (
    `rec_key`              VARCHAR(32)   NOT NULL COMMENT 'md5(report_batch|inter_name|horizon|rec_seq)',
    `report_batch`         VARCHAR(32)   NOT NULL DEFAULT 'jinan_20260609',
    `inter_name_raw`       VARCHAR(256)  NOT NULL,
    `horizon`              VARCHAR(16)   NOT NULL COMMENT '近期/远期',
    `rec_seq`              SMALLINT      NOT NULL,
    `rec_text`             TEXT          NOT NULL,
    `issue_key`            VARCHAR(32)   NULL,
    `source_file`          VARCHAR(512)  NULL,
    `ingest_time`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`rec_key`),
    INDEX `idx_report_batch` (`report_batch`),
    INDEX `idx_inter_name_raw` (`inter_name_raw`(64))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交通组织调研改造建议贴源'
""".strip()

CREATE_ODS_MATRIX_DDL = """
CREATE TABLE IF NOT EXISTS `ods_tfc_field_survey_matrix_raw` (
    `matrix_key`           VARCHAR(32)   NOT NULL COMMENT 'md5(report_batch|inter_seq)',
    `report_batch`         VARCHAR(32)   NOT NULL DEFAULT 'jinan_20260609',
    `inter_seq`            VARCHAR(16)   NOT NULL,
    `inter_name_raw`       VARCHAR(256)  NOT NULL,
    `section_name`         VARCHAR(32)   NULL,
    `flag_json`            JSON          NOT NULL,
    `issue_type_cnt`       SMALLINT      NOT NULL DEFAULT 0,
    `source_file`          VARCHAR(512)  NULL,
    `ingest_time`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`matrix_key`),
    INDEX `idx_report_batch` (`report_batch`),
    INDEX `idx_inter_seq` (`inter_seq`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交通组织调研汇总矩阵贴源'
""".strip()

CREATE_DWD_ISSUE_DDL = """
CREATE TABLE IF NOT EXISTS `dwd_tfc_field_survey_inter_issue` (
    `issue_key`            VARCHAR(32)   NOT NULL,
    `source_key`           VARCHAR(32)   NOT NULL COMMENT 'inter_id 或 issue_key',
    `inter_id`             VARCHAR(16)   NULL,
    `inter_name`           VARCHAR(128)  NOT NULL,
    `report_batch`         VARCHAR(32)   NOT NULL DEFAULT 'jinan_20260609',
    `section_name`         VARCHAR(32)   NULL,
    `inter_seq`            VARCHAR(16)   NULL,
    `inter_name_raw`       VARCHAR(256)  NOT NULL,
    `inter_alias`          VARCHAR(128)  NULL,
    `issue_seq`            SMALLINT      NOT NULL,
    `issue_category`       VARCHAR(16)   NOT NULL,
    `issue_type`           VARCHAR(64)   NOT NULL,
    `issue_desc`           TEXT          NULL,
    `recommendation_text`  TEXT          NULL,
    `image_urls`           JSON          NULL,
    `recommendations_json` JSON          NULL,
    `match_method`         VARCHAR(32)   NULL,
    `match_status`         VARCHAR(16)   NOT NULL DEFAULT 'pending',
    `match_distance_m`     DOUBLE        NULL,
    `roadnet_lon`          DOUBLE        NULL,
    `roadnet_lat`          DOUBLE        NULL,
    `source_file`          VARCHAR(512)  NULL,
    `create_time`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `is_deleted`           TINYINT       NOT NULL DEFAULT 0,
    PRIMARY KEY (`report_batch`, `issue_key`),
    INDEX `idx_inter_id` (`inter_id`),
    INDEX `idx_issue_type` (`issue_type`),
    INDEX `idx_match_status` (`match_status`),
    INDEX `idx_source_key` (`source_key`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='交通组织调研问题融合表（DWD）'
""".strip()

ALL_DDL = (
    CREATE_ODS_ISSUE_DDL,
    CREATE_ODS_IMAGE_DDL,
    CREATE_ODS_RECOMMENDATION_DDL,
    CREATE_ODS_MATRIX_DDL,
    CREATE_DWD_ISSUE_DDL,
)

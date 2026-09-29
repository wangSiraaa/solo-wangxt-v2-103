-- 工艺管网隔离演示：PostgreSQL 初始化脚本（由 docker-entrypoint-initdb.d 自动执行）
-- 应用启动时也会幂等 upsert 种子数据；此处显式建表表达存储模型。

CREATE TABLE IF NOT EXISTS nodes (
    network_id VARCHAR(64)  NOT NULL,
    node_id    VARCHAR(64)  NOT NULL,
    label      VARCHAR(256) NOT NULL,
    kind       VARCHAR(32)  NOT NULL CHECK (kind IN ('source','junction','equipment','supply','sink')),
    pos_x      INTEGER      NOT NULL DEFAULT 0,
    pos_y      INTEGER      NOT NULL DEFAULT 0,
    PRIMARY KEY (network_id, node_id)
);

CREATE TABLE IF NOT EXISTS segments (
    network_id  VARCHAR(64)  NOT NULL,
    segment_id  VARCHAR(64)  NOT NULL,
    source_id   VARCHAR(64)  NOT NULL,
    target_id   VARCHAR(64)  NOT NULL,
    kind        VARCHAR(32)  NOT NULL CHECK (kind IN ('main','bypass','branch','outlet')),
    label       VARCHAR(256) NOT NULL DEFAULT '',
    PRIMARY KEY (network_id, segment_id),
    FOREIGN KEY (network_id, source_id) REFERENCES nodes(network_id, node_id),
    FOREIGN KEY (network_id, target_id) REFERENCES nodes(network_id, node_id)
);

CREATE TABLE IF NOT EXISTS valves (
    network_id VARCHAR(64)  NOT NULL,
    valve_id   VARCHAR(64)  NOT NULL,
    segment_id VARCHAR(64)  NOT NULL,
    label      VARCHAR(256) NOT NULL,
    is_open    BOOLEAN      NOT NULL DEFAULT TRUE,   -- 阀门开闭
    is_locked  BOOLEAN      NOT NULL DEFAULT FALSE,  -- 锁定（不可操作）
    PRIMARY KEY (network_id, valve_id),
    FOREIGN KEY (network_id, segment_id) REFERENCES segments(network_id, segment_id)
);

CREATE TABLE IF NOT EXISTS scenarios (
    network_id  VARCHAR(64)  NOT NULL,
    scenario_id VARCHAR(64)  NOT NULL,
    name        VARCHAR(256) NOT NULL,
    target_id   VARCHAR(64)  NOT NULL,
    PRIMARY KEY (network_id, scenario_id),
    FOREIGN KEY (network_id, target_id) REFERENCES nodes(network_id, node_id)
);

CREATE TABLE IF NOT EXISTS scenario_required_supplies (
    network_id  VARCHAR(64) NOT NULL,
    scenario_id VARCHAR(64) NOT NULL,
    node_id     VARCHAR(64) NOT NULL,
    PRIMARY KEY (network_id, scenario_id, node_id),
    FOREIGN KEY (network_id, scenario_id) REFERENCES scenarios(network_id, scenario_id),
    FOREIGN KEY (network_id, node_id) REFERENCES nodes(network_id, node_id)
);

-- 连接/阀门状态审计视图：隔离计算前可先核对拓扑与阀态
CREATE OR REPLACE VIEW v_valve_status AS
SELECT v.network_id,
       v.valve_id,
       v.label            AS valve_label,
       v.segment_id,
       s.source_id,
       s.target_id,
       s.kind             AS segment_kind,
       v.is_open,
       v.is_locked
FROM valves v
JOIN segments s
  ON v.network_id = s.network_id AND v.segment_id = s.segment_id;

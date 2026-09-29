"""API 端到端测试（SQLite 回退，不需要 PostgreSQL）。"""

import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["USE_SQLITE"] = "1"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app import main  # noqa: F401  触发 startup
    with TestClient(main.app) as c:
        yield c


def test_health_and_disclaimer(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "不连接真实控制系统" in r.json()["disclaimer"]


def test_topology_shape(client):
    topo = client.get("/api/topology").json()
    assert topo["network_id"] == "demo-1"
    assert {n["id"] for n in topo["nodes"]} >= {"SRC", "T", "SP1", "SP2"}
    assert {v["valve_id"] for v in topo["valves"]} >= {"V3", "V6", "V7", "V10"}
    v10 = next(v for v in topo["valves"] if v["valve_id"] == "V10")
    assert v10["is_open"] is False  # 排液阀初始关闭
    assert topo["scenarios"][0]["target_id"] == "T"
    assert topo["scenarios"][0]["required_supply_ids"] == ["SP1", "SP2"]


def test_isolation_default(client):
    r = client.post("/api/isolation", json={"scenario_id": "eq_t"})
    data = r.json()
    assert data["feasible"] is True
    assert data["plans"][0]["valve_ids"] == ["V3", "V6"]
    assert data["plans"][0]["closes_bypass"] is True
    rejected = {tuple(p["valve_ids"]) for p in data["rejected_plans"]}
    assert ("V0",) in rejected and ("V2",) in rejected


def test_isolation_locked_v6_residual_path(client):
    r = client.post(
        "/api/isolation",
        json={"scenario_id": "eq_t", "locked_valve_ids": ["V6"]},
    )
    data = r.json()
    assert data["feasible"] is False
    assert data["reason"] == "locked_path"
    assert data["residual_path_node_ids"] == ["SRC", "A", "N", "B", "E", "T"]
    assert "s6" in data["residual_segment_ids"]


def test_persist_lock_and_reset(client):
    # 在库里锁定 V6（持久状态）
    r = client.patch("/api/valves/V6", json={"is_locked": True})
    assert r.json()["is_locked"] is True
    # 不带临时锁定时也应表现为锁定 -> 无解
    data = client.post("/api/isolation", json={"scenario_id": "eq_t"}).json()
    assert data["feasible"] is False
    assert "V6" in data["locked_valve_ids"]
    # 恢复
    assert client.post("/api/reset").status_code == 200
    data = client.post("/api/isolation", json={"scenario_id": "eq_t"}).json()
    assert data["feasible"] is True


def test_unknown_valve_rejected(client):
    r = client.post(
        "/api/isolation",
        json={"scenario_id": "eq_t", "locked_valve_ids": ["NOPE"]},
    )
    assert r.status_code == 400

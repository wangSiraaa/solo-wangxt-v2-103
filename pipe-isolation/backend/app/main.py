"""FastAPI 入口：隔离方案计算演示后端。

启动时自动建表并写入演示数据。数据库不可用时以错误信息明确暴露
（部署见 deploy/docker-compose.yml）；单元测试通过 USE_SQLITE=1 运行。
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import repository, seed
from .repository import reset_network
from .schemas import (
    DISCLAIMER,
    IsolationIn,
    IsolationOut,
    NodeOut,
    ScenarioOut,
    SegmentOut,
    TopologyOut,
    ValveOut,
    ValveStateIn,
)
from .seed_db import NETWORK_ID, seed_database
from .solver import isolate

app = FastAPI(
    title="工艺管网隔离方案演示",
    version="1.0.0",
    description="NetworkX 计算候选隔离集合；纯演示，不连接真实控制系统。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    seed_database()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "disclaimer": DISCLAIMER}


@app.get("/api/topology", response_model=TopologyOut)
def get_topology() -> TopologyOut:
    network = repository.load_network(NETWORK_ID)
    positions = repository.get_positions(NETWORK_ID)
    valve_by_segment = {v.segment_id: v for v in network.valves}
    segments = [
        SegmentOut(
            id=seg.id,
            source_id=seg.source_id,
            target_id=seg.target_id,
            kind=seg.kind.value,
            label=seg.label,
            valve_id=(valve_by_segment[seg.id].id if seg.id in valve_by_segment else None),
            valve_open=(
                valve_by_segment[seg.id].is_open if seg.id in valve_by_segment else False
            ),
            valve_locked=(
                valve_by_segment[seg.id].is_locked if seg.id in valve_by_segment else False
            ),
        )
        for seg in network.segments
    ]
    return TopologyOut(
        network_id=NETWORK_ID,
        nodes=[
            NodeOut(
                id=n.id,
                label=n.label,
                kind=n.kind,
                position=positions.get(n.id, [0, 0]),
            )
            for n in network.nodes
        ],
        segments=segments,
        valves=[
            ValveOut(
                valve_id=v.id,
                segment_id=v.segment_id,
                label=v.label,
                is_open=v.is_open,
                is_locked=v.is_locked,
            )
            for v in network.valves
        ],
        source_ids=list(network.source_ids),
        scenarios=[ScenarioOut(**sc) for sc in repository.list_scenarios(NETWORK_ID)],
        disclaimer=DISCLAIMER,
    )


@app.post("/api/isolation", response_model=IsolationOut)
def compute_isolation(payload: IsolationIn) -> IsolationOut:
    scenario = repository.get_scenario(NETWORK_ID, payload.scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="scenario not found")
    network = repository.load_network(NETWORK_ID)

    unknown = set(payload.locked_valve_ids) - {v.id for v in network.valves}
    if unknown:
        raise HTTPException(
            status_code=400, detail=f"unknown locked valve ids: {sorted(unknown)}"
        )

    result = isolate(
        network,
        target_id=scenario["target_id"],
        required_supply_ids=scenario["required_supply_ids"],
        extra_locked_valve_ids=set(payload.locked_valve_ids),
    )
    return IsolationOut(**result.to_dict())


@app.patch("/api/valves/{valve_id}", response_model=ValveOut)
def update_valve(valve_id: str, payload: ValveStateIn) -> ValveOut:
    row = repository.set_valve_state(
        NETWORK_ID,
        valve_id,
        is_open=payload.is_open,
        is_locked=payload.is_locked,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="valve not found")
    return ValveOut(**row)


@app.post("/api/reset")
def reset() -> dict:
    reset_network(NETWORK_ID, seed.VALVES)
    return {"status": "ok"}

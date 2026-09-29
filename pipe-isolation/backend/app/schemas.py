from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ValveOut(BaseModel):
    valve_id: str
    segment_id: str
    label: str
    is_open: bool
    is_locked: bool


class ValveStateIn(BaseModel):
    is_open: Optional[bool] = None
    is_locked: Optional[bool] = None


class NodeOut(BaseModel):
    id: str
    label: str
    kind: str
    position: list[int] = Field(min_length=2, max_length=2)


class SegmentOut(BaseModel):
    id: str
    source_id: str
    target_id: str
    kind: str
    label: str
    valve_id: Optional[str] = None
    valve_open: bool
    valve_locked: bool


class ScenarioOut(BaseModel):
    id: str
    name: str
    target_id: str
    required_supply_ids: list[str]
    network_id: str


class TopologyOut(BaseModel):
    network_id: str
    nodes: list[NodeOut]
    segments: list[SegmentOut]
    valves: list[ValveOut]
    source_ids: list[str]
    scenarios: list[ScenarioOut]
    disclaimer: str


class IsolationIn(BaseModel):
    scenario_id: str = "eq_t"
    # 前端临时锁定（不写库）的阀门
    locked_valve_ids: list[str] = Field(default_factory=list)


class PlanOut(BaseModel):
    valve_ids: list[str]
    closes_bypass: bool


class RejectedPlanOut(BaseModel):
    valve_ids: list[str]
    lost_required_supply_ids: list[str]


class IsolationOut(BaseModel):
    feasible: bool
    target_id: str
    required_supply_ids: list[str]
    plans: list[PlanOut]
    rejected_plans: list[RejectedPlanOut]
    already_closed_valve_ids: list[str]
    locked_valve_ids: list[str]
    residual_path_node_ids: Optional[list[str]]
    residual_segment_ids: Optional[list[str]]
    reason: Optional[str]


DISCLAIMER = (
    "本系统仅针对给定拓扑与阀门模型做工艺培训演示，不连接真实控制系统；"
    "结果不构成检修隔离依据，不代表满足真实检修安全条件。"
)

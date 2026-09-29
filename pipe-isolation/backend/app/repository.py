"""数据访问：把行记录装配成 solver 的 Network；阀门状态可被前端改写。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select

from .database import RequiredSupplyRow, ScenarioRow, SegmentRow, NodeRow, ValveRow, session_scope
from .solver import Network, Node, Segment, SegmentKind, Valve


def load_network(network_id: str) -> Network:
    with session_scope() as s:
        nodes = [
            Node(n.node_id, n.label, n.kind)
            for n in s.scalars(select(NodeRow).where(NodeRow.network_id == network_id))
        ]
        segments = [
            Segment(
                seg.segment_id,
                seg.source_id,
                seg.target_id,
                SegmentKind(seg.kind),
                seg.label,
            )
            for seg in s.scalars(
                select(SegmentRow).where(SegmentRow.network_id == network_id)
            )
        ]
        valves = [
            Valve(v.valve_id, v.segment_id, v.label, v.is_open, v.is_locked)
            for v in s.scalars(
                select(ValveRow).where(ValveRow.network_id == network_id)
            )
        ]
        source_ids = [n.id for n in nodes if n.kind == "source"]
    return Network(nodes=nodes, segments=segments, valves=valves, source_ids=source_ids)


def list_scenarios(network_id: str) -> list[dict]:
    with session_scope() as s:
        rows = list(
            s.scalars(
                select(ScenarioRow).where(ScenarioRow.network_id == network_id)
            )
        )
        out = []
        for row in rows:
            supplies = list(
                s.scalars(
                    select(RequiredSupplyRow.node_id).where(
                        RequiredSupplyRow.network_id == network_id,
                        RequiredSupplyRow.scenario_id == row.scenario_id,
                    )
                )
            )
            out.append(
                {
                    "id": row.scenario_id,
                    "name": row.name,
                    "target_id": row.target_id,
                    "required_supply_ids": supplies,
                    "network_id": network_id,
                }
            )
        return out


def get_scenario(network_id: str, scenario_id: str) -> Optional[dict]:
    for sc in list_scenarios(network_id):
        if sc["id"] == scenario_id:
            return sc
    return None


def get_positions(network_id: str) -> dict[str, list[int]]:
    with session_scope() as s:
        return {
            n.node_id: [n.pos_x, n.pos_y]
            for n in s.scalars(select(NodeRow).where(NodeRow.network_id == network_id))
        }


def set_valve_state(
    network_id: str, valve_id: str, *, is_open: Optional[bool], is_locked: Optional[bool]
) -> Optional[dict]:
    with session_scope() as s:
        row = s.get(ValveRow, (network_id, valve_id))
        if row is None:
            return None
        if is_open is not None:
            row.is_open = is_open
        if is_locked is not None:
            row.is_locked = is_locked
        s.commit()
        return {
            "valve_id": row.valve_id,
            "segment_id": row.segment_id,
            "label": row.label,
            "is_open": row.is_open,
            "is_locked": row.is_locked,
        }


def reset_network(network_id: str, seed_valves: list[Valve]) -> None:
    """恢复演示阀门初始状态。"""
    with session_scope() as s:
        for v in seed_valves:
            row = s.get(ValveRow, (network_id, v.id))
            if row is not None:
                row.is_open = v.is_open
                row.is_locked = v.is_locked
        s.commit()

"""把 seed.py 的演示数据写入数据库（幂等 upsert）。"""

from __future__ import annotations

from sqlalchemy import select

from . import seed
from .database import (
    Base,
    NodeRow,
    RequiredSupplyRow,
    ScenarioRow,
    SegmentRow,
    ValveRow,
    create_all,
    get_engine,
    session_scope,
)

NETWORK_ID = seed.SCENARIO["network_id"]


def seed_database() -> None:
    create_all()
    with session_scope() as s:
        for n in seed.NODES:
            x, y = seed.LAYOUT_POSITIONS.get(n.id, (0, 0))
            row = s.get(NodeRow, (NETWORK_ID, n.id))
            if row is None:
                s.add(
                    NodeRow(
                        network_id=NETWORK_ID,
                        node_id=n.id,
                        label=n.label,
                        kind=n.kind,
                        pos_x=x,
                        pos_y=y,
                    )
                )
            else:
                row.label, row.kind, row.pos_x, row.pos_y = n.label, n.kind, x, y

        for seg in seed.SEGMENTS:
            row = s.get(SegmentRow, (NETWORK_ID, seg.id))
            if row is None:
                s.add(
                    SegmentRow(
                        network_id=NETWORK_ID,
                        segment_id=seg.id,
                        source_id=seg.source_id,
                        target_id=seg.target_id,
                        kind=seg.kind.value,
                        label=seg.label,
                    )
                )
            else:
                row.source_id = seg.source_id
                row.target_id = seg.target_id
                row.kind = seg.kind.value
                row.label = seg.label

        for v in seed.VALVES:
            row = s.get(ValveRow, (NETWORK_ID, v.id))
            if row is None:
                s.add(
                    ValveRow(
                        network_id=NETWORK_ID,
                        valve_id=v.id,
                        segment_id=v.segment_id,
                        label=v.label,
                        is_open=v.is_open,
                        is_locked=v.is_locked,
                    )
                )
            else:
                row.segment_id = v.segment_id
                row.label = v.label
                row.is_open = v.is_open
                row.is_locked = v.is_locked

        sc = seed.SCENARIO
        row = s.get(ScenarioRow, (NETWORK_ID, sc["id"]))
        if row is None:
            s.add(
                ScenarioRow(
                    network_id=NETWORK_ID,
                    scenario_id=sc["id"],
                    name=sc["name"],
                    target_id=sc["target_id"],
                )
            )
        else:
            row.name = sc["name"]
            row.target_id = sc["target_id"]

        existing = set(
            s.scalars(
                select(RequiredSupplyRow.node_id).where(
                    RequiredSupplyRow.network_id == NETWORK_ID,
                    RequiredSupplyRow.scenario_id == sc["id"],
                )
            )
        )
        for sp in sc["required_supply_ids"]:
            if sp not in existing:
                s.add(
                    RequiredSupplyRow(
                        network_id=NETWORK_ID,
                        scenario_id=sc["id"],
                        node_id=sp,
                    )
                )
        s.commit()


if __name__ == "__main__":
    seed_database()
    eng = get_engine()
    print(f"seeded into {eng.url}")

"""隔离方案求解器（纯 NetworkX，不依赖数据库，便于单元测试）。

模型约定（演示用，明确简化）：

* 管网是 *有向图*：管段方向即介质流向，残余连通性按有向边判定，
  不模拟停输后的物理倒流。
* 每条管段(segment)上至多挂一个阀门(valve)：
    - 阀门开启且可操作   -> 边权 1，可以被纳入关闭集合；
    - 阀门开启但被锁定   -> 不可切断（逻辑权 INF），只能保持开启；
    - 阀门已关闭         -> 边直接从图中移除；
    - 管段上没有阀门     -> 不可切断（逻辑权 INF）。
* 目标：切断所有 source 节点到目标设备节点的有向路径；
* 约束：方案执行后，每个“必要供给点”仍可从任一 source 有向可达。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import networkx as nx

# 不可切断边的逻辑容量（管段无阀 / 阀门被锁定开启）
INF = 10**6

# 枚举规模上限（演示管网很小，防止组合爆炸）
MAX_PLAN_SIZE = 5
MAX_SEARCH_NODES = 4000


class SegmentKind(str, Enum):
    MAIN = "main"        # 主管
    BYPASS = "bypass"    # 旁路（绕回）
    BRANCH = "branch"    # 支路（含必要供给点）
    OUTLET = "outlet"    # 设备下游


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    kind: str  # source | junction | equipment | supply | sink


@dataclass(frozen=True)
class Segment:
    id: str
    source_id: str
    target_id: str
    kind: SegmentKind = SegmentKind.MAIN
    label: str = ""


@dataclass(frozen=True)
class Valve:
    id: str
    segment_id: str
    label: str
    is_open: bool = True
    is_locked: bool = False


@dataclass
class Network:
    nodes: list[Node]
    segments: list[Segment]
    valves: list[Valve]
    source_ids: list[str] = field(default_factory=list)


@dataclass
class Plan:
    valve_ids: list[str]
    closes_bypass: bool


@dataclass
class IsolationResult:
    feasible: bool
    target_id: str
    required_supply_ids: list[str]
    plans: list[Plan]
    rejected_plans: list[dict]
    already_closed_valve_ids: list[str]
    locked_valve_ids: list[str]
    residual_path_node_ids: Optional[list[str]]
    residual_segment_ids: Optional[list[str]]
    reason: Optional[str]  # locked_path | supply_conflict | None

    def to_dict(self) -> dict:
        return {
            "feasible": self.feasible,
            "target_id": self.target_id,
            "required_supply_ids": self.required_supply_ids,
            "plans": [
                {"valve_ids": p.valve_ids, "closes_bypass": p.closes_bypass}
                for p in self.plans
            ],
            "rejected_plans": self.rejected_plans,
            "already_closed_valve_ids": self.already_closed_valve_ids,
            "locked_valve_ids": self.locked_valve_ids,
            "residual_path_node_ids": self.residual_path_node_ids,
            "residual_segment_ids": self.residual_segment_ids,
            "reason": self.reason,
        }


def _build_graph(network: Network) -> nx.MultiDiGraph:
    """按管段方向建图，边属性记录管段/阀门与可切断性。"""
    g = nx.MultiDiGraph()
    for n in network.nodes:
        g.add_node(n.id, label=n.label, kind=n.kind)

    valves_by_segment = {v.segment_id: v for v in network.valves}
    for seg in network.segments:
        valve = valves_by_segment.get(seg.id)
        if valve is not None and not valve.is_open:
            # 已关闭阀门：管段断开，不加入图
            continue
        cuttable = valve is not None and not valve.is_locked
        g.add_edge(
            seg.source_id,
            seg.target_id,
            key=seg.id,
            segment_id=seg.id,
            segment_kind=seg.kind.value,
            valve_id=valve.id if valve else None,
            cuttable=cuttable,
        )
    return g


def _find_s_target_path(
    g: nx.MultiDiGraph, sources: list[str], target: str
) -> Optional[list[str]]:
    """找一条任一 source 到目标的有向路径，返回边 key(segment_id) 列表。"""
    for s in sources:
        if not g.has_node(s) or not nx.has_path(g, s, target):
            continue
        nodes = nx.shortest_path(g, s, target)
        return [
            g[u][v][key]["segment_id"]
            for u, v, key in _edge_keys_on_node_path(g, nodes)
        ]
    return None


def _edge_keys_on_node_path(g: nx.MultiDiGraph, nodes: list[str]):
    for u, v in zip(nodes, nodes[1:]):
        # MultiDiGraph 两节点间若有多条平行管段，取任意一条（演示管网无平行边）
        key = next(iter(g[u][v]))
        yield u, v, key


def _enumerate_minimal_cuts(
    g: nx.MultiDiGraph, sources: list[str], target: str
) -> list[frozenset[str]]:
    """枚举所有“极小”可切断管段集合（ hitting-set 方式递归）。

    递归思路：任取一条仍连通的 source->target 路径，要切断它就必须
    关闭路径上某个可操作阀门；逐个尝试并递归。每个命中集合都是极小的。
    """
    results: set[frozenset[str]] = set()
    stats = {"nodes": 0}

    def rec(removed: frozenset[str]) -> None:
        stats["nodes"] += 1
        if stats["nodes"] > MAX_SEARCH_NODES or len(removed) > MAX_PLAN_SIZE:
            return

        view = _view_without(g, removed)
        path = _find_s_target_path(view, sources, target)
        if path is None:
            # 去掉冗余：仅保留极小集合
            if not any(existing < removed for existing in results):
                results.discard(removed)
                results.add(frozenset(removed))
            return

        # 注意：不能因为已经找到更小的割就停止展开——更小的割可能因
        # “断供”被否决（例如 {V2} 会断 SP2），仍需枚举 {V3,V6} 这类
        # 稍大但保供的极小割。
        candidates = {
            view[u][v][key]["valve_id"]
            for sid in path
            for u, v, key in [_edge_key_by_segment(view, sid)]
            if view[u][v][key]["cuttable"]
        }
        for valve_id in sorted(candidates):
            sid = _segment_of_valve(g, valve_id)
            if sid and sid not in removed:
                rec(removed | {sid})

    rec(frozenset())
    # 极小性过滤（枚举过程已近似保证，这里兜底）
    minimal = [r for r in results if not any(o < r for o in results)]
    minimal.sort(key=lambda r: (len(r), sorted(r)))
    return minimal


def _view_without(g: nx.MultiDiGraph, removed_segment_ids: frozenset[str]):
    if not removed_segment_ids:
        return g
    view = g.copy()
    for sid in removed_segment_ids:
        u, v, key = _edge_key_by_segment(g, sid)
        if view.has_edge(u, v, key):
            view.remove_edge(u, v, key)
    return view


def _edge_key_by_segment(g: nx.MultiDiGraph, segment_id: str):
    for u, v, key, data in g.edges(keys=True, data=True):
        if data["segment_id"] == segment_id:
            return u, v, key
    raise KeyError(segment_id)


def _segment_of_valve(g: nx.MultiDiGraph, valve_id: str) -> Optional[str]:
    for _, _, _, data in g.edges(keys=True, data=True):
        if data.get("valve_id") == valve_id:
            return data["segment_id"]
    return None


def _supplies_reachable(
    g: nx.MultiDiGraph, sources: list[str], supplies: list[str]
) -> dict[str, bool]:
    reachable: set[str] = set()
    for s in sources:
        if g.has_node(s):
            reachable.update(nx.descendants(g, s))
            reachable.add(s)
    return {sp: sp in reachable for sp in supplies}


def _residual_path_after_supply_safe_closures(
    g: nx.MultiDiGraph, sources: list[str], target: str, supplies: list[str]
) -> Optional[list[str]]:
    """贪心地关闭所有“不影响必要供给”的可操作阀门，再看目标是否仍连通。

    用于找不到方案时给前端返回一条 *仍然连通* 的残余路径（稳定可复现，
    仅作演示展示，不声称是唯一路径）。
    """
    view = g.copy()
    finite_edges = [
        (u, v, key)
        for u, v, key in sorted(
            view.edges(keys=True), key=lambda e: view[e[0]][e[1]][e[2]]["segment_id"]
        )
        if view[u][v][key]["cuttable"]
    ]
    changed = True
    while changed:
        changed = False
        for edge in list(finite_edges):
            u, v, key = edge
            if not view.has_edge(u, v, key):
                continue
            view.remove_edge(u, v, key)
            status = _supplies_reachable(view, sources, supplies)
            if all(status.values()):
                changed = True  # 保留关闭
                finite_edges.remove(edge)
            else:
                view.add_edge(u, v, key, **g[u][v][key])  # 恢复

    for s in sources:
        if view.has_node(s) and nx.has_path(view, s, target):
            return nx.shortest_path(view, s, target)
    return None


def isolate(
    network: Network,
    target_id: str,
    required_supply_ids: list[str],
    extra_locked_valve_ids: Optional[set[str]] = None,
) -> IsolationResult:
    """计算隔离候选集合。

    extra_locked_valve_ids: 前端临时锁定（不可操作）的阀门，叠加在
    阀门自身 is_locked 状态之上。
    """
    extra_locked = extra_locked_valve_ids or set()
    if extra_locked:
        network = _with_locks(network, extra_locked)

    g = _build_graph(network)
    seg_by_id = {s.id: s for s in network.segments}
    valve_by_id = {v.id: v for v in network.valves}
    bypass_segments = {s.id for s in network.segments if s.kind == SegmentKind.BYPASS}

    already_closed = sorted(v.id for v in network.valves if not v.is_open)
    locked = sorted(v.id for v in network.valves if v.is_locked)

    # 特殊情形：目标已被当前关闭的阀门隔离，无需再关任何阀
    if not g_has_any_path(g, network.source_ids, target_id):
        supply_status = _supplies_reachable(g, network.source_ids, required_supply_ids)
        lost = [sp for sp, ok in supply_status.items() if not ok]
        return IsolationResult(
            feasible=not lost,
            target_id=target_id,
            required_supply_ids=required_supply_ids,
            plans=[Plan(valve_ids=[], closes_bypass=False)] if not lost else [],
            rejected_plans=[{"valve_ids": [], "lost_required_supply_ids": lost}] if lost else [],
            already_closed_valve_ids=already_closed,
            locked_valve_ids=locked,
            residual_path_node_ids=None,
            residual_segment_ids=None,
            reason=None if not lost else "supply_conflict",
        )

    all_cuts = _enumerate_minimal_cuts(g, network.source_ids, target_id)

    plans: list[Plan] = []
    rejected: list[dict] = []
    for cut in all_cuts:
        valve_ids = sorted(
            g[u][v][key]["valve_id"]
            for sid in cut
            for u, v, key in [_edge_key_by_segment(g, sid)]
        )
        view = _view_without(g, cut)
        supply_status = _supplies_reachable(
            view, network.source_ids, required_supply_ids
        )
        lost = [sp for sp, ok in supply_status.items() if not ok]
        if not lost:
            plans.append(
                Plan(
                    valve_ids=valve_ids,
                    closes_bypass=any(sid in bypass_segments for sid in cut),
                )
            )
        else:
            rejected.append(
                {
                    "valve_ids": valve_ids,
                    "lost_required_supply_ids": lost,
                }
            )

    if plans:
        return IsolationResult(
            feasible=True,
            target_id=target_id,
            required_supply_ids=required_supply_ids,
            plans=plans,
            rejected_plans=rejected[:10],
            already_closed_valve_ids=already_closed,
            locked_valve_ids=locked,
            residual_path_node_ids=None,
            residual_segment_ids=None,
            reason=None,
        )

    # ---- 无解：给出一条仍然连通的残余路径 ----
    residual_nodes = _residual_path_after_supply_safe_closures(
        g, network.source_ids, target_id, required_supply_ids
    )
    residual_segments: Optional[list[str]] = None
    if residual_nodes is not None:
        residual_segments = [
            g[u][v][next(iter(g[u][v]))]["segment_id"]
            for u, v in zip(residual_nodes, residual_nodes[1:])
        ]

    # 若所有不影响供给的阀门都关了仍隔离不了 -> 锁定阀门在维持连通
    still_fed = g_has_any_path(g, network.source_ids, target_id)
    if residual_nodes is not None and still_fed:
        reason = "locked_path"
    else:
        reason = "supply_conflict"

    return IsolationResult(
        feasible=False,
        target_id=target_id,
        required_supply_ids=required_supply_ids,
        plans=[],
        rejected_plans=rejected[:10],
        already_closed_valve_ids=already_closed,
        locked_valve_ids=locked,
        residual_path_node_ids=residual_nodes,
        residual_segment_ids=residual_segments,
        reason=reason,
    )


def g_has_any_path(g: nx.MultiDiGraph, sources: list[str], target: str) -> bool:
    return any(
        g.has_node(s) and nx.has_path(g, s, target) for s in sources
    )


def _with_locks(network: Network, locked_ids: set[str]) -> Network:
    valves = [
        Valve(
            id=v.id,
            segment_id=v.segment_id,
            label=v.label,
            is_open=v.is_open,
            is_locked=v.is_locked or v.id in locked_ids,
        )
        for v in network.valves
    ]
    return Network(
        nodes=network.nodes,
        segments=network.segments,
        valves=valves,
        source_ids=list(network.source_ids),
    )

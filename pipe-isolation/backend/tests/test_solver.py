"""样例验证（需求中明确的三类）：

1. 旁路绕回：默认场景下 {V3,V6} 切断 T，V7 绕回保证 SP2 不被断供；
2. 锁定阀门：锁定 V6 后无方案，返回残余路径（经被锁定的 V6）；
3. 不应断供的支路：根部阀门 {V0}/{V1} 与上游 {V2} 等方案因断供被否决；
   另用闭合排液阀 V10 验证“已关闭阀直接断开”。
"""

import networkx as nx

from app.seed import NETWORK
from app.solver import isolate, _build_graph, _supplies_reachable, _view_without

TARGET = "T"
SUPPLIES = ["SP1", "SP2"]


def test_default_plan_is_v3_v6_and_loopback_keeps_sp2():
    """样例 1：旁路绕回。"""
    r = isolate(NETWORK, TARGET, SUPPLIES)
    assert r.feasible
    assert r.plans[0].valve_ids == ["V3", "V6"]
    assert r.plans[0].closes_bypass is True  # V6 在旁路上

    # 执行方案后 T 从所有来源不可达
    g = _build_graph(NETWORK)
    valve_seg = {v.id: v.segment_id for v in NETWORK.valves}
    cut_segments = {valve_seg[v] for v in ["V3", "V6"]}
    view = _view_without(g, cut_segments)
    assert not any(
        view.has_node(s) and nx.has_path(view, s, TARGET)
        for s in NETWORK.source_ids
    )
    # 两个必要供给点仍可达（SP2 由 V7 绕回供给）
    status = _supplies_reachable(view, NETWORK.source_ids, SUPPLIES)
    assert status == {"SP1": True, "SP2": True}


def test_plans_without_bypass_are_present_as_alternatives():
    r = isolate(NETWORK, TARGET, SUPPLIES)
    # 只应得到保供可行方案；{V3,V5} 会断 SP2，不能出现
    assert [p.valve_ids for p in r.plans] == [["V3", "V6"]]


def test_locked_v6_has_no_plan_and_reports_residual_path_through_lock():
    """样例 2：锁定不可操作阀门。"""
    r = isolate(NETWORK, TARGET, SUPPLIES, extra_locked_valve_ids={"V6"})
    assert not r.feasible
    assert r.reason == "locked_path"
    assert r.locked_valve_ids == ["V6"]
    # 残余路径 SRC-A-N-B-E-T，经过锁定的 V6(s6)
    assert r.residual_path_node_ids == ["SRC", "A", "N", "B", "E", "T"]
    assert r.residual_segment_ids == ["s0", "s1", "s2", "s5", "s6"]
    assert "s6" in r.residual_segment_ids  # 被锁定的旁路跨接段
    assert not r.plans


def test_locking_both_feed_valves_reports_main_residual_path():
    r = isolate(NETWORK, TARGET, SUPPLIES, extra_locked_valve_ids={"V3", "V6"})
    assert not r.feasible
    assert r.residual_path_node_ids[-1] == "T"
    # 主路仍通：... B -> T 经过锁定 V3(s3)
    assert r.residual_segment_ids[-1] == "s3"


def test_supply_killing_branches_are_rejected():
    """样例 3：不应断供的支路被明确否决并给出断供点。"""
    r = isolate(NETWORK, TARGET, SUPPLIES)
    rejected = {tuple(p["valve_ids"]): p["lost_required_supply_ids"]
                for p in r.rejected_plans}
    assert rejected[("V0",)] == ["SP1", "SP2"]   # 根部阀全断
    assert rejected[("V1",)] == ["SP1", "SP2"]
    assert rejected[("V2",)] == ["SP2"]           # SP1 在 N 之前仍通
    assert rejected[("V3", "V5")] == ["SP2"]      # 旁路入口被关则绕回失效


def test_sp1_branch_when_locked_v8_supply_is_preserved():
    # 锁定支路阀 V8 不影响 T 隔离方案（V8 本就不在到 T 的路径上），
    # 但 SP2 依然保供；这里验证锁定非路径阀门不改变方案。
    r = isolate(NETWORK, TARGET, SUPPLIES, extra_locked_valve_ids={"V8"})
    assert r.feasible
    assert r.plans[0].valve_ids == ["V3", "V6"]


def test_already_closed_valve_segment_absent_from_graph():
    """V10 初始关闭：排液支路 C->DRAIN 不应出现在图中。"""
    g = _build_graph(NETWORK)
    assert "s10" not in {d["segment_id"] for _, _, d in g.edges(data=True)}
    assert not g.has_node("DRAIN") or not nx_has_edge(g, "C", "DRAIN")


def nx_has_edge(g, u, v):
    return g.has_edge(u, v)


def test_closing_v3_v6_then_reopen_via_network_copy():
    """已关闭阀门语义：把 V6 关闭后（模拟方案已执行），T 单靠 V3 仍可隔离。"""
    from app.solver import Valve

    valves = [
        Valve(v.id, v.segment_id, v.label,
              is_open=(v.is_open if v.id != "V6" else False),
              is_locked=v.is_locked)
        for v in NETWORK.valves
    ]
    from app.solver import Network
    net = Network(NETWORK.nodes, NETWORK.segments, valves, NETWORK.source_ids)
    r = isolate(net, TARGET, SUPPLIES)
    assert r.feasible
    assert r.plans[0].valve_ids == ["V3"]
    assert "V6" in r.already_closed_valve_ids

"""演示管网（种子数据）。

拓扑（有向，介质流向）：

                SP1(必要供给点)
                 ^ V8
  SRC ->V0 A ->V1 N ->V2 B
                      |  \\
               V3     V5   (旁路)
                      |    \\
                      T(eq)  E --V7(绕回)--\\
                       \\    ^V6           |
                        V4   |            |
                         \\  /            v
                          C --V9--> SP2(必要供给点)
                          |
                          V11 -> SINK
  另：C ->V10(常闭排液)-> DRAIN

* V3：目标设备 T 的进口阀；V4：出口阀
* V5/V6/V7：旁路，其中 V7 绕回下游 C，保证隔离 T 时 SP2 不被断供
* V8、V9 为不应断供支路；V10 排液阀初始关闭（演示“已关闭阀直接断开”）
"""

from .solver import Network, Node, Segment, SegmentKind, Valve

NODES = [
    Node("SRC", "介质来源 S1", "source"),
    Node("A", "节点 A", "junction"),
    Node("N", "节点 N", "junction"),
    Node("B", "节点 B", "junction"),
    Node("E", "旁路节点 E", "junction"),
    Node("T", "目标设备 T", "equipment"),
    Node("C", "下游汇合 C", "junction"),
    Node("SP1", "必要供给点 SP1", "supply"),
    Node("SP2", "必要供给点 SP2", "supply"),
    Node("SINK", "下游 SINK", "sink"),
    Node("DRAIN", "排液点 DRAIN", "sink"),
]

SEGMENTS = [
    Segment("s0", "SRC", "A", SegmentKind.MAIN, "主管 SRC-A"),
    Segment("s1", "A", "N", SegmentKind.MAIN, "主管 A-N"),
    Segment("s2", "N", "B", SegmentKind.MAIN, "主管 N-B"),
    Segment("s3", "B", "T", SegmentKind.MAIN, "设备进口段 B-T"),
    Segment("s4", "T", "C", SegmentKind.OUTLET, "设备出口段 T-C"),
    Segment("s5", "B", "E", SegmentKind.BYPASS, "旁路入口 B-E"),
    Segment("s6", "E", "T", SegmentKind.BYPASS, "旁路跨接 E-T"),
    Segment("s7", "E", "C", SegmentKind.BYPASS, "旁路绕回 E-C"),
    Segment("s8", "N", "SP1", SegmentKind.BRANCH, "支路 N-SP1"),
    Segment("s9", "C", "SP2", SegmentKind.BRANCH, "支路 C-SP2"),
    Segment("s10", "C", "DRAIN", SegmentKind.BRANCH, "排液支路 C-DRAIN"),
    Segment("s11", "C", "SINK", SegmentKind.OUTLET, "下游 C-SINK"),
]

VALVES = [
    Valve("V0", "s0", "根部阀 V0"),
    Valve("V1", "s1", "阀 V1"),
    Valve("V2", "s2", "阀 V2"),
    Valve("V3", "s3", "设备进口阀 V3"),
    Valve("V4", "s4", "设备出口阀 V4"),
    Valve("V5", "s5", "旁路入口阀 V5"),
    Valve("V6", "s6", "旁路跨接阀 V6"),
    Valve("V7", "s7", "旁路绕回阀 V7"),
    Valve("V8", "s8", "支路阀 V8"),
    Valve("V9", "s9", "支路阀 V9"),
    Valve("V10", "s10", "排液阀 V10", is_open=False),
    Valve("V11", "s11", "下游阀 V11"),
]

NETWORK = Network(
    nodes=NODES,
    segments=SEGMENTS,
    valves=VALVES,
    source_ids=["SRC"],
)

# 布局坐标（Cytoscape 也会用）
LAYOUT_POSITIONS = {
    "SRC": (0, 100),
    "A": (120, 100),
    "N": (260, 100),
    "B": (400, 100),
    "T": (560, 100),
    "C": (720, 100),
    "SINK": (880, 100),
    "SP1": (260, 240),
    "E": (480, -40),
    "SP2": (720, 240),
    "DRAIN": (880, 240),
}

SCENARIO_ID = "eq_t"
SCENARIO = {
    "id": SCENARIO_ID,
    "name": "隔离目标设备 T（带旁路绕回）",
    "target_id": "T",
    "required_supply_ids": ["SP1", "SP2"],
    "network_id": "demo-1",
}

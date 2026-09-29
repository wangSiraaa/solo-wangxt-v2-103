export interface NodeInfo {
  id: string;
  label: string;
  kind: 'source' | 'junction' | 'equipment' | 'supply' | 'sink';
  position: [number, number];
}

export interface SegmentInfo {
  id: string;
  source_id: string;
  target_id: string;
  kind: 'main' | 'bypass' | 'branch' | 'outlet';
  label: string;
  valve_id: string | null;
  valve_open: boolean;
  valve_locked: boolean;
}

export interface ValveInfo {
  valve_id: string;
  segment_id: string;
  label: string;
  is_open: boolean;
  is_locked: boolean;
}

export interface Scenario {
  id: string;
  name: string;
  target_id: string;
  required_supply_ids: string[];
  network_id: string;
}

export interface Topology {
  network_id: string;
  nodes: NodeInfo[];
  segments: SegmentInfo[];
  valves: ValveInfo[];
  source_ids: string[];
  scenarios: Scenario[];
  disclaimer: string;
}

export interface Plan {
  valve_ids: string[];
  closes_bypass: boolean;
}

export interface RejectedPlan {
  valve_ids: string[];
  lost_required_supply_ids: string[];
}

export interface IsolationResult {
  feasible: boolean;
  target_id: string;
  required_supply_ids: string[];
  plans: Plan[];
  rejected_plans: RejectedPlan[];
  already_closed_valve_ids: string[];
  locked_valve_ids: string[];
  residual_path_node_ids: string[] | null;
  residual_segment_ids: string[] | null;
  reason: 'locked_path' | 'supply_conflict' | null;
}

import {
  AfterViewInit,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  Output,
  ViewChild,
} from '@angular/core';
import cytoscape, { Core, NodeSingular } from 'cytoscape';
import { IsolationResult, Topology } from '../../models/topology';

/**
 * Cytoscape 管网视图。
 * - 管段方向用箭头表示；主路蓝灰、旁路蓝色虚线、支路青色。
 * - 阀门为菱形：绿色=开启，红色=已关闭，黄色=锁定不可操作。
 * - 单击阀门：切换“锁定/解锁”（仅前端临时状态，触发 lockToggle）。
 */
@Component({
  selector: 'app-topology',
  standalone: true,
  template: `<div #cy class="cy"></div>`,
  styles: [
    `
      .cy {
        width: 100%;
        height: 100%;
        min-height: 560px;
        background: #0f1420;
        border: 1px solid var(--border);
        border-radius: 8px;
      }
    `,
  ],
})
export class TopologyComponent implements AfterViewInit, OnChanges {
  @Input() topology: Topology | null = null;
  @Input() result: IsolationResult | null = null;
  @Input() scenarioId = 'eq_t';
  @Input() transientLocks: Set<string> = new Set();

  @Output() lockToggle = new EventEmitter<string>();

  @ViewChild('cy') cyRef!: ElementRef<HTMLDivElement>;

  private cy: Core | null = null;

  ngAfterViewInit(): void {
    this.render();
  }

  ngOnChanges(): void {
    if (this.cy) {
      this.render();
    }
  }

  private render(): void {
    if (!this.topology) return;
    const topo = this.topology;

    const scenario = topo.scenarios.find((s) => s.id === this.scenarioId);
    const targetId = scenario?.target_id ?? '';
    const supplies = new Set(scenario?.required_supply_ids ?? []);

    const elements: any[] = [];
    for (const n of topo.nodes) {
      elements.push({
        data: {
          id: n.id,
          label: n.label,
          kind: n.kind,
          isTarget: n.id === targetId,
          isSupply: supplies.has(n.id),
        },
        position: { x: n.position[0], y: n.position[1] },
      });
    }

    const pos = (id: string) => topo.nodes.find((x) => x.id === id)!.position;

    for (const seg of topo.segments) {
      const p1 = pos(seg.source_id);
      const p2 = pos(seg.target_id);
      const mid = { x: (p1[0] + p2[0]) / 2, y: (p1[1] + p2[1]) / 2 };

      if (seg.valve_id) {
        const v = topo.valves.find((x) => x.valve_id === seg.valve_id)!;
        const transient = this.transientLocks.has(v.valve_id);
        const valveNodeId = `valve:${v.valve_id}`;
        elements.push({
          data: {
            id: valveNodeId,
            label: v.valve_id,
            kind: 'valve',
            valveId: v.valve_id,
            valveOpen: v.is_open,
            valveLocked: v.is_locked || transient,
            transientLock: transient,
            segKind: seg.kind,
            segId: seg.id,
          },
          position: mid,
        });
        elements.push(this.edgeEl(seg, 'a', seg.source_id, valveNodeId));
        elements.push(this.edgeEl(seg, 'b', valveNodeId, seg.target_id));
      } else {
        const midId = `mid:${seg.id}`;
        elements.push({
          data: { id: midId, label: '', kind: 'mid', segKind: seg.kind, segId: seg.id },
          position: mid,
        });
        elements.push(this.edgeEl(seg, 'a', seg.source_id, midId));
        elements.push(this.edgeEl(seg, 'b', midId, seg.target_id));
      }
    }

    this.cy = cytoscape({
      container: this.cyRef.nativeElement,
      elements,
      wheelSensitivity: 0.2,
      minZoom: 0.3,
      maxZoom: 2.5,
      style: this.cyStyle(),
    });

    this.cy.nodes('[kind = "valve"]').on('click', (evt) => {
      const node = evt.target as NodeSingular;
      this.lockToggle.emit(node.data('valveId'));
    });

    this.applyResultHighlight();
    setTimeout(() => this.cy?.fit(undefined, 50), 0);
  }

  private edgeEl(seg: any, suffix: string, source: string, target: string) {
    return {
      data: {
        id: `${seg.id}:${suffix}`,
        source,
        target,
        segId: seg.id,
        segKind: seg.kind,
        open: seg.valve_id !== null && seg.valve_open,
      },
    };
  }

  private cyStyle(): any[] {
    return [
      {
        selector: 'node',
        style: {
          label: 'data(label)',
          'font-size': 11,
          color: '#cfe0f5',
          'text-valign': 'bottom',
          'text-margin-y': 6,
          'background-color': '#3a4a63',
          width: 26,
          height: 26,
          'border-width': 1,
          'border-color': '#90a6c4',
        },
      },
      { selector: 'node[kind = "source"]', style: { 'background-color': '#2b6cb0', shape: 'round-tag', width: 36, height: 36 } },
      { selector: 'node[kind = "sink"]', style: { 'background-color': '#4a5568', shape: 'barrel' } },
      {
        selector: 'node[kind = "equipment"]',
        style: { shape: 'round-rectangle', width: 48, height: 36, 'background-color': '#6b46c1', 'border-color': '#b794f4', 'border-width': 2 },
      },
      { selector: 'node[?isTarget]', style: { 'border-color': '#ff5c5c', 'border-width': 4 } },
      {
        selector: 'node[?isSupply]',
        style: { 'background-color': '#2f855a', shape: 'diamond', width: 40, height: 40, 'border-color': '#68d391' },
      },
      {
        selector: 'node[kind = "valve"]',
        style: {
          shape: 'diamond',
          width: 22,
          height: 22,
          'background-color': '#3fbf7f',
          'border-color': '#c6f6d5',
          'font-size': 10,
          'text-valign': 'top',
          'text-margin-y': 4,
          label: (n: NodeSingular) =>
            `${n.data('label')}${n.data('valveLocked') ? ' 🔒' : ''}${n.data('valveOpen') ? '' : ' ✖'}`,
        },
      },
      {
        selector: 'node[kind = "valve"][?valveLocked]',
        style: { 'background-color': '#d69e2e', 'border-color': '#f6e05e' },
      },
      {
        selector: 'node[kind = "valve"][!valveOpen]',
        style: { 'background-color': '#c53030', 'border-color': '#feb2b2' },
      },
      { selector: 'node[kind = "mid"]', style: { width: 5, height: 5, label: '', 'background-color': '#5a6b85' } },
      {
        selector: 'edge',
        style: {
          width: 2.5,
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'arrow-scale': 1.1,
          'line-color': '#6b88ad',
          'target-arrow-color': '#6b88ad',
        },
      },
      {
        selector: 'edge[segKind = "bypass"]',
        style: { 'line-color': '#4fa8ff', 'target-arrow-color': '#4fa8ff', 'line-style': 'dashed' },
      },
      {
        selector: 'edge[segKind = "branch"]',
        style: { 'line-color': '#38b2ac', 'target-arrow-color': '#38b2ac' },
      },
      {
        selector: 'edge[!open]',
        style: { 'line-style': 'dotted', 'line-color': '#9a4444', 'target-arrow-color': '#9a4444' },
      },
      {
        selector: 'node.plan-close',
        style: { 'background-color': '#ff5c5c', 'border-color': '#ffffff', 'border-width': 3, width: 28, height: 28 },
      },
      {
        selector: 'edge.residual',
        style: { 'line-color': '#ffb020', 'target-arrow-color': '#ffb020', width: 4.5, 'line-style': 'solid' },
      },
      { selector: 'node.residual', style: { 'border-color': '#ffb020', 'border-width': 3 } },
      {
        selector: 'node.rejected',
        style: { 'border-color': '#a0522d', 'border-width': 2, 'border-style': 'dashed' },
      },
    ];
  }

  private applyResultHighlight(): void {
    if (!this.cy || !this.result) return;
    const r = this.result;

    r.plans.forEach((p) =>
      p.valve_ids.forEach((vid) => this.cy!.$id(`valve:${vid}`).addClass('plan-close')),
    );

    r.residual_segment_ids?.forEach((sid) =>
      this.cy!.edges(`[segId = "${sid}"]`).addClass('residual'),
    );
    r.residual_path_node_ids?.forEach((nid) =>
      this.cy!.$id(nid).addClass('residual'),
    );
    r.rejected_plans.forEach((p) =>
      p.valve_ids.forEach((vid) => this.cy!.$id(`valve:${vid}`).addClass('rejected')),
    );
  }
}

import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from './services/api.service';
import { IsolationResult, Topology, ValveInfo } from './models/topology';
import { TopologyComponent } from './components/topology/topology.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [FormsModule, TopologyComponent],
  template: `
    <div class="page">
      <header>
        <h1>工艺管网隔离方案演示</h1>
        <p class="sub">
          Angular + Cytoscape.js 拓扑 · FastAPI + NetworkX 候选隔离集合 ·
          PostgreSQL 连接/阀态/供给点
        </p>
      </header>

      @if (errorMsg()) {
        <div class="error">{{ errorMsg() }}</div>
      }

      <div class="layout">
        <div class="graph-panel">
          <app-topology
            [topology]="topology()"
            [result]="result()"
            [scenarioId]="scenarioId"
            [transientLocks]="transientLocks"
            (lockToggle)="onLockToggle($event)"
          />
          <p class="hint">
            单击阀门菱形 = 锁定/解锁（不可操作，临时）；
            阀门颜色：绿=开启，红=已关闭，黄=锁定；
            蓝色虚线=旁路，青色=支路；箭头=管段介质流向。
          </p>
        </div>

        <aside class="side">
          <section class="card">
            <h2>隔离任务</h2>
            @if (topology(); as t) {
              @for (sc of t.scenarios; track sc.id) {
                <label class="scenario">
                  <input
                    type="radio"
                    name="scenario"
                    [value]="sc.id"
                    [(ngModel)]="scenarioId"
                    (change)="recompute()"
                  />
                  <span>{{ sc.name }}</span>
                </label>
                <p class="meta">
                  目标设备：<b>{{ labelOf(sc.target_id) }}</b
                  ><br />
                  必要供给点：
                  <b>{{ labelsOf(sc.required_supply_ids).join('、') }}</b>
                </p>
              }
            }
            <button class="primary" (click)="recompute()" [disabled]="loading()">
              {{ loading() ? '计算中…' : '重新计算候选方案' }}
            </button>
            <button class="ghost" (click)="resetAll()">恢复初始阀态</button>
          </section>

          @if (result(); as r) {
            <section class="card">
              <h2>计算结果</h2>
              @if (r.feasible) {
                <div class="ok">✓ 找到 {{ r.plans.length }} 个候选隔离集合（均保供）</div>
                @for (plan of r.plans; track $index) {
                  <div class="plan">
                    <div class="plan-title">
                      方案 {{ $index + 1 }}：关闭
                      <span class="valves">{{ plan.valve_ids.join(' + ') }}</span>
                      @if (plan.closes_bypass) {
                        <span class="tag bypass">含旁路阀</span>
                      }
                    </div>
                    <ul>
                      <li>关闭后目标 <b>{{ labelOf(r.target_id) }}</b> 与所有来源断开</li>
                      @for (sp of r.required_supply_ids; track sp) {
                        <li class="ok-text">供给点 {{ labelOf(sp) }} 仍可达</li>
                      }
                    </ul>
                  </div>
                }
              } @else {
                <div class="bad">✗ 当前条件下找不到可行隔离方案</div>
                @if (r.reason === 'locked_path') {
                  <p class="meta">
                    原因：存在仍连通的路径，且其上阀门被锁定不可操作或已无阀可切。
                  </p>
                } @else {
                  <p class="meta">原因：任何切法都会断供必要供给点。</p>
                }
                @if (r.residual_path_node_ids; as path) {
                  <div class="residual-box">
                    <div class="residual-title">仍然连通的残余路径（橙色高亮）：</div>
                    <div class="path-chain">
                      {{ labelsOf(path).join('  →  ') }}
                    </div>
                    <div class="path-ids">
                      管段：{{ r.residual_segment_ids?.join(' → ') }}
                    </div>
                  </div>
                }
              }

              @if (r.rejected_plans.length) {
                <details>
                  <summary>被否决的切法（断供，{{ r.rejected_plans.length }}）</summary>
                  @for (rp of r.rejected_plans; track $index) {
                    <div class="rejected">
                      <span class="valves">{{ rp.valve_ids.join(' + ') }}</span>
                      → 断供：
                      <span class="bad-text">{{
                        labelsOf(rp.lost_required_supply_ids).join('、')
                      }}</span>
                    </div>
                  }
                </details>
              }

              <div class="state-line">
                已关闭：{{ r.already_closed_valve_ids.join(', ') || '无' }} ｜
                锁定：{{ r.locked_valve_ids.join(', ') || '无' }}
              </div>
            </section>
          }

          <section class="card">
            <h2>阀门操作</h2>
            @if (topology(); as t) {
              <div class="valve-grid">
                @for (v of t.valves; track v.valve_id) {
                  <div
                    class="valve-row"
                    [class.row-open]="v.is_open"
                    [class.row-closed]="!v.is_open"
                  >
                    <span class="vname">{{ v.valve_id }}</span>
                    <span class="vlabel">{{ v.label.replace(v.valve_id, '').trim() }}</span>
                    <button
                      class="mini"
                      [class.on]="v.is_open"
                      (click)="setOpen(v, true)"
                    >
                      开
                    </button>
                    <button
                      class="mini"
                      [class.off]="!v.is_open"
                      (click)="setOpen(v, false)"
                    >
                      关
                    </button>
                    <button
                      class="mini"
                      [class.warn-on]="transientLocks.has(v.valve_id) || v.is_locked"
                      (click)="onLockToggle(v.valve_id)"
                    >
                      {{ transientLocks.has(v.valve_id) || v.is_locked ? '解锁' : '锁定' }}
                    </button>
                  </div>
                }
              </div>
            }
          </section>
        </aside>
      </div>

      <footer class="disclaimer">
        ⚠ {{ disclaimer() }}
      </footer>
    </div>
  `,
  styles: [
    `
      .page { max-width: 1400px; margin: 0 auto; padding: 18px 22px 40px; }
      header h1 { margin: 0 0 4px; font-size: 22px; }
      .sub { margin: 0 0 14px; color: #8da2c0; font-size: 13px; }
      .layout { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 16px; align-items: start; }
      .card {
        background: var(--panel);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 14px;
        margin-bottom: 14px;
      }
      h2 { margin: 0 0 10px; font-size: 15px; color: #a9c3e8; }
      .scenario { display: flex; gap: 8px; align-items: center; font-weight: 600; }
      .meta { font-size: 12.5px; color: #9fb2cc; margin: 6px 0 12px; line-height: 1.7; }
      button {
        cursor: pointer;
        border-radius: 6px;
        border: 1px solid var(--border);
        padding: 8px 12px;
        background: #223047;
        color: #dbe7f7;
        font-size: 13px;
      }
      button:hover { border-color: var(--accent); }
      button:disabled { opacity: .5; cursor: default; }
      .primary { background: #2b6cb0; border-color: #3b82c4; width: 100%; margin-bottom: 6px; }
      .ghost { width: 100%; }
      .ok { color: var(--ok); font-weight: 700; margin-bottom: 10px; }
      .ok-text { color: var(--ok); }
      .bad { color: var(--bad); font-weight: 700; margin-bottom: 8px; }
      .bad-text { color: var(--bad); }
      .plan { border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; background: #131b29; }
      .plan-title { font-size: 13.5px; margin-bottom: 4px; }
      .valves { color: #ffb4b4; font-weight: 700; letter-spacing: .5px; }
      .tag { font-size: 11px; padding: 1px 7px; border-radius: 10px; margin-left: 6px; }
      .tag.bypass { background: #1c4a78; color: #9cd0ff; }
      ul { margin: 4px 0 0; padding-left: 18px; font-size: 12.5px; color: #b8c8df; line-height: 1.7; }
      .residual-box { background: #33270a; border: 1px solid #7a5a1a; border-radius: 6px; padding: 10px; margin: 8px 0; }
      .residual-title { color: var(--warn); font-weight: 700; font-size: 13px; margin-bottom: 6px; }
      .path-chain { font-size: 13px; line-height: 1.7; color: #ffe2a8; }
      .path-ids { font-size: 11.5px; color: #b59a5f; margin-top: 4px; word-break: break-all; }
      .rejected { font-size: 12.5px; padding: 4px 0; border-bottom: 1px dashed #2a3548; }
      details { margin-top: 8px; font-size: 13px; }
      summary { cursor: pointer; color: #a9c3e8; }
      .state-line { margin-top: 10px; font-size: 12px; color: #8da2c0; }
      .valve-grid { display: flex; flex-direction: column; gap: 4px; max-height: 320px; overflow-y: auto; }
      .valve-row { display: grid; grid-template-columns: 34px 1fr auto auto auto; gap: 4px; align-items: center; font-size: 12px; padding: 3px 4px; border-radius: 4px; }
      .valve-row.row-closed { background: #3a1d1d; }
      .vname { font-weight: 700; color: #cfe0f5; }
      .vlabel { color: #93a6c2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .mini { padding: 3px 8px; font-size: 11.5px; }
      .mini.on { background: #1f5132; border-color: #3fbf7f; }
      .mini.off { background: #6e2424; border-color: #ff5c5c; }
      .mini.warn-on { background: #7a5a1a; border-color: #ffb020; color: #ffe2a8; }
      .hint { font-size: 12px; color: #8da2c0; margin: 8px 2px; }
      .error { background: #4a1d1d; border: 1px solid #a04040; padding: 10px 14px; border-radius: 6px; margin-bottom: 12px; }
      .disclaimer {
        margin-top: 18px; padding: 10px 14px; font-size: 12.5px;
        background: #2b2313; border: 1px solid #7a5a1a; border-radius: 6px; color: #ffd98a;
      }
      @media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
    `,
  ],
})
export class AppComponent implements OnInit {
  private api = inject(ApiService);

  topology = signal<Topology | null>(null);
  result = signal<IsolationResult | null>(null);
  loading = signal(false);
  errorMsg = signal('');
  disclaimer = signal('');

  scenarioId = 'eq_t';
  transientLocks = new Set<string>();

  ngOnInit(): void {
    this.api.getTopology().subscribe({
      next: (t) => {
        this.topology.set(t);
        this.disclaimer.set(t.disclaimer);
        this.recompute();
      },
      error: (e) =>
        this.errorMsg.set(
          '加载拓扑失败：' + (e?.message ?? e) + '（请确认后端已启动）',
        ),
    });
  }

  labelOf(id: string): string {
    return this.topology()?.nodes.find((n) => n.id === id)?.label ?? id;
  }

  labelsOf(ids: string[]): string[] {
    return ids.map((id) => this.labelOf(id));
  }

  recompute(): void {
    this.loading.set(true);
    this.api
      .computeIsolation(this.scenarioId, [...this.transientLocks])
      .subscribe({
        next: (r) => {
          this.result.set(r);
          this.loading.set(false);
        },
        error: (e) => {
          this.errorMsg.set('计算失败：' + (e?.error?.detail ?? e?.message ?? e));
          this.loading.set(false);
        },
      });
  }

  onLockToggle(valveId: string): void {
    if (this.transientLocks.has(valveId)) {
      this.transientLocks.delete(valveId);
    } else {
      this.transientLocks.add(valveId);
    }
    // 触发视图更新（Set 引用不变时手动复制）
    this.transientLocks = new Set(this.transientLocks);
    this.recompute();
  }

  setOpen(v: ValveInfo, isOpen: boolean): void {
    this.api.setValveState(v.valve_id, { is_open: isOpen }).subscribe({
      next: () => this.reloadTopology(),
      error: (e) => this.errorMsg.set(String(e?.message ?? e)),
    });
  }

  resetAll(): void {
    this.api.reset().subscribe(() => {
      this.transientLocks = new Set();
      this.reloadTopology();
    });
  }

  private reloadTopology(): void {
    this.api.getTopology().subscribe((t) => {
      this.topology.set(t);
      this.recompute();
    });
  }
}

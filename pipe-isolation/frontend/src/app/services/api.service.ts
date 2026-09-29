import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { IsolationResult, Topology, ValveInfo } from '../models/topology';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);
  private base = '/api';

  getTopology(): Observable<Topology> {
    return this.http.get<Topology>(`${this.base}/topology`);
  }

  computeIsolation(
    scenarioId: string,
    lockedValveIds: string[],
  ): Observable<IsolationResult> {
    return this.http.post<IsolationResult>(`${this.base}/isolation`, {
      scenario_id: scenarioId,
      locked_valve_ids: lockedValveIds,
    });
  }

  setValveState(
    valveId: string,
    state: { is_open?: boolean; is_locked?: boolean },
  ): Observable<ValveInfo> {
    return this.http.patch<ValveInfo>(`${this.base}/valves/${valveId}`, state);
  }

  reset(): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${this.base}/reset`, {});
  }
}

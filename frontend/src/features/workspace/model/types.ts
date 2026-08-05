import type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRoutePlan,
  MakersRouteStrategy,
} from '../../maps/model';

export type WorkspaceActionKind = 'map_recommendation' | 'calendar_changes' | 'meeting_create' | 'image_generate';
export type WorkspaceActionStatus = 'ready' | 'active' | 'awaiting_confirmation' | 'executing' | 'succeeded' | 'failed' | 'cancelled' | 'reconciliation_required';

/** Versioned proposal contract; no client may bypass its confirmation state. */
export interface WorkspaceAction {
  schema_version: number;
  id: string;
  kind: WorkspaceActionKind;
  status: WorkspaceActionStatus;
  version: number;
  payload: {
    title?: string;
    action_text?: string;
    places?: MakersMapPlace[];
    route_mode?: MakersRouteMode;
    route_strategy?: MakersRouteStrategy;
    route?: MakersRoutePlan;
    show_route?: boolean;
    route_plan_id?: string;
    calendar_offer?: boolean;
    summary?: string;
    changes?: Array<Record<string, unknown>>;
    subject?: string;
    start_time?: string;
    end_time?: string;
    warnings?: string[];
    missing_fields?: string[];
    validation_errors?: string[];
    prompt?: string;
    parent_action_id?: string;
    group_id?: string;
  };
  result?: Record<string, unknown> | null;
  error?: string;
  snapshot_hash?: string;
  idempotency_key?: string;
  attempt?: number;
  lease_owner?: string;
  lease_until?: number;
  provider_request_id?: string;
  reconciliation_required?: boolean;
  created_at?: number;
  updated_at?: number;
}

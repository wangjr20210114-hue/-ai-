import type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRouteStrategy,
  ScheduleItem,
  TravelPlan,
  WorkspaceAction,
} from '../../../shared/types';

export type { ScheduleItem, WorkspaceAction } from '../../../shared/types';

export interface CalendarWorkspaceResponse {
  revision: number;
  schedules: ScheduleItem[];
  map?: {
    action_id: string;
    title: string;
    places: MakersMapPlace[];
    route_mode?: MakersRouteMode | '';
    route_strategy?: MakersRouteStrategy | '';
    show_route?: boolean;
  } | null;
  action?: WorkspaceAction;
  actions?: WorkspaceAction[];
  changed?: Array<ScheduleItem & { deleted?: boolean }>;
  skipped?: Array<{ operation: string; target: string; reason: string }>;
  travel_plan?: TravelPlan;
  travel_plans?: TravelPlan[];
  deleted_plan_id?: string;
}

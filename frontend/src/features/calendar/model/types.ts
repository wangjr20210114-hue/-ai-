import type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRoutePlan,
  MakersRouteStrategy,
} from '../../maps/model';
import type { WorkspaceAction } from '../../workspace/model';

export interface TravelPlan {
  id: string;
  session_id: string;
  title: string;
  departure: string;
  destination: string;
  days: number;
  travel_style: string;
  scenery_preference: string;
  budget: string;
  extra_notes: string;
  markdown_content: string;
  baike_info: {
    summary?: string;
    highlights?: string[];
    best_season?: string;
    error?: string;
    [key: string]: unknown;
  };
  created_at: number;
  updated_at: number;
}

export type ScheduleCategory = 'travel' | 'meeting' | 'dining' | 'remind' | 'task' | 'other';

export interface ScheduleItem {
  id: string;
  session_id: string;
  title: string;
  category: ScheduleCategory;
  start_time: number;
  duration_minutes: number;
  duration_days: number;
  location: string;
  description: string;
  markdown_content: string;
  extra: {
    search_query?: string;
    search_keyword?: string;
    city?: string;
    cost_estimate?: number;
    description?: string;
    place_type?: string;
    place?: MakersMapPlace;
    [key: string]: unknown;
  };
  done: boolean;
  created_at: number;
  updated_at: number;
}

export type { WorkspaceAction } from '../../workspace/model';

export interface CalendarWorkspaceResponse {
  revision: number;
  schedules: ScheduleItem[];
  map?: {
    action_id: string;
    title: string;
    places: MakersMapPlace[];
    route_mode?: MakersRouteMode | '';
    route_strategy?: MakersRouteStrategy | '';
    route?: MakersRoutePlan;
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

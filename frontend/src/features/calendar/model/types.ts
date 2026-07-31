export type { ScheduleItem, WorkspaceAction } from '../../../shared/types';

export interface CalendarWorkspaceResponse {
  revision: number;
  schedules: import('../../../shared/types').ScheduleItem[];
  action?: import('../../../shared/types').WorkspaceAction;
}

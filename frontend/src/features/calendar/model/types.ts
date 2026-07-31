export type { ScheduleItem, WorkspaceAction } from '../../../types';

export interface CalendarWorkspaceResponse {
  revision: number;
  schedules: import('../../../types').ScheduleItem[];
  action?: import('../../../types').WorkspaceAction;
}

import type { ScheduleItem } from '../../calendar/model';
import type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRoutePlan,
  MakersRouteStrategy,
} from './types';

export function shouldPlanMakersRoute(showRoute: boolean, placesCount: number): boolean {
  return showRoute && placesCount >= 2;
}

export function shouldRequestMakersRoute(
  showRoute: boolean,
  placesCount: number,
  snapshot?: MakersRoutePlan,
): boolean {
  return shouldPlanMakersRoute(showRoute, placesCount) && !snapshot?.places?.length;
}

/** A schedule's time order is authoritative; route distance must never reorder it. */
export function chronologicalSchedulePlaces(items: ScheduleItem[]): MakersMapPlace[] {
  const ordered = items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => a.item.start_time - b.item.start_time || a.index - b.index)
    .map(({ item }) => item.extra?.place)
    .filter((place): place is MakersMapPlace => Boolean(place));
  return ordered.filter((place, index) => (
    index === 0 || place.place_id !== ordered[index - 1].place_id
  ));
}

export function scheduleRoutePreferences(items: ScheduleItem[]): {
  mode?: MakersRouteMode;
  strategy?: MakersRouteStrategy;
} {
  const modes = new Set(items.map((item) => item.extra?.route_mode).filter(Boolean));
  const strategies = new Set(items.map((item) => item.extra?.route_strategy).filter(Boolean));
  const mode = modes.size === 1 ? [...modes][0] : undefined;
  const strategy = strategies.size === 1 ? [...strategies][0] : undefined;
  return {
    ...(mode && ['driving', 'transit', 'walking', 'bicycling'].includes(mode) ? { mode } : {}),
    ...(strategy && ['time_then_cost', 'least_time', 'least_cost'].includes(strategy) ? { strategy } : {}),
  };
}

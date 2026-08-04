import type { ScheduleItem } from '../../calendar/model';
import type { MakersMapPlace, MakersRoutePlan } from './types';

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
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => a.item.start_time - b.item.start_time || a.index - b.index)
    .map(({ item }) => item.extra?.place)
    .filter((place): place is MakersMapPlace => Boolean(place));
}

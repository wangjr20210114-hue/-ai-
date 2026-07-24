import type { MakersMapPlace, ScheduleItem } from '../../types';

export function shouldPlanMakersRoute(showRoute: boolean, placesCount: number): boolean {
  return showRoute && placesCount >= 2;
}

/** A schedule's time order is authoritative; route distance must never reorder it. */
export function chronologicalSchedulePlaces(items: ScheduleItem[]): MakersMapPlace[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => a.item.start_time - b.item.start_time || a.index - b.index)
    .map(({ item }) => item.extra?.place)
    .filter((place): place is MakersMapPlace => Boolean(place));
}

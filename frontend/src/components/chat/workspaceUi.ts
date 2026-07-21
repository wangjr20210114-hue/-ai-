import type { WorkspaceAction } from '../../types';

export function nextWholeHourRange(now = new Date()): { start: string; end: string } {
  const start = new Date(now);
  start.setSeconds(0, 0);
  start.setMinutes(0);
  start.setHours(start.getHours() + 1);
  const end = new Date(start.getTime() + 60 * 60_000);
  return { start: start.toISOString(), end: end.toISOString() };
}

/** A map Action may reveal only its frozen, server-verified usable snapshot. */
export function usableMapPlaces(action: WorkspaceAction) {
  return (action.payload.places || []).filter((place) => (
    Boolean(place.place_id && place.name)
    && Number.isFinite(place.latitude)
    && Number.isFinite(place.longitude)
    && Math.abs(place.latitude) <= 90
    && Math.abs(place.longitude) <= 180
  ));
}

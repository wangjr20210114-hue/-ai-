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

/** Build the minimal, non-sensitive signal used after a successful image Action. */
export function generatedImageOpportunitySignal(action: WorkspaceAction) {
  const prompt = String(action.payload.prompt || action.result?.prompt || '').trim();
  if (action.kind !== 'image_generate' || action.status !== 'succeeded' || !prompt) return null;
  const hasPreviousVersion = Boolean(action.payload.parent_action_id);
  return {
    signal_type: 'image_generated',
    dedup_key: action.id,
    payload: {
      action_id: action.id,
      prompt,
      has_reference_image: hasPreviousVersion,
      has_previous_version: hasPreviousVersion,
    },
  };
}

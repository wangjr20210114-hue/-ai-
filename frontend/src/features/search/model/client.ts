import type { SearchEvent } from './types';


export const routes = Object.freeze([] as string[]);

export function parseSearchEvent(value: unknown): SearchEvent | null {
  if (!value || typeof value !== 'object') return null;
  const event = value as Record<string, unknown>;
  if (!['stage', 'sources', 'media'].includes(String(event.type || ''))) return null;
  if (!event.payload || typeof event.payload !== 'object') return null;
  return event as unknown as SearchEvent;
}

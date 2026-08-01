import { requestJson } from '../../../shared/transport/httpClient';
import type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRoutePlan,
  MakersRouteStrategy,
} from '../../../shared/types';


export const routes = Object.freeze(['/places', '/routes']);

export function searchPlaces<T>(
  conversationId: string,
  input: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>('/places', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify(input),
  });
}

export function planRoute<T>(
  conversationId: string,
  input: Record<string, unknown>,
): Promise<T> {
  return requestJson<T>('/routes', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'makers-conversation-id': conversationId,
    },
    body: JSON.stringify(input),
  });
}

export async function searchMakersPlaces(
  conversationId: string,
  query: string,
  city = '全国',
): Promise<MakersMapPlace[]> {
  const data = await searchPlaces<{ places?: MakersMapPlace[] }>(
    conversationId,
    { query, city, limit: 10 },
  );
  return data.places || [];
}

export async function planMakersRoute(
  conversationId: string,
  places: MakersMapPlace[],
  mode?: MakersRouteMode,
  strategy?: MakersRouteStrategy,
): Promise<MakersRoutePlan> {
  const data = await planRoute<{ route?: MakersRoutePlan }>(conversationId, {
    places,
    ...(mode ? { mode } : {}),
    ...(strategy ? { strategy } : {}),
    optimize: false,
  });
  if (!data.route) throw new Error('Route provider returned no route');
  return data.route;
}

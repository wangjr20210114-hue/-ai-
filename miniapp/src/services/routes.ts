import { apiRequest } from './request'

export type RoutePlace = {
  place_id?: string
  name?: string
  address?: string
  latitude: number
  longitude: number
}

export type PlannedRoute = {
  path?: Array<{ latitude: number; longitude: number }>
  distance_meters?: number
  duration_seconds?: number
}

/** Invalid coordinates must not make one bad result break the whole native map. */
export function validRoutePlaces(places: RoutePlace[]): RoutePlace[] {
  return places.filter((place) => {
    const latitude = Number(place.latitude)
    const longitude = Number(place.longitude)
    return (
      Number.isFinite(latitude)
      && Number.isFinite(longitude)
      && latitude >= -90
      && latitude <= 90
      && longitude >= -180
      && longitude <= 180
    )
  })
}

export function orderedRoutePayload(
  places: RoutePlace[],
  mode?: string,
  strategy?: string,
): {
  places: RoutePlace[]
  mode?: string
  strategy?: string
  optimize: false
} {
  return {
    // The Agent has already resolved and frozen the user's stop order. The
    // native map may render it, but must never optimize or reorder it.
    places: places.map((place) => ({ ...place })),
    ...(mode ? { mode } : {}),
    ...(strategy ? { strategy } : {}),
    optimize: false,
  }
}

export function planOrderedRoute(
  conversationId: string,
  places: RoutePlace[],
  mode?: string,
  strategy?: string,
): Promise<{ route?: PlannedRoute }> {
  return apiRequest<{ route?: PlannedRoute }>('/routes', {
    method: 'POST',
    conversationId,
    data: orderedRoutePayload(places, mode, strategy),
    timeout: 30_000,
  })
}

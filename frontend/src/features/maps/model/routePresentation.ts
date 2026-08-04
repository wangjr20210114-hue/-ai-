import type {
  MakersMapPlace,
  MakersRouteLeg,
  MakersRouteMode,
  MakersRoutePlan,
  MakersRouteSection,
  MakersRouteSectionMode,
} from './types';

export type RouteZoomLevel = 'overview' | 'legs' | 'sections';

export const ROUTE_MODE_COLORS: Record<MakersRouteSectionMode, string> = {
  driving: '#e5484d',
  transit: '#2f6fed',
  bus: '#2f6fed',
  rail: '#7c3aed',
  walking: '#2e9d67',
  bicycling: '#ed8b2c',
};

export function routeZoomLevel(zoom: number): RouteZoomLevel {
  if (zoom <= 8) return 'overview';
  if (zoom <= 12) return 'legs';
  return 'sections';
}

function fallbackSection(
  mode: MakersRouteMode,
  path: MakersRoutePlan['path'],
  distance: number,
  duration: number,
): MakersRouteSection {
  return {
    mode,
    path,
    distance_meters: distance,
    duration_seconds: duration,
  };
}

export function routeLegs(route: MakersRoutePlan): MakersRouteLeg[] {
  if (route.legs?.length) return route.legs;
  if (route.places.length < 2) return [];
  return [{
    from: route.places[0],
    to: route.places[route.places.length - 1],
    mode: route.mode,
    path: route.path,
    sections: [fallbackSection(
      route.mode,
      route.path,
      route.distance_meters,
      route.duration_seconds,
    )],
    distance_meters: route.distance_meters,
    duration_seconds: route.duration_seconds,
  }];
}

export function visibleRouteSections(route: MakersRoutePlan): MakersRouteSection[] {
  const legs = routeLegs(route);
  const sections = legs.flatMap((leg) => leg.sections || []);
  return sections.length
    ? sections
    : [fallbackSection(route.mode, route.path, route.distance_meters, route.duration_seconds)];
}

export function routeCities(places: MakersMapPlace[]): Array<{
  city: string;
  place: MakersMapPlace;
}> {
  const seen = new Set<string>();
  const result: Array<{ city: string; place: MakersMapPlace }> = [];
  places.forEach((place) => {
    const city = String(place.city || '').trim();
    if (!city || seen.has(city)) return;
    seen.add(city);
    result.push({ city, place });
  });
  return result;
}

export function legModeSequence(leg: MakersRouteLeg): MakersRouteSectionMode[] {
  const result: MakersRouteSectionMode[] = [];
  (leg.sections || []).forEach((section) => {
    if (result[result.length - 1] !== section.mode) result.push(section.mode);
  });
  return result.length ? result : [leg.mode];
}

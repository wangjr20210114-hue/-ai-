import type {
  MakersMapPlace,
  MakersRouteLeg,
  MakersRouteMode,
  MakersRoutePlan,
  MakersRouteSection,
  MakersRouteSectionMode,
} from './types';

export type RouteZoomLevel = 'overview' | 'legs' | 'sections';

export interface RouteSectionStep {
  leg: MakersRouteLeg;
  legIndex: number;
  section: MakersRouteSection;
  sectionIndex: number;
}

export interface RouteMapPoint {
  latitude: number;
  longitude: number;
}

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

export function routeLegScope(
  leg: MakersRouteLeg,
): 'intercity' | 'local' | 'unknown' {
  if (leg.scope) return leg.scope;
  const originCity = String(leg.from.city || '').trim().toLowerCase();
  const destinationCity = String(leg.to.city || '').trim().toLowerCase();
  if (!originCity || !destinationCity) return 'unknown';
  return originCity === destinationCity ? 'local' : 'intercity';
}

export function routeHasIntercityLeg(route: MakersRoutePlan): boolean {
  return routeLegs(route).some((leg) => routeLegScope(leg) === 'intercity');
}

export function visibleRouteSections(route: MakersRoutePlan): MakersRouteSection[] {
  return routeSectionSteps(route).map((step) => ({
    ...step.section,
    path: routeSectionPath(step),
  }));
}

export function routeSectionSteps(route: MakersRoutePlan): RouteSectionStep[] {
  return routeLegs(route).flatMap((leg, legIndex) => {
    const sections = leg.sections?.length
      ? leg.sections
      : [fallbackSection(leg.mode, leg.path, leg.distance_meters, leg.duration_seconds)];
    return sections.map((section, sectionIndex) => ({
      leg,
      legIndex,
      section,
      sectionIndex,
    }));
  });
}

/**
 * Older provider snapshots may only contain a leg polyline. In that case,
 * divide it proportionally by the provider section distances so every client
 * can still focus the relevant section without inventing route semantics.
 */
export function routeSectionPath({ leg, section, sectionIndex }: RouteSectionStep) {
  if (section.path.length > 1 || leg.path.length < 2) return section.path;
  const sections = leg.sections?.length ? leg.sections : [section];
  const weights = sections.map((item) => (
    item.distance_meters > 0 ? item.distance_meters
      : item.duration_seconds > 0 ? item.duration_seconds
        : 1
  ));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  const before = weights.slice(0, sectionIndex).reduce((sum, weight) => sum + weight, 0);
  const after = before + (weights[sectionIndex] || 1);
  const lastPoint = leg.path.length - 1;
  const start = Math.max(0, Math.floor((before / total) * lastPoint));
  const end = Math.min(lastPoint, Math.ceil((after / total) * lastPoint));
  return leg.path.slice(start, Math.max(start + 2, end + 1));
}

function projectedDistanceSquared(
  point: RouteMapPoint,
  path: RouteMapPoint[],
): number {
  if (!path.length) return Number.POSITIVE_INFINITY;
  const longitudeScale = Math.cos((point.latitude * Math.PI) / 180);
  const px = point.longitude * longitudeScale;
  const py = point.latitude;
  let closest = Number.POSITIVE_INFINITY;

  for (let index = 0; index < path.length; index += 1) {
    const start = path[index];
    const end = path[index + 1] || start;
    const ax = start.longitude * longitudeScale;
    const ay = start.latitude;
    const bx = end.longitude * longitudeScale;
    const by = end.latitude;
    const dx = bx - ax;
    const dy = by - ay;
    const lengthSquared = (dx * dx) + (dy * dy);
    const projection = lengthSquared
      ? Math.max(0, Math.min(1, (((px - ax) * dx) + ((py - ay) * dy)) / lengthSquared))
      : 0;
    const offsetX = px - (ax + (projection * dx));
    const offsetY = py - (ay + (projection * dy));
    closest = Math.min(closest, (offsetX * offsetX) + (offsetY * offsetY));
  }
  return closest;
}

/**
 * Resolve the route section nearest to the map's visual centre. This keeps the
 * UI driven by provider geometry and works for any city or transport mix.
 */
export function closestRouteSectionIndex(
  route: MakersRoutePlan,
  point: RouteMapPoint,
): number {
  const steps = routeSectionSteps(route);
  let closestIndex = -1;
  let closestDistance = Number.POSITIVE_INFINITY;
  steps.forEach((step, index) => {
    const path = routeSectionPath(step);
    const distance = projectedDistanceSquared(point, path);
    if (distance < closestDistance) {
      closestDistance = distance;
      closestIndex = index;
    }
  });
  return closestIndex;
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

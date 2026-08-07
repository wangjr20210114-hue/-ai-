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

export interface RouteSectionEndpoints {
  from: string;
  to: string;
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
 * Derive a label only from provider-backed stop names around one section.
 * This avoids presenting an unlabelled transfer walk as the entire route leg.
 */
export function routeSectionEndpoints(
  steps: RouteSectionStep[],
  index: number,
): RouteSectionEndpoints | null {
  const current = steps[index];
  if (!current) return null;
  const explicitFrom = String(current.section.geton || '').trim();
  const explicitTo = String(current.section.getoff || '').trim();
  if (explicitFrom && explicitTo) return { from: explicitFrom, to: explicitTo };

  let from = String(current.leg.from.name || '').trim();
  for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
    const previous = steps[cursor];
    if (previous.legIndex !== current.legIndex) break;
    const endpoint = String(
      previous.section.getoff || previous.section.geton || '',
    ).trim();
    if (endpoint) {
      from = endpoint;
      break;
    }
  }

  let to = String(current.leg.to.name || '').trim();
  for (let cursor = index + 1; cursor < steps.length; cursor += 1) {
    const next = steps[cursor];
    if (next.legIndex !== current.legIndex) break;
    const endpoint = String(next.section.geton || next.section.getoff || '').trim();
    if (endpoint) {
      to = endpoint;
      break;
    }
  }
  return from && to && from !== to ? { from, to } : null;
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

function planarMetersSquared(a: RouteMapPoint, b: RouteMapPoint): number {
  const latitude = ((a.latitude + b.latitude) / 2) * (Math.PI / 180);
  const dx = (a.longitude - b.longitude) * 111_320 * Math.cos(latitude);
  const dy = (a.latitude - b.latitude) * 110_540;
  return (dx * dx) + (dy * dy);
}

function segmentDistanceSquaredMeters(
  point: RouteMapPoint,
  start: RouteMapPoint,
  end: RouteMapPoint,
): number {
  const latitude = point.latitude * (Math.PI / 180);
  const scaleX = 111_320 * Math.cos(latitude);
  const scaleY = 110_540;
  const ax = start.longitude * scaleX;
  const ay = start.latitude * scaleY;
  const bx = end.longitude * scaleX;
  const by = end.latitude * scaleY;
  const px = point.longitude * scaleX;
  const py = point.latitude * scaleY;
  const dx = bx - ax;
  const dy = by - ay;
  const length = (dx * dx) + (dy * dy);
  const ratio = length
    ? Math.max(0, Math.min(1, (((px - ax) * dx) + ((py - ay) * dy)) / length))
    : 0;
  const offsetX = px - (ax + (ratio * dx));
  const offsetY = py - (ay + (ratio * dy));
  return (offsetX * offsetX) + (offsetY * offsetY);
}

function simplifyPresentationPath(
  path: RouteMapPoint[],
  toleranceMeters: number,
): RouteMapPoint[] {
  if (path.length < 3) return path;
  const keep = new Set([0, path.length - 1]);
  const toleranceSquared = toleranceMeters * toleranceMeters;
  const pending: Array<[number, number]> = [[0, path.length - 1]];
  while (pending.length) {
    const [startIndex, endIndex] = pending.pop() as [number, number];
    let farthestIndex = -1;
    let farthestDistance = 0;
    for (let index = startIndex + 1; index < endIndex; index += 1) {
      const distance = segmentDistanceSquaredMeters(
        path[index], path[startIndex], path[endIndex],
      );
      if (distance > farthestDistance) {
        farthestDistance = distance;
        farthestIndex = index;
      }
    }
    if (farthestIndex < 0 || farthestDistance <= toleranceSquared) continue;
    keep.add(farthestIndex);
    pending.push([startIndex, farthestIndex], [farthestIndex, endIndex]);
  }
  return [...keep].sort((a, b) => a - b).map((index) => path[index]);
}

function dottedWalkingPaths(path: RouteMapPoint[]): RouteMapPoint[][] {
  const dots: RouteMapPoint[][] = [];
  const totalMeters = path.slice(0, -1).reduce(
    (sum, point, index) => sum + Math.sqrt(planarMetersSquared(point, path[index + 1])),
    0,
  );
  const cycleMeters = Math.max(46, totalMeters / 160);
  const dashMeters = cycleMeters * 0.61;
  const gapMeters = cycleMeters - dashMeters;
  let draw = true;
  let remaining = dashMeters;
  for (let index = 0; index < path.length - 1; index += 1) {
    const start = path[index];
    const end = path[index + 1];
    const distance = Math.sqrt(planarMetersSquared(start, end));
    if (!distance) continue;
    let offset = 0;
    while (offset < distance) {
      const length = Math.min(remaining, distance - offset);
      const fromRatio = offset / distance;
      const toRatio = (offset + length) / distance;
      if (draw && length > 0.5) {
        dots.push([
          {
            latitude: start.latitude + ((end.latitude - start.latitude) * fromRatio),
            longitude: start.longitude + ((end.longitude - start.longitude) * fromRatio),
          },
          {
            latitude: start.latitude + ((end.latitude - start.latitude) * toRatio),
            longitude: start.longitude + ((end.longitude - start.longitude) * toRatio),
          },
        ]);
      }
      offset += length;
      remaining -= length;
      if (remaining <= 0.5) {
        draw = !draw;
        remaining = draw ? dashMeters : gapMeters;
      }
    }
  }
  return dots.length ? dots : [path];
}

/**
 * Return render-only geometry for one provider section. Walking geometry is
 * lightly simplified and split into short round-capped strokes so transfer
 * details stay readable without altering the trusted route or its metrics.
 */
export function routeSectionDisplayPaths(step: RouteSectionStep): RouteMapPoint[][] {
  const path = routeSectionPath(step);
  if (step.section.mode !== 'walking' || path.length < 2) return [path];
  const tolerance = Math.max(
    6,
    Math.min(18, Number(step.section.distance_meters || 0) / 120),
  );
  return dottedWalkingPaths(simplifyPresentationPath(path, tolerance));
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

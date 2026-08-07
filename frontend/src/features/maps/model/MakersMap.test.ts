import { describe, expect, it } from 'vitest';
import { LOCATION_OPTIONS, locationErrorMessage, permissionAfterLocationFailure } from './makersMapLocation';
import { chronologicalSchedulePlaces, shouldPlanMakersRoute, shouldRequestMakersRoute } from './makersMapRouting';
import {
  closestRouteSectionIndex,
  legModeSequence,
  routeHasIntercityLeg,
  routeLegScope,
  routeLegs,
  routeSectionDisplayPaths,
  routeSectionPath,
  routeSectionSteps,
  routeZoomLevel,
} from './routePresentation';
import type { ScheduleItem } from '../../calendar/model';
import type { MakersMapPlace, MakersRoutePlan } from './types';

describe('MakersMap geolocation recovery', () => {
  it('reuses a recent authorized location after a page refresh', () => {
    expect(LOCATION_OPTIONS.enableHighAccuracy).toBe(false);
    expect(LOCATION_OPTIONS.maximumAge).toBeGreaterThanOrEqual(5 * 60_000);
    expect(LOCATION_OPTIONS.timeout).toBeLessThanOrEqual(12_000);
  });

  it('gives a concrete retry instruction for every browser failure', () => {
    expect(locationErrorMessage({ code: 1 } as GeolocationPositionError)).toContain('网站设置');
    expect(locationErrorMessage({ code: 3 } as GeolocationPositionError)).toContain('重试');
    expect(locationErrorMessage({ code: 2 } as GeolocationPositionError)).toContain('重试');
  });

  it('keeps granted permission after a transient timeout or unavailable fix', () => {
    expect(permissionAfterLocationFailure(3, 'granted')).toBe('granted');
    expect(permissionAfterLocationFailure(2, 'granted')).toBe('granted');
    expect(permissionAfterLocationFailure(1, 'granted')).toBe('denied');
    expect(permissionAfterLocationFailure(3, 'prompt')).toBe('prompt');
  });

  it('plans routes only for ordered maps with at least two places', () => {
    expect(shouldPlanMakersRoute(false, 3)).toBe(false);
    expect(shouldPlanMakersRoute(true, 1)).toBe(false);
    expect(shouldPlanMakersRoute(true, 2)).toBe(true);
  });

  it('keeps schedule places in chronological order instead of shortest-path order', () => {
    const place = (name: string): MakersMapPlace => ({
      place_id: name,
      name,
      address: name,
      latitude: 39.9,
      longitude: 116.4,
    });
    const schedule = (name: string, startTime: number): ScheduleItem => ({
      id: name,
      session_id: 'test',
      title: name,
      category: 'travel',
      start_time: startTime,
      duration_minutes: 30,
      duration_days: 0,
      location: name,
      description: '',
      markdown_content: '',
      extra: { place: place(name) },
      done: false,
      created_at: 0,
      updated_at: 0,
    });
    const items = [
      schedule('锦江之星', 300),
      schedule('早餐店', 100),
      schedule('北京站', 200),
    ];

    expect(chronologicalSchedulePlaces(items).map((item) => item.name))
      .toEqual(['早餐店', '北京站', '锦江之星']);
  });

  it('reuses a verified action route instead of requesting the provider again', () => {
    const snapshot = { places: [{ place_id: 'a' }, { place_id: 'b' }] } as MakersRoutePlan;
    expect(shouldRequestMakersRoute(true, 2, snapshot)).toBe(false);
    expect(shouldRequestMakersRoute(true, 2)).toBe(true);
  });

  it('changes route detail naturally with map zoom', () => {
    expect(routeZoomLevel(7)).toBe('overview');
    expect(routeZoomLevel(10)).toBe('legs');
    expect(routeZoomLevel(15)).toBe('sections');
  });

  it('keeps mixed transport modes in the provider order for each leg', () => {
    const place = (name: string): MakersMapPlace => ({
      place_id: name, name, address: name, latitude: 30.2, longitude: 120.1,
    });
    const route: MakersRoutePlan = {
      schema_version: 4,
      provider: 'tencent',
      mode: 'transit',
      places: [place('灵隐寺'), place('西湖')],
      path: [],
      distance_meters: 5000,
      duration_seconds: 1800,
      fare: { currency: 'CNY', basis: '' },
      legs: [{
        from: place('灵隐寺'), to: place('西湖'), mode: 'transit', path: [],
        distance_meters: 5000, duration_seconds: 1800,
        sections: [
          { mode: 'walking', path: [], distance_meters: 300, duration_seconds: 300 },
          { mode: 'bus', line: '278路', path: [], distance_meters: 4200, duration_seconds: 1200 },
          { mode: 'walking', path: [], distance_meters: 500, duration_seconds: 300 },
        ],
      }],
    };
    expect(routeLegs(route)).toHaveLength(1);
    expect(legModeSequence(routeLegs(route)[0])).toEqual(['walking', 'bus', 'walking']);
  });

  it('classifies route scope from provider cities without city-specific rules', () => {
    const place = (name: string, city: string): MakersMapPlace => ({
      place_id: name, name, city, address: name, latitude: 30.2, longitude: 120.1,
    });
    const leg = {
      from: place('A', 'City One'), to: place('B', 'City Two'), mode: 'transit' as const,
      path: [], sections: [], distance_meters: 10, duration_seconds: 10,
    };
    const route = {
      schema_version: 4, provider: 'tencent', mode: 'transit' as const,
      places: [leg.from, leg.to], path: [], legs: [leg], distance_meters: 10,
      duration_seconds: 10, fare: { currency: 'CNY', basis: '' },
    };
    expect(routeLegScope(leg)).toBe('intercity');
    expect(routeHasIntercityLeg(route)).toBe(true);
  });

  it('follows the map attention point through mixed provider route sections', () => {
    const place = (name: string, latitude: number, longitude: number): MakersMapPlace => ({
      place_id: name, name, address: name, latitude, longitude,
    });
    const origin = place('Origin', 31.2, 121.4);
    const destination = place('Destination', 30.3, 120.2);
    const route: MakersRoutePlan = {
      schema_version: 4,
      provider: 'tencent',
      mode: 'transit',
      places: [origin, destination],
      path: [origin, destination],
      distance_meters: 180000,
      duration_seconds: 7200,
      fare: { currency: 'CNY', basis: '' },
      legs: [{
        from: origin,
        to: destination,
        mode: 'transit',
        path: [origin, destination],
        distance_meters: 180000,
        duration_seconds: 7200,
        sections: [
          {
            mode: 'bus', line: 'Local A', distance_meters: 8000, duration_seconds: 1200,
            path: [{ latitude: 31.2, longitude: 121.4 }, { latitude: 31.1, longitude: 121.3 }],
          },
          {
            mode: 'rail', line: 'Rail B', distance_meters: 172000, duration_seconds: 6000,
            path: [{ latitude: 31.1, longitude: 121.3 }, { latitude: 30.3, longitude: 120.2 }],
          },
        ],
      }],
    };

    expect(routeSectionSteps(route).map(({ section }) => section.line)).toEqual(['Local A', 'Rail B']);
    expect(closestRouteSectionIndex(route, { latitude: 31.19, longitude: 121.39 })).toBe(0);
    expect(closestRouteSectionIndex(route, { latitude: 30.5, longitude: 120.4 })).toBe(1);

    const leg = route.legs?.[0];
    if (!leg) throw new Error('fixture leg missing');
    leg.path = [
      { latitude: 31.2, longitude: 121.4 },
      { latitude: 31.1, longitude: 121.3 },
      { latitude: 30.3, longitude: 120.2 },
    ];
    leg.sections.forEach((section) => {
      section.path = [];
      section.distance_meters = 90000;
    });
    const fallbackSteps = routeSectionSteps(route);
    expect(routeSectionPath(fallbackSteps[0])).toHaveLength(2);
    expect(routeSectionPath(fallbackSteps[1])).toHaveLength(2);
    expect(closestRouteSectionIndex(route, { latitude: 30.4, longitude: 120.3 })).toBe(1);
  });

  it('renders walking detail as bounded dotted presentation geometry', () => {
    const origin: MakersMapPlace = {
      place_id: 'origin', name: 'Origin', address: 'Origin', latitude: 39.9, longitude: 116.3,
    };
    const destination: MakersMapPlace = {
      place_id: 'destination', name: 'Destination', address: 'Destination', latitude: 39.901, longitude: 116.304,
    };
    const route: MakersRoutePlan = {
      schema_version: 4,
      provider: 'tencent',
      mode: 'walking',
      places: [origin, destination],
      path: [origin, destination],
      distance_meters: 420,
      duration_seconds: 360,
      fare: { currency: 'CNY', basis: '' },
      legs: [{
        from: origin,
        to: destination,
        mode: 'walking',
        path: [
          origin,
          { latitude: 39.90002, longitude: 116.30002 },
          { latitude: 39.90001, longitude: 116.30001 },
          { latitude: 39.9005, longitude: 116.302 },
          destination,
        ],
        distance_meters: 420,
        duration_seconds: 360,
        sections: [{
          mode: 'walking',
          path: [
            origin,
            { latitude: 39.90002, longitude: 116.30002 },
            { latitude: 39.90001, longitude: 116.30001 },
            { latitude: 39.9005, longitude: 116.302 },
            destination,
          ],
          distance_meters: 420,
          duration_seconds: 360,
        }],
      }],
    };

    const paths = routeSectionDisplayPaths(routeSectionSteps(route)[0]);
    expect(paths.length).toBeGreaterThan(2);
    expect(paths.length).toBeLessThanOrEqual(161);
    expect(paths.every((path) => path.length === 2)).toBe(true);
  });
});

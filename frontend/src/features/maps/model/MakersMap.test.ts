import { describe, expect, it } from 'vitest';
import { LOCATION_OPTIONS, locationErrorMessage, permissionAfterLocationFailure } from './makersMapLocation';
import { chronologicalSchedulePlaces, shouldPlanMakersRoute } from './makersMapRouting';
import { legModeSequence, routeLegs, routeZoomLevel } from './routePresentation';
import type { MakersMapPlace, MakersRoutePlan, ScheduleItem } from '../../../shared/types';

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
});

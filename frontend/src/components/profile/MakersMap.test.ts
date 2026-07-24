import { describe, expect, it } from 'vitest';
import { LOCATION_OPTIONS, locationErrorMessage, permissionAfterLocationFailure } from './makersMapLocation';
import { chronologicalSchedulePlaces, shouldPlanMakersRoute } from './makersMapRouting';
import type { MakersMapPlace, ScheduleItem } from '../../types';

describe('MakersMap geolocation recovery', () => {
  it('reuses a recent authorized location after a page refresh', () => {
    expect(LOCATION_OPTIONS.enableHighAccuracy).toBe(false);
    expect(LOCATION_OPTIONS.maximumAge).toBeGreaterThanOrEqual(5 * 60_000);
    expect(LOCATION_OPTIONS.timeout).toBeLessThanOrEqual(8_000);
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
});

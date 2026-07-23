import { describe, expect, it } from 'vitest';
import { LOCATION_OPTIONS, locationErrorMessage, permissionAfterLocationFailure } from './makersMapLocation';
import { shouldPlanMakersRoute } from './makersMapRouting';

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
});

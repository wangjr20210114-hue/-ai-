import { describe, expect, it } from 'vitest';
import {
  clearBrowserLocation,
  currentBrowserLocation,
  publishBrowserLocation,
} from './browserLocation';

describe('ephemeral browser location', () => {
  it('publishes a fresh WGS84 fix for one chat request and expires it', () => {
    clearBrowserLocation();
    const place = publishBrowserLocation({
      timestamp: 1_000,
      coords: {
        latitude: 43.82,
        longitude: 125.32,
        accuracy: 20,
      } as GeolocationCoordinates,
    });
    expect(place.provider).toBe('browser-wgs84');
    expect(currentBrowserLocation(2_000)).toMatchObject({
      latitude: 43.82,
      longitude: 125.32,
      coordinate_type: 'wgs84',
    });
    expect(currentBrowserLocation(10 * 60 * 1000 + 1_001)).toBeNull();
  });
});

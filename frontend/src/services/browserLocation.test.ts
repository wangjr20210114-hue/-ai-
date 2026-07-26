import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  browserLocationRequestContext,
  clearBrowserLocation,
  currentBrowserLocation,
  publishBrowserLocation,
  requestBrowserLocationForChat,
} from './browserLocation';

describe('ephemeral browser location', () => {
  afterEach(() => {
    clearBrowserLocation();
    vi.restoreAllMocks();
  });

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

  it('requests permission and publishes an allowed position before chat', async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => success({
      timestamp: Date.now(),
      coords: {
        latitude: 39.9042,
        longitude: 116.4074,
        accuracy: 15,
      } as GeolocationCoordinates,
    } as GeolocationPosition));
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });

    await expect(requestBrowserLocationForChat()).resolves.toBe('available');
    expect(getCurrentPosition).toHaveBeenCalledOnce();
    expect(currentBrowserLocation()).toMatchObject({
      latitude: 39.9042,
      longitude: 116.4074,
    });
  });

  it('reports denied permission without inventing a position', async () => {
    const getCurrentPosition = vi.fn((_success: PositionCallback, failure: PositionErrorCallback) => failure({
      code: 1,
      message: 'denied',
    } as GeolocationPositionError));
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });

    await expect(requestBrowserLocationForChat()).resolves.toBe('denied');
    expect(currentBrowserLocation()).toBeNull();
    expect(browserLocationRequestContext().state).toBe('denied');
  });

  it('reports a location timeout so the backend can fall back to a card', async () => {
    const getCurrentPosition = vi.fn((_success: PositionCallback, failure: PositionErrorCallback) => failure({
      code: 3,
      message: 'timeout',
    } as GeolocationPositionError));
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: { getCurrentPosition },
    });

    await expect(requestBrowserLocationForChat()).resolves.toBe('timed_out');
    expect(currentBrowserLocation()).toBeNull();
    expect(browserLocationRequestContext().state).toBe('timed_out');
  });
});

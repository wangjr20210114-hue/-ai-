import type { MakersMapPlace } from '../types';
import { translate } from '../i18n';

export interface BrowserLocationContext {
  latitude: number;
  longitude: number;
  accuracy_meters: number;
  captured_at: number;
  coordinate_type: 'wgs84';
}

const MAX_LOCATION_AGE_MS = 10 * 60 * 1000;
let latestLocation: BrowserLocationContext | null = null;

export function publishBrowserLocation(
  position: Pick<GeolocationPosition, 'coords' | 'timestamp'>,
): MakersMapPlace {
  latestLocation = {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy_meters: Math.max(0, Number(position.coords.accuracy || 0)),
    captured_at: Number(position.timestamp || Date.now()),
    coordinate_type: 'wgs84',
  };
  return {
    place_id: 'browser-current-location',
    provider: 'browser-wgs84',
    name: translate('currentLocation'),
    address: translate('sessionOnlyLocation'),
    latitude: latestLocation.latitude,
    longitude: latestLocation.longitude,
  };
}

export function currentBrowserLocation(now = Date.now()): BrowserLocationContext | null {
  if (!latestLocation) return null;
  if (now - latestLocation.captured_at > MAX_LOCATION_AGE_MS) {
    latestLocation = null;
    return null;
  }
  return { ...latestLocation };
}

export function clearBrowserLocation(): void {
  latestLocation = null;
}

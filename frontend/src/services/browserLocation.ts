import type { MakersMapPlace } from '../types';
import { translate } from '../i18n';

export interface BrowserLocationContext {
  latitude: number;
  longitude: number;
  accuracy_meters: number;
  captured_at: number;
  coordinate_type: 'wgs84';
}

export interface BrowserLocationRequestContext {
  state: BrowserLocationRequestResult | 'idle';
  attempted_at: number;
}

const MAX_LOCATION_AGE_MS = 10 * 60 * 1000;
const CHAT_LOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 12_000,
  maximumAge: 5 * 60 * 1000,
};
let latestLocation: BrowserLocationContext | null = null;
let latestRequest: BrowserLocationRequestContext = {
  state: 'idle',
  attempted_at: 0,
};
let activeRequest: Promise<BrowserLocationRequestResult> | null = null;

export const BROWSER_LOCATION_EVENT = 'floris:browser-location-changed';

export type BrowserLocationRequestResult =
  | 'available'
  | 'denied'
  | 'timed_out'
  | 'unavailable'
  | 'failed';

function broadcastBrowserLocation(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(BROWSER_LOCATION_EVENT, {
    detail: {
      location: currentBrowserLocation(),
      request: browserLocationRequestContext(),
    },
  }));
}

export async function requestBrowserLocationForChat(): Promise<BrowserLocationRequestResult> {
  if (currentBrowserLocation()) {
    latestRequest = { state: 'available', attempted_at: Date.now() };
    return 'available';
  }
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    latestRequest = { state: 'unavailable', attempted_at: Date.now() };
    broadcastBrowserLocation();
    return 'unavailable';
  }
  if (activeRequest) return activeRequest;
  latestRequest = { state: 'idle', attempted_at: Date.now() };
  const request = new Promise<BrowserLocationRequestResult>((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        publishBrowserLocation(position);
        latestRequest = { state: 'available', attempted_at: Date.now() };
        broadcastBrowserLocation();
        resolve('available');
      },
      (error) => {
        const state: BrowserLocationRequestResult = error.code === 1
          ? 'denied'
          : error.code === 3
            ? 'timed_out'
            : error.code === 2
              ? 'unavailable'
              : 'failed';
        // A permission denial invalidates the displayed fix. A transient GPS
        // timeout does not erase a still-visible point; its original timestamp
        // remains authoritative and the backend will reject it once stale.
        if (state === 'denied') latestLocation = null;
        latestRequest = { state, attempted_at: Date.now() };
        broadcastBrowserLocation();
        resolve(state);
      },
      CHAT_LOCATION_OPTIONS,
    );
  }).finally(() => {
    activeRequest = null;
  });
  activeRequest = request;
  return request;
}

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
  latestRequest = { state: 'available', attempted_at: Date.now() };
  broadcastBrowserLocation();
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
    return null;
  }
  return { ...latestLocation };
}

export function browserLocationRequestContext(): BrowserLocationRequestContext {
  return { ...latestRequest };
}

export function clearBrowserLocation(
  state: BrowserLocationRequestContext['state'] = 'idle',
): void {
  latestLocation = null;
  latestRequest = { state, attempted_at: state === 'idle' ? 0 : Date.now() };
  broadcastBrowserLocation();
}

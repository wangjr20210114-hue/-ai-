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
const CHAT_LOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 8_000,
  maximumAge: 5 * 60 * 1000,
};
let latestLocation: BrowserLocationContext | null = null;

export type BrowserLocationRequestResult =
  | 'available'
  | 'denied'
  | 'timed_out'
  | 'unavailable'
  | 'failed';

function normalizedMessage(value: string): string {
  return String(value || '').toLowerCase().replace(/\s+/g, '');
}

/**
 * Only request the privacy-sensitive browser permission for unmistakably
 * location-grounded turns. The backend semantic planner remains authoritative;
 * this guard merely ensures the native permission prompt is opened while the
 * user's send gesture is still active.
 */
export function messageNeedsBrowserLocation(value: string): boolean {
  const text = normalizedMessage(value);
  if (!text) return false;
  if (/^(?:请)?(?:告诉我)?我(?:现在|当前)?(?:具体)?在哪(?:里|儿)?[？?。！!]*$/.test(text)) return true;
  if (/^(?:请)?(?:告诉我)?(?:我的)?当前位置(?:是|在哪(?:里|儿)?)?[？?。！!]*$/.test(text)) return true;
  if (/(?:我|这|当前位置|当前地点)(?:这边|这里|这儿)?(?:附近|周边)/.test(text)) return true;
  if (/^(?:这|我这|这里|这儿)?附近(?:有|哪|找|推荐|什么)/.test(text)) return true;
  if (/(?:我想去|我要去|带我去|怎么去|如何去|导航到|导航去).+/.test(text)) return true;
  return false;
}

export async function requestBrowserLocationForChat(): Promise<BrowserLocationRequestResult> {
  if (currentBrowserLocation()) return 'available';
  if (typeof navigator === 'undefined' || !navigator.geolocation) return 'unavailable';
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (position) => {
        publishBrowserLocation(position);
        resolve('available');
      },
      (error) => {
        clearBrowserLocation();
        if (error.code === 1) resolve('denied');
        else if (error.code === 3) resolve('timed_out');
        else resolve('failed');
      },
      CHAT_LOCATION_OPTIONS,
    );
  });
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

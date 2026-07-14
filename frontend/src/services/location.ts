export interface UserLocation {
  lat: number;
  lng: number;
  accuracy: number;
  capturedAt: number;
}

export type LocationConsent = 'unknown' | 'granted' | 'denied';

const CONSENT_KEY = 'yuanbao.locationConsent';
const SESSION_LOCATION_KEY = 'yuanbao.currentLocation';
export const LOCATION_EVENT = 'yuanbao:location-changed';

export function readLocationConsent(): LocationConsent {
  try {
    const value = localStorage.getItem(CONSENT_KEY);
    return value === 'granted' || value === 'denied' ? value : 'unknown';
  } catch {
    return 'unknown';
  }
}

export function setLocationConsent(value: Exclude<LocationConsent, 'unknown'>): void {
  try {
    localStorage.setItem(CONSENT_KEY, value);
  } catch { /* browser storage can be unavailable */ }
  window.dispatchEvent(new CustomEvent(LOCATION_EVENT));
}

export function readSessionLocation(): UserLocation | null {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(SESSION_LOCATION_KEY) || 'null') as UserLocation | null;
    if (!parsed || !Number.isFinite(parsed.lat) || !Number.isFinite(parsed.lng)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function requestCurrentLocation(): Promise<UserLocation> {
  if (!navigator.geolocation) throw new Error('当前浏览器不支持定位');
  const position = await new Promise<GeolocationPosition>((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 12000,
      maximumAge: 5 * 60 * 1000,
    });
  });
  const value: UserLocation = {
    lat: position.coords.latitude,
    lng: position.coords.longitude,
    accuracy: position.coords.accuracy,
    capturedAt: Date.now(),
  };
  setLocationConsent('granted');
  try {
    sessionStorage.setItem(SESSION_LOCATION_KEY, JSON.stringify(value));
  } catch { /* keep the in-memory event path */ }
  window.dispatchEvent(new CustomEvent(LOCATION_EVENT, { detail: value }));
  return value;
}

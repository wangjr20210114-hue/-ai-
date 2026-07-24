const LOCATION_CACHE_MS = 5 * 60_000;

export const LOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 8_000,
  maximumAge: LOCATION_CACHE_MS,
};

export function locationErrorMessage(error: GeolocationPositionError): string {
  if (error.code === 1) return translate('locationPermissionHelp');
  if (error.code === 3) return translate('locationTimedOut');
  return translate('locationFailed');
}

export function permissionAfterLocationFailure(
  errorCode: number,
  browserPermission?: PermissionState,
): 'prompt' | 'granted' | 'denied' {
  if (errorCode === 1 || browserPermission === 'denied') return 'denied';
  return browserPermission === 'granted' ? 'granted' : 'prompt';
}
import { translate } from '../../i18n';

const LOCATION_CACHE_MS = 5 * 60_000;

export const LOCATION_OPTIONS: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 8_000,
  maximumAge: LOCATION_CACHE_MS,
};

export function locationErrorMessage(error: GeolocationPositionError): string {
  if (error.code === 1) return '位置权限未开启。请在地址栏左侧的网站设置中允许位置，然后重试。';
  if (error.code === 3) return '定位暂时超时，请确认系统定位服务已开启后重试。';
  return '暂时无法取得位置，请确认网络和系统定位服务后重试。';
}

export function permissionAfterLocationFailure(
  errorCode: number,
  browserPermission?: PermissionState,
): 'prompt' | 'granted' | 'denied' {
  if (errorCode === 1 || browserPermission === 'denied') return 'denied';
  return browserPermission === 'granted' ? 'granted' : 'prompt';
}

const CLOUDBASE_NETWORK_ERROR = /failed to fetch|network(?:error| request failed)|load failed/i;

export const CLOUDBASE_NETWORK_UNAVAILABLE = 'cloudbase_network_unavailable';

export function normalizeAuthError(reason: unknown): string {
  const message = String((reason as Error)?.message || reason || '').trim();
  if (CLOUDBASE_NETWORK_ERROR.test(message)) {
    return CLOUDBASE_NETWORK_UNAVAILABLE;
  }
  return message || 'CloudBase authentication failed';
}

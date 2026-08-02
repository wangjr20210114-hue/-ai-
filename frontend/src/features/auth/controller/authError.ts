const CLOUDBASE_NETWORK_ERROR = /failed to fetch|network(?:error| request failed)|load failed/i;
const TECHNICAL_AUTH_ERROR = /cloudbase|access token|otp verifier|authorization url|floris could not verify|jwt|session exchange/i;

export const CLOUDBASE_NETWORK_UNAVAILABLE = 'cloudbase_network_unavailable';
export const AUTH_UNKNOWN_ERROR = 'auth_unknown_error';

export function normalizeAuthError(reason: unknown): string {
  const message = String((reason as Error)?.message || reason || '').trim();
  if (CLOUDBASE_NETWORK_ERROR.test(message)) {
    return CLOUDBASE_NETWORK_UNAVAILABLE;
  }
  if (TECHNICAL_AUTH_ERROR.test(message)) return AUTH_UNKNOWN_ERROR;
  return message || AUTH_UNKNOWN_ERROR;
}

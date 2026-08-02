import { describe, expect, it } from 'vitest';

import {
  CLOUDBASE_NETWORK_UNAVAILABLE,
  normalizeAuthError,
} from './authError';

describe('CloudBase authentication errors', () => {
  it.each([
    new TypeError('Failed to fetch'),
    new Error('NetworkError when attempting to fetch resource.'),
    new Error('Load failed'),
  ])('maps browser network failures to an actionable UI key', (reason) => {
    expect(normalizeAuthError(reason)).toBe(CLOUDBASE_NETWORK_UNAVAILABLE);
  });

  it('preserves a useful provider error', () => {
    expect(normalizeAuthError(new Error('Email login is disabled')))
      .toBe('Email login is disabled');
  });

  it('never exposes authentication infrastructure details to users', () => {
    expect(normalizeAuthError(new Error('CloudBase did not return an access token')))
      .toBe('auth_unknown_error');
  });
});

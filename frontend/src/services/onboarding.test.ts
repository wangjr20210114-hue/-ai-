import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ONBOARDING_STORAGE_KEY,
  completeOnboarding,
  disableOnboarding,
  enableOnboarding,
  readOnboardingPreference,
  shouldOpenOnboarding,
} from './onboarding';

describe('onboarding preference', () => {
  beforeEach(() => {
    const values = new Map<string, string>();
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
      clear: () => values.clear(),
    });
  });

  it('opens for a first-time visitor', () => {
    expect(readOnboardingPreference()).toEqual({ enabled: true, completedVersion: 0 });
    expect(shouldOpenOnboarding()).toBe(true);
  });

  it('keeps a completed tour available without reopening automatically', () => {
    completeOnboarding();
    expect(readOnboardingPreference().enabled).toBe(true);
    expect(shouldOpenOnboarding()).toBe(false);
  });

  it('distinguishes dismissing from completing and can be re-enabled', () => {
    disableOnboarding();
    expect(readOnboardingPreference().enabled).toBe(false);
    expect(shouldOpenOnboarding()).toBe(false);

    enableOnboarding();
    expect(localStorage.getItem(ONBOARDING_STORAGE_KEY)).toBeTruthy();
    expect(shouldOpenOnboarding()).toBe(true);
  });
});

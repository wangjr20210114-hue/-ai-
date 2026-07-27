export const ONBOARDING_VERSION = 1;
export const ONBOARDING_STORAGE_KEY = 'floris-onboarding-preference';
export const OPEN_ONBOARDING_EVENT = 'floris:open-onboarding';

export interface OnboardingPreference {
  enabled: boolean;
  completedVersion: number;
}

const DEFAULT_PREFERENCE: OnboardingPreference = {
  enabled: true,
  completedVersion: 0,
};

export function readOnboardingPreference(): OnboardingPreference {
  try {
    const stored = JSON.parse(localStorage.getItem(ONBOARDING_STORAGE_KEY) || 'null') as Partial<OnboardingPreference> | null;
    if (!stored || typeof stored !== 'object') return DEFAULT_PREFERENCE;
    return {
      enabled: stored.enabled !== false,
      completedVersion: Number.isFinite(stored.completedVersion)
        ? Math.max(0, Number(stored.completedVersion))
        : 0,
    };
  } catch {
    return DEFAULT_PREFERENCE;
  }
}

export function writeOnboardingPreference(preference: OnboardingPreference): void {
  try {
    localStorage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(preference));
  } catch {
    // The tour still works when browser storage is unavailable.
  }
}

export function shouldOpenOnboarding(preference = readOnboardingPreference()): boolean {
  return preference.enabled && preference.completedVersion < ONBOARDING_VERSION;
}

export function enableOnboarding(): void {
  writeOnboardingPreference({ enabled: true, completedVersion: 0 });
}

export function disableOnboarding(): void {
  writeOnboardingPreference({ enabled: false, completedVersion: ONBOARDING_VERSION });
}

export function completeOnboarding(): void {
  writeOnboardingPreference({ enabled: true, completedVersion: ONBOARDING_VERSION });
}

export function requestOnboarding(startImmediately = false): void {
  window.dispatchEvent(new CustomEvent(OPEN_ONBOARDING_EVENT, {
    detail: { startImmediately },
  }));
}

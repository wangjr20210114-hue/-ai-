import { useCallback, useEffect, useRef, useState } from 'react';

import {
  currentAuthSession,
  ensureAuthSession,
  OPEN_AUTH_DIALOG_EVENT,
  type AuthSession,
} from '../../../shared/auth/session';
import {
  cloudBaseConfigured,
  sendEmailOtp,
  signOutEverywhere,
  startGithubLogin,
  verifyEmailOtp,
} from '../model/cloudbaseClient';
import { normalizeAuthError } from './authError';
import { updateAccountProfile } from '../model/profileClient';
import {
  disableOnboarding,
  enableOnboarding,
  readOnboardingPreference,
  requestOnboarding,
} from '../../../services/onboarding';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const OTP_COOLDOWN_SECONDS = 60;

export function useAuthController() {
  const [visible, setVisible] = useState(false);
  const [closing, setClosing] = useState(false);
  const closeTimer = useRef<number | null>(null);
  const [session, setSession] = useState<AuthSession | null>(currentAuthSession());
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [displayName, setDisplayName] = useState(session?.identity.display_name || '');
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState('');
  const [onboardingEnabled, setOnboardingEnabled] = useState(
    () => readOnboardingPreference().enabled,
  );
  const [busy, setBusy] = useState<'email' | 'verify' | 'github' | 'profile' | 'logout' | ''>('');
  const [error, setError] = useState('');

  const clearCloseTimer = useCallback(() => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);

  const open = useCallback(() => {
    clearCloseTimer();
    setClosing(false);
    setVisible(true);
    setError('');
    void ensureAuthSession().then(setSession).catch(() => undefined);
  }, [clearCloseTimer]);

  const setDialogVisible = useCallback((next: boolean) => {
    clearCloseTimer();
    if (next) {
      setClosing(false);
      setVisible(true);
      return;
    }
    setClosing(true);
    closeTimer.current = window.setTimeout(() => {
      setVisible(false);
      setClosing(false);
      closeTimer.current = null;
    }, 180);
  }, [clearCloseTimer]);

  useEffect(() => {
    window.addEventListener(OPEN_AUTH_DIALOG_EVENT, open);
    const changed = (event: Event) => {
      setSession((event as CustomEvent<AuthSession>).detail);
    };
    window.addEventListener('floris:auth-changed', changed);
    return () => {
      window.removeEventListener(OPEN_AUTH_DIALOG_EVENT, open);
      window.removeEventListener('floris:auth-changed', changed);
    };
  }, [open]);

  useEffect(() => {
    setDisplayName(session?.identity.display_name || '');
  }, [session?.identity.display_name]);

  useEffect(() => {
    if (!avatarFile) {
      setAvatarPreview('');
      return undefined;
    }
    const url = URL.createObjectURL(avatarFile);
    setAvatarPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [avatarFile]);

  useEffect(() => clearCloseTimer, [clearCloseTimer]);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const timer = window.setInterval(() => {
      setCooldown((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [cooldown]);

  const sendCode = async () => {
    const normalized = email.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(normalized)) {
      setError('invalid_email');
      return;
    }
    setBusy('email');
    setError('');
    try {
      await sendEmailOtp(normalized);
      setEmail(normalized);
      setCodeSent(true);
      setCooldown(OTP_COOLDOWN_SECONDS);
    } catch (reason) {
      setError(normalizeAuthError(reason));
    } finally {
      setBusy('');
    }
  };

  const verifyCode = async () => {
    if (!/^\d{4,8}$/.test(code.trim())) {
      setError('invalid_code');
      return;
    }
    setBusy('verify');
    setError('');
    try {
      const next = await verifyEmailOtp(code.trim());
      setSession(next);
      setDialogVisible(false);
    } catch (reason) {
      setError(normalizeAuthError(reason));
    } finally {
      setBusy('');
    }
  };

  const github = async () => {
    setBusy('github');
    setError('');
    try {
      await startGithubLogin();
    } catch (reason) {
      setError(normalizeAuthError(reason));
      setBusy('');
    }
  };

  const logout = async () => {
    setBusy('logout');
    setError('');
    try {
      const next = await signOutEverywhere();
      setSession(next);
      setCode('');
      setCodeSent(false);
      setDialogVisible(false);
    } catch (reason) {
      setError(normalizeAuthError(reason));
    } finally {
      setBusy('');
    }
  };

  const saveProfile = async () => {
    const name = displayName.trim();
    if (!name) {
      setError('display_name_required');
      return;
    }
    setBusy('profile');
    setError('');
    try {
      const next = await updateAccountProfile(name, avatarFile);
      setSession(next);
      setAvatarFile(null);
    } catch (reason) {
      setError(normalizeAuthError(reason));
    } finally {
      setBusy('');
    }
  };

  const toggleOnboarding = (enabled: boolean) => {
    setOnboardingEnabled(enabled);
    if (enabled) enableOnboarding();
    else disableOnboarding();
  };

  const replayOnboarding = () => {
    enableOnboarding();
    setOnboardingEnabled(true);
    setDialogVisible(false);
    window.setTimeout(() => requestOnboarding(true), 220);
  };

  return {
    avatarFile,
    avatarPreview,
    busy,
    cloudBaseConfigured,
    closing,
    code,
    codeSent,
    cooldown,
    displayName,
    email,
    error,
    github,
    logout,
    onboardingEnabled,
    replayOnboarding,
    saveProfile,
    sendCode,
    session,
    setAvatarFile,
    setCode,
    setDisplayName,
    setEmail,
    setVisible: setDialogVisible,
    toggleOnboarding,
    verifyCode,
    visible,
  };
}

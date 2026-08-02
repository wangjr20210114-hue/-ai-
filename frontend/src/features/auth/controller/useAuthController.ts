import { useCallback, useEffect, useRef, useState } from 'react';

import {
  currentAuthSession,
  ensureAuthSession,
  logoutSession,
  OPEN_AUTH_DIALOG_EVENT,
  type AuthSession,
} from '../../../shared/auth/session';
import {
  cloudBaseConfigured,
  hasRestorableCloudBaseSession,
  restoreCloudBaseSession,
  sendEmailOtp,
  signOutEverywhere,
  startGithubLogin,
  verifyEmailOtp,
} from '../model/cloudbaseClient';
import { normalizeAuthError } from './authError';
import { updateAccountProfile } from '../model/profileClient';
import {
  forgetRecentAccount,
  readRecentAccount,
  rememberRecentAccount,
  type RecentAccount,
} from '../model/recentAccount';
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
  const [accountManagerOpen, setAccountManagerOpen] = useState(false);
  const [resumeAvailable, setResumeAvailable] = useState(false);
  const [recentAccount, setRecentAccount] = useState<RecentAccount | null>(readRecentAccount);
  const [displayName, setDisplayName] = useState(session?.identity.display_name || '');
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarPreview, setAvatarPreview] = useState('');
  const [onboardingEnabled, setOnboardingEnabled] = useState(
    () => readOnboardingPreference().enabled,
  );
  const [busy, setBusy] = useState<'resume' | 'email' | 'verify' | 'github' | 'profile' | 'switch' | 'logout' | ''>('');
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
    const savedAccount = readRecentAccount();
    setRecentAccount(savedAccount);
    setAccountManagerOpen(false);
    void ensureAuthSession().then((next) => {
      setSession(next);
      if (next.identity.auth_type !== 'guest') {
        setResumeAvailable(true);
        return;
      }
      void hasRestorableCloudBaseSession()
        .then((available) => {
          setResumeAvailable(available);
          setAccountManagerOpen(available);
        })
        .catch(() => setResumeAvailable(false));
    }).catch(() => undefined);
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
    if (session?.identity.auth_type && session.identity.auth_type !== 'guest') {
      setRecentAccount(rememberRecentAccount(session.identity));
    }
  }, [session?.identity]);

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

  const resumeAccount = async () => {
    setBusy('resume');
    setError('');
    try {
      const next = await restoreCloudBaseSession();
      if (!next) {
        setResumeAvailable(false);
        setError('no_saved_session');
        return;
      }
      setSession(next);
      setRecentAccount(rememberRecentAccount(next.identity));
      setDialogVisible(false);
    } catch (reason) {
      setResumeAvailable(false);
      setError(normalizeAuthError(reason));
    } finally {
      setBusy('');
    }
  };

  const switchAccount = async () => {
    setBusy('switch');
    setError('');
    try {
      const next = await signOutEverywhere();
      forgetRecentAccount();
      setSession(next);
      setRecentAccount(null);
      setResumeAvailable(false);
      setCode('');
      setCodeSent(false);
    } catch (reason) {
      setError(normalizeAuthError(reason));
    } finally {
      setBusy('');
    }
  };

  const logout = async () => {
    setBusy('logout');
    setError('');
    try {
      if (session?.identity.auth_type && session.identity.auth_type !== 'guest') {
        setRecentAccount(rememberRecentAccount(session.identity));
      }
      const next = await logoutSession();
      setSession(next);
      setResumeAvailable(true);
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
    accountManagerOpen,
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
    recentAccount,
    resumeAccount,
    resumeAvailable,
    saveProfile,
    sendCode,
    session,
    setAvatarFile,
    setAccountManagerOpen,
    setCode,
    setDisplayName,
    setEmail,
    setVisible: setDialogVisible,
    switchAccount,
    toggleOnboarding,
    verifyCode,
    visible,
  };
}

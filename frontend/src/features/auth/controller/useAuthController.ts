import { useCallback, useEffect, useState } from 'react';

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

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const OTP_COOLDOWN_SECONDS = 60;

export function useAuthController() {
  const [visible, setVisible] = useState(false);
  const [session, setSession] = useState<AuthSession | null>(currentAuthSession());
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const [busy, setBusy] = useState<'email' | 'verify' | 'github' | 'logout' | ''>('');
  const [error, setError] = useState('');

  const open = useCallback(() => {
    setVisible(true);
    setError('');
    void ensureAuthSession().then(setSession).catch(() => undefined);
  }, []);

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
      setError(String((reason as Error)?.message || reason));
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
      setVisible(false);
    } catch (reason) {
      setError(String((reason as Error)?.message || reason));
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
      setError(String((reason as Error)?.message || reason));
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
      setVisible(false);
    } catch (reason) {
      setError(String((reason as Error)?.message || reason));
    } finally {
      setBusy('');
    }
  };

  return {
    busy,
    cloudBaseConfigured,
    code,
    codeSent,
    cooldown,
    email,
    error,
    github,
    logout,
    sendCode,
    session,
    setCode,
    setEmail,
    setVisible,
    verifyCode,
    visible,
  };
}

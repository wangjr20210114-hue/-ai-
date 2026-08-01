import { Button } from 'tdesign-react';
import { LogoGithubIcon } from 'tdesign-icons-react';

import { useLanguage } from '../../../i18n';
import { useAuthController } from '../controller/useAuthController';

export default function AuthDialog() {
  const auth = useAuthController();
  const { t } = useLanguage();
  if (!auth.visible) return null;

  const signedIn = auth.session?.identity.auth_type !== 'guest';
  const error = auth.error === 'invalid_email'
    ? t('authInvalidEmail')
    : auth.error === 'invalid_code'
      ? t('authInvalidCode')
      : auth.error;

  return (
    <div className="auth-overlay" role="presentation" onMouseDown={() => auth.setVisible(false)}>
      <section
        className="auth-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          type="button"
          className="auth-dialog-close"
          aria-label={t('close')}
          onClick={() => auth.setVisible(false)}
        >×</button>
        <div className="auth-dialog-brand" aria-hidden="true">{t('florisAvatarGlyph')}</div>
        <h2 id="auth-dialog-title">{signedIn ? t('authAccountTitle') : t('authTitle')}</h2>
        <p className="auth-dialog-hint">
          {signedIn ? t('authSignedInHint') : t('authGuestHint')}
        </p>

        {signedIn ? (
          <div className="auth-account-card">
            {auth.session?.identity.avatar_url
              ? <img src={auth.session.identity.avatar_url} alt="" referrerPolicy="no-referrer" />
              : <span aria-hidden="true">{t('accountAvatarGlyph')}</span>}
            <div>
              <strong>{auth.session?.identity.display_name}</strong>
              <small>{auth.session?.identity.auth_providers.join(' · ') || 'CloudBase'}</small>
            </div>
            <Button
              variant="outline"
              loading={auth.busy === 'logout'}
              onClick={() => void auth.logout()}
            >{t('authSignOut')}</Button>
          </div>
        ) : <>
          {!auth.cloudBaseConfigured && (
            <div className="auth-error" role="alert">{t('authNotConfigured')}</div>
          )}
          <label className="auth-field">
            <span>{t('authEmail')}</span>
            <input
              type="email"
              autoComplete="email"
              value={auth.email}
              disabled={!auth.cloudBaseConfigured || auth.busy !== ''}
              placeholder={t('authEmailPlaceholder')}
              onChange={(event) => auth.setEmail(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !auth.codeSent) void auth.sendCode();
              }}
            />
          </label>
          {auth.codeSent && (
            <label className="auth-field">
              <span>{t('authCode')}</span>
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={8}
                value={auth.code}
                disabled={auth.busy !== ''}
                placeholder={t('authCodePlaceholder')}
                onChange={(event) => auth.setCode(event.target.value.replace(/\D/g, ''))}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') void auth.verifyCode();
                }}
              />
            </label>
          )}
          {error && <div className="auth-error" role="alert">{error}</div>}
          <div className="auth-primary-actions">
            {auth.codeSent && (
              <Button
                block
                theme="primary"
                loading={auth.busy === 'verify'}
                disabled={!auth.cloudBaseConfigured || auth.busy !== ''}
                onClick={() => void auth.verifyCode()}
              >{t('authVerify')}</Button>
            )}
            <Button
              block
              variant={auth.codeSent ? 'outline' : 'base'}
              theme="primary"
              loading={auth.busy === 'email'}
              disabled={!auth.cloudBaseConfigured || auth.busy !== '' || auth.cooldown > 0}
              onClick={() => void auth.sendCode()}
            >{auth.cooldown > 0
                ? t('authResendCountdown', { count: auth.cooldown })
                : auth.codeSent ? t('authResendCode') : t('authSendCode')}</Button>
          </div>

          <div className="auth-divider"><span>{t('authOtherMethods')}</span></div>
          <Button
            block
            variant="outline"
            icon={<LogoGithubIcon />}
            loading={auth.busy === 'github'}
            disabled={!auth.cloudBaseConfigured || auth.busy !== ''}
            onClick={() => void auth.github()}
          >{t('authGithub')}</Button>
          <button type="button" className="auth-guest-continue" onClick={() => auth.setVisible(false)}>
            {t('authContinueGuest')}
          </button>
        </>}
      </section>
    </div>
  );
}

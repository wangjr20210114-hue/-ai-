import { Button } from 'tdesign-react';
import {
  ChatIcon,
  CheckCircleIcon,
  CloseIcon,
  LockOnIcon,
  LogoGithubIcon,
  MailIcon,
} from 'tdesign-icons-react';

import { useLanguage } from '../../../i18n';
import { CLOUDBASE_NETWORK_UNAVAILABLE } from '../controller/authError';
import { useAuthController } from '../controller/useAuthController';

export default function AuthDialog() {
  const auth = useAuthController();
  const { t } = useLanguage();
  if (!auth.visible) return null;

  const signedIn = Boolean(
    auth.session && auth.session.identity.auth_type !== 'guest',
  );
  const error = auth.error === 'invalid_email'
    ? t('authInvalidEmail')
    : auth.error === 'invalid_code'
      ? t('authInvalidCode')
      : auth.error === CLOUDBASE_NETWORK_UNAVAILABLE
        ? t('authNetworkUnavailable')
        : auth.error;

  return (
    <div
      className={`auth-overlay${auth.closing ? ' is-closing' : ''}`}
      role="presentation"
      onMouseDown={() => auth.setVisible(false)}
    >
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
          title={t('close')}
          onClick={() => auth.setVisible(false)}
        ><CloseIcon /></button>

        <aside className="auth-dialog-story" aria-hidden="true">
          <div className="auth-story-orbit"><span /><span /><span /></div>
          <div className="auth-dialog-brand">{t('florisAvatarGlyph')}</div>
          <span className="auth-dialog-eyebrow">{t('authSecureEyebrow')}</span>
          <h2>{signedIn ? t('authAccountTitle') : t('authTitle')}</h2>
          <p>{signedIn ? t('authSignedInHint') : t('authGuestHint')}</p>
          <div className="auth-story-features">
            <span><ChatIcon />{t('authGuestChatReady')}</span>
            <span><LockOnIcon />{t('authCloudBaseProtected')}</span>
          </div>
        </aside>

        <div className="auth-dialog-content">
          <div className="auth-mobile-brand" aria-hidden="true">
            <div className="auth-dialog-brand">{t('florisAvatarGlyph')}</div>
            <span>{t('authBrandWord')}</span>
          </div>
          <header className="auth-content-header">
            <span className="auth-dialog-eyebrow">{signedIn ? t('authAccountEyebrow') : t('authWelcomeEyebrow')}</span>
            <h2 id="auth-dialog-title">{signedIn ? t('authAccountTitle') : t('authEmailLogin')}</h2>
            <p>{signedIn ? t('authSignedInHint') : t('authEmailLoginHint')}</p>
          </header>

          {signedIn ? (
            <div className="auth-account-card">
              {auth.session?.identity.avatar_url
                ? <img src={auth.session.identity.avatar_url} alt="" referrerPolicy="no-referrer" />
                : <span aria-hidden="true">{t('accountAvatarGlyph')}</span>}
              <div>
                <strong>{auth.session?.identity.display_name}</strong>
                <small>{auth.session?.identity.auth_providers.join(' · ') || 'CloudBase'}</small>
              </div>
              <CheckCircleIcon className="auth-account-verified" aria-label={t('authSignedIn')} />
              <Button
                variant="outline"
                loading={auth.busy === 'logout'}
                onClick={() => void auth.logout()}
              >{t('authSignOut')}</Button>
            </div>
          ) : <>
            <div className={`auth-progress ${auth.codeSent ? 'is-code' : ''}`} aria-label={t('authLoginProgress')}>
              <span className="is-active"><b>{t('authStepOne')}</b>{t('authStepEmail')}</span>
              <i />
              <span className={auth.codeSent ? 'is-active' : ''}><b>{t('authStepTwo')}</b>{t('authStepVerify')}</span>
            </div>
            {!auth.cloudBaseConfigured && (
              <div className="auth-error" role="alert">{t('authNotConfigured')}</div>
            )}
            <label className="auth-field">
              <span>{t('authEmail')}</span>
              <div className="auth-input-shell">
                <MailIcon aria-hidden="true" />
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
              </div>
            </label>
            {auth.codeSent && (
              <label className="auth-field auth-code-field">
                <span>{t('authCode')}</span>
                <div className="auth-input-shell">
                  <LockOnIcon aria-hidden="true" />
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
                </div>
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
              className="auth-github-button"
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
        </div>
      </section>
    </div>
  );
}

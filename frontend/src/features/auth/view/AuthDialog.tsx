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
        : auth.error === 'display_name_required'
          ? t('authDisplayNameRequired')
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
            <h2 id="auth-dialog-title">{signedIn ? t('authProfileTitle') : t('authEmailLogin')}</h2>
            <p>{signedIn ? t('authProfileHint') : t('authEmailLoginHint')}</p>
          </header>

          {signedIn ? (
            <div className="auth-profile-panel">
              <div className="auth-account-card">
                <label className="auth-avatar-editor">
                  <img
                    src={auth.avatarPreview || auth.session?.identity.avatar_url || '/default-user-avatar-anime.png'}
                    alt=""
                    referrerPolicy="no-referrer"
                  />
                  <span>{t('authChangeAvatar')}</span>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    disabled={auth.busy !== ''}
                    onChange={(event) => auth.setAvatarFile(event.target.files?.[0] || null)}
                  />
                </label>
                <div>
                  <strong>{auth.session?.identity.display_name}</strong>
                  <small>{auth.session?.identity.auth_providers.join(' · ') || 'CloudBase'}</small>
                </div>
                <CheckCircleIcon className="auth-account-verified" aria-label={t('authSignedIn')} />
              </div>
              <label className="auth-field">
                <span>{t('authDisplayName')}</span>
                <div className="auth-input-shell">
                  <input
                    value={auth.displayName}
                    maxLength={120}
                    disabled={auth.busy !== ''}
                    placeholder={t('authDisplayNamePlaceholder')}
                    onChange={(event) => auth.setDisplayName(event.target.value)}
                  />
                </div>
              </label>
              <small className="auth-avatar-format">{t('authAvatarFormat')}</small>
              <Button
                block
                theme="primary"
                loading={auth.busy === 'profile'}
                disabled={auth.busy !== ''}
                onClick={() => void auth.saveProfile()}
              >{t('authSaveProfile')}</Button>
              <div className="auth-profile-preference">
                <div>
                  <strong>{t('authOnboardingControl')}</strong>
                  <small>{t('authOnboardingControlHint')}</small>
                </div>
                <label className="onboarding-settings-switch">
                  <input
                    type="checkbox"
                    checked={auth.onboardingEnabled}
                    aria-label={t('onboardingEnabled')}
                    onChange={(event) => auth.toggleOnboarding(event.target.checked)}
                  />
                  <span aria-hidden="true" />
                </label>
              </div>
              {auth.onboardingEnabled && <Button
                block
                variant="outline"
                disabled={auth.busy !== ''}
                onClick={auth.replayOnboarding}
              >{t('onboardingReplay')}</Button>}
              {error && <div className="auth-error" role="alert">{error}</div>}
              <button
                type="button"
                className="auth-signout-link"
                disabled={auth.busy !== ''}
                onClick={() => void auth.logout()}
              >{t('authSignOut')}</button>
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

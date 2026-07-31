import { useEffect, useState } from 'react';

import type { ChatMessage } from '../../../../shared/types';
import { progressTranslationKey } from '../../../../shared/ui/progressLabel';
import { useLanguage } from '../../../../i18n';


function ImageCreationProgress({ message }: { message: ChatMessage }) {
  const { t } = useLanguage();
  const reference = message.searchResults?.media?.[0];
  const [step, setStep] = useState(0);
  const steps = reference?.alt
    ? [t('paintingReference', { name: `${reference.alt.slice(0, 28)}${reference.alt.length > 28 ? '…' : ''}` }), t('paintingCartoon'), t('paintingDetail'), t('paintingReveal')]
    : [t('paintingUnderstand'), t('paintingCompose'), t('paintingDetail'), t('paintingReveal')];
  useEffect(() => {
    const timer = window.setInterval(() => setStep((value) => (value + 1) % steps.length), 1800);
    return () => window.clearInterval(timer);
  }, [steps.length]);
  return <div className="image-generation-canvas">
    <div className="image-generation-wash" style={reference?.url ? { backgroundImage: `url(${reference.url})` } : undefined}>
      <div className="image-painting-overlay">
        <span />
        <div className="image-painting-copy" aria-live="polite">
          <strong>{steps[step]}</strong>
          <small>{t('paintingWait')}</small>
        </div>
      </div>
    </div>
  </div>;
}

export function ProgressRenderer({ message }: { message: ChatMessage }) {
  const { t } = useLanguage();
  if (!message.streaming) return null;
  const visibleProgress = (message.progress || [])
    .filter((step) => step.stage !== 'complete')
    .slice(-5);
  const activeProgress = [...visibleProgress].reverse().find(
    (step) => step.status === 'active',
  ) || visibleProgress[visibleProgress.length - 1];
  const searchStatus = typeof message.skill?.data?.statusText === 'string'
    ? message.skill.data.statusText
    : t('understandingRequest');
  const progressStatus = message.content
    ? (message.skill?.intent === 'search'
      ? (message.searchResults?.media_pending
        ? t('writingReviewing')
        : t('organizingVerifiedAnswer'))
      : t('organizingAnswer'))
    : activeProgress
      ? t(progressTranslationKey(activeProgress))
      : searchStatus;

  if (message.skill?.intent === 'image') {
    return <ImageCreationProgress message={message} />;
  }
  return <div className="structured-progress-shell">
    <div className={`search-progress ${message.content ? 'has-content' : ''}`}>
      <div className="image-generating-spinner" />
      <span className="search-progress-status" title={progressStatus}>{progressStatus}</span>
      <span className="image-generating-dots"><span>.</span><span>.</span><span>.</span></span>
    </div>
    {!message.content && visibleProgress.length > 0 && (
      <ol className="structured-progress" aria-label={t('progressSafetyNote')} title={t('progressSafetyNote')}>
        {visibleProgress.map((step) => (
          <li
            key={`${step.stage}:${step.activity}`}
            className={`is-${step.status}`}
          >
            <span aria-hidden="true">
              {step.status === 'completed' ? '✓' : step.status === 'skipped' ? '–' : '•'}
            </span>
            {t(progressTranslationKey(step))}
          </li>
        ))}
      </ol>
    )}
  </div>;
}

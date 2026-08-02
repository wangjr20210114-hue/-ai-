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
  const searchDurationMs = Number(message.searchResults?.timings_ms?.search || 0);
  const sourceCount = message.searchResults?.results?.length || 0;
  const [now, setNow] = useState(() => Date.now());
  const webSearchActive = (message.progress || []).some(
    (step) => step.activity === 'web_search' && step.status === 'active',
  );
  useEffect(() => {
    if (!message.streaming || !webSearchActive || searchDurationMs > 0) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [message.streaming, searchDurationMs, webSearchActive]);
  const searchTiming = searchDurationMs > 0
    ? t('searchCompletedIn', { seconds: (searchDurationMs / 1000).toFixed(1) })
    : webSearchActive
      ? t('searchingForSeconds', { seconds: Math.max(1, Math.round((now - message.ts) / 1000)) })
      : '';

  if (!message.streaming) {
    return searchDurationMs > 0 ? <div className="search-complete-meta">
      {t('searchCompleteMeta', {
        count: sourceCount,
        seconds: (searchDurationMs / 1000).toFixed(1),
      })}
    </div> : null;
  }
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
      {searchTiming && <span className="search-progress-time">{searchTiming}</span>}
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

import type { ChatMessage } from '../../chat/model';
import { useLanguage } from '../../../i18n';
import { useSearchTiming } from '../controller';

export function SearchCompleteMeta({ message }: { message: ChatMessage }) {
  const { t } = useLanguage();
  const timing = useSearchTiming(message);
  if (!message.searchResults || (!timing.searchStartedAt && !timing.providerDurationMs)) {
    return null;
  }
  return <div className="search-complete-meta">
    {t('searchCompleteMeta', {
      count: timing.sourceCount,
      seconds: (timing.durationMs / 1000).toFixed(1),
    })}
  </div>;
}

export function SearchLiveTiming({ message }: { message: ChatMessage }) {
  const { t } = useLanguage();
  const timing = useSearchTiming(message);
  if (timing.searchInProgress) {
    return <>{t('searchingForSeconds', {
      seconds: Math.max(1, Math.round(timing.durationMs / 1000)),
    })}</>;
  }
  if (timing.turnInProgress) {
    return <>{t('workingForSeconds', {
      seconds: Math.max(1, Math.round((timing.now - timing.turnStartedAt) / 1000)),
    })}</>;
  }
  if (timing.searchStartedAt || timing.providerDurationMs) {
    return <>{t('searchCompletedIn', {
      seconds: (timing.durationMs / 1000).toFixed(1),
    })}</>;
  }
  return null;
}

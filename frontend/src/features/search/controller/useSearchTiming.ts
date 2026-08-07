import { useEffect, useState } from 'react';

import type { ChatMessage } from '../../chat/model';
import { citedSearchSourceCount } from '../../../components/common/richContent';

export function useSearchTiming(message: ChatMessage) {
  const [now, setNow] = useState(() => Date.now());
  const providerDurationMs = Number(message.searchResults?.timings_ms?.search || 0);
  const turnStartedAt = Number(message.turnStartedAt || 0);
  const searchStartedAt = Number(message.searchStartedAt || 0);
  const searchCompletedAt = Number(message.searchCompletedAt || 0);
  const durationMs = searchStartedAt
    ? Math.max(0, (searchCompletedAt || now) - searchStartedAt)
    : providerDurationMs;
  const searchInProgress = Boolean(
    message.streaming && searchStartedAt && !searchCompletedAt,
  );
  const turnInProgress = Boolean(
    message.streaming && turnStartedAt && !searchStartedAt,
  );
  useEffect(() => {
    if (!searchInProgress && !turnInProgress) return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [searchInProgress, turnInProgress]);
  return {
    durationMs,
    now,
    providerDurationMs,
    searchCompletedAt,
    searchInProgress,
    searchStartedAt,
    sourceCount: citedSearchSourceCount(
      message.content,
      message.searchResults?.results || [],
    ),
    turnInProgress,
    turnStartedAt,
  };
}

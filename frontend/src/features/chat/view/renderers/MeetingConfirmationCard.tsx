import { useEffect, useRef, useState } from 'react';
import { Button } from 'tdesign-react';

import { nextWholeHourRange } from '../../../../components/chat/workspaceUi';
import { useLanguage } from '../../../../i18n';
import type { WorkspaceAction } from '../../../../shared/types';

interface Props {
  action: WorkspaceAction;
  busy: boolean;
  onUpdate(input: Record<string, unknown>): Promise<void>;
  onConfirm(): Promise<void>;
  onCancel(): Promise<void>;
}

function meetingInputValue(value?: string): string {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
}

export function MeetingConfirmationCard({
  action,
  busy,
  onUpdate,
  onConfirm,
  onCancel,
}: Props) {
  const { t } = useLanguage();
  const startInputRef = useRef<HTMLInputElement>(null);
  const [subject, setSubject] = useState(String(action.payload.subject || t('tencentMeeting')));
  const [startTime, setStartTime] = useState(meetingInputValue(action.payload.start_time));
  const [endTime, setEndTime] = useState(meetingInputValue(action.payload.end_time));
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const warnings = action.payload.warnings || [];
  const validationErrors = action.payload.validation_errors || [];
  const result = action.result || {};

  useEffect(() => {
    setSubject(String(action.payload.subject || t('tencentMeeting')));
    setStartTime(meetingInputValue(action.payload.start_time));
    setEndTime(meetingInputValue(action.payload.end_time));
    setAcknowledged([]);
  }, [action.id, action.version, action.payload.subject, action.payload.start_time, action.payload.end_time, t]);

  const normalizedSubject = subject.trim() || t('tencentMeeting');
  const dirty = normalizedSubject !== String(action.payload.subject || t('tencentMeeting'))
    || startTime !== meetingInputValue(action.payload.start_time)
    || endTime !== meetingInputValue(action.payload.end_time);
  const timesComplete = Boolean(
    startTime
    && endTime
    && new Date(endTime).getTime() > new Date(startTime).getTime(),
  );
  const needsValidation = dirty
    || Boolean(action.payload.missing_fields?.length)
    || validationErrors.length > 0;
  const warningsAccepted = warnings.every((warning) => acknowledged.includes(warning));
  const useSuggestedTime = () => {
    const range = nextWholeHourRange();
    setStartTime(meetingInputValue(range.start));
    setEndTime(meetingInputValue(range.end));
  };
  const useOneHourDuration = () => {
    if (!startTime) return;
    setEndTime(meetingInputValue(
      new Date(new Date(startTime).getTime() + 60 * 60_000).toISOString(),
    ));
  };

  if (action.status !== 'awaiting_confirmation') {
    return <div className="workspace-confirm-card meeting-confirm-card">
      <div className="workspace-confirm-title">
        {t('meetingNamed', { subject: String(action.payload.subject || t('unnamedMeeting')) })}
      </div>
      <div className={`workspace-action-status status-${action.status}`}>
        {action.status === 'succeeded'
          ? t('meetingCreatedCalendar')
          : action.status === 'cancelled'
            ? t('cancelled')
            : action.status === 'reconciliation_required'
              ? t('needsReview', { error: action.error || t('externalResultUnknown') })
              : action.status === 'failed'
                ? t('failedWithReason', { error: action.error || t('executionFailed') })
                : t('processing')}
      </div>
      {typeof result.join_url === 'string' && result.join_url
        && <a href={result.join_url} target="_blank" rel="noreferrer">{t('joinTencentMeeting')}</a>}
      {typeof result.trace_id === 'string' && result.trace_id
        && <div className="workspace-confirm-meta">{t('traceId', { id: result.trace_id })}</div>}
    </div>;
  }

  return <div className="workspace-confirm-card meeting-confirm-card">
    <div className="workspace-confirm-title">{t('createTencentMeeting')}</div>
    <p className="meeting-confirm-help">{t('meetingConfirmHelp')}</p>
    <label>{t('meetingSubject')}
      <input value={subject} maxLength={120} onInput={(event) => setSubject(event.currentTarget.value)} />
    </label>
    <div className="meeting-confirm-times">
      <label>{t('startTime')}
        <input ref={startInputRef} type="datetime-local" value={startTime} onInput={(event) => setStartTime(event.currentTarget.value)} />
      </label>
      <label>{t('endTime')}
        <input type="datetime-local" value={endTime} onInput={(event) => setEndTime(event.currentTarget.value)} />
      </label>
    </div>
    {validationErrors.map((message) => <div key={message} className="meeting-confirm-error">{message}</div>)}
    {!startTime && <div className="meeting-confirm-error">{t('chooseStartTime')}</div>}
    {!endTime && <div className="meeting-confirm-error">{t('chooseEndTime')}</div>}
    {startTime && endTime && !timesComplete
      && <div className="meeting-confirm-error">{t('endAfterStart')}</div>}
    {(!startTime || !endTime) && <div className="meeting-quick-actions">
      <span>{t('quickFill')}</span>
      <Button size="small" variant="text" disabled={busy} onClick={useSuggestedTime}>{t('nextHourOneHour')}</Button>
      {startTime && !endTime && <Button size="small" variant="text" disabled={busy} onClick={useOneHourDuration}>{t('oneHourFromStart')}</Button>}
    </div>}
    {!needsValidation && warnings.map((warning) => <label key={warning} className="meeting-warning-choice">
      <input
        type="checkbox"
        checked={acknowledged.includes(warning)}
        onChange={(event) => setAcknowledged((items) => event.target.checked
          ? [...items, warning]
          : items.filter((item) => item !== warning))}
      />
      <span><b>{t('scheduleWarning')}</b>{warning}<small>{t('acknowledgeConflict')}</small></span>
    </label>)}
    {!needsValidation && warnings.length > 1 && !warningsAccepted && <Button
      size="small"
      variant="text"
      disabled={busy}
      onClick={() => setAcknowledged([...warnings])}
    >{t('acceptAllConflicts', { count: warnings.length })}</Button>}
    <div className="workspace-confirm-actions">
      {needsValidation
        ? <Button
          size="small"
          theme="primary"
          loading={busy}
          disabled={!timesComplete}
          onClick={() => void onUpdate({
            subject: normalizedSubject,
            start_time: new Date(startTime).toISOString(),
            end_time: new Date(endTime).toISOString(),
          })}
        >{t('saveCheckConflicts')}</Button>
        : <>
          {warnings.length > 0 && <Button size="small" variant="outline" disabled={busy} onClick={() => startInputRef.current?.focus()}>{t('modifyTime')}</Button>}
          <Button
            size="small"
            theme="primary"
            loading={busy}
            disabled={!timesComplete || !warningsAccepted}
            onClick={() => void onConfirm()}
          >{warnings.length ? t('acceptConflictsCreate') : t('createTencentMeeting')}</Button>
        </>}
      <Button size="small" variant="outline" disabled={busy} onClick={() => void onCancel()}>{t('cancel')}</Button>
    </div>
  </div>;
}

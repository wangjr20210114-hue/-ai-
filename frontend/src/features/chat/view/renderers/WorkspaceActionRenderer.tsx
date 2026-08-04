import type { ReactNode } from 'react';
import { Button } from 'tdesign-react';

import ImageStudioCard from '../../../../components/image/ImageStudioCard';
import type { WorkspaceAction } from '../../model';
import { useLanguage } from '../../../../i18n';


export type WorkspaceActionOperation =
  | 'activate_map'
  | 'update_meeting_action'
  | 'confirm_action'
  | 'cancel_action';

interface Props {
  actions: WorkspaceAction[];
  busyKey: string;
  conversationId: string;
  generationActive: boolean;
  onAction(
    action: WorkspaceAction,
    operation: WorkspaceActionOperation,
    input?: Record<string, unknown>,
  ): Promise<void>;
  onRouteCalendarProposal(action: WorkspaceAction): Promise<void>;
  onReplace(action: WorkspaceAction): void;
  renderMeeting(action: WorkspaceAction, busy: boolean): ReactNode;
}

export function WorkspaceActionRenderer({
  actions,
  busyKey,
  conversationId,
  generationActive,
  onAction,
  onRouteCalendarProposal,
  onReplace,
  renderMeeting,
}: Props) {
  const { t } = useLanguage();
  return <>{actions.map((action) => {
    const busy = busyKey === action.id;
    if (action.kind === 'map_recommendation') {
      const calendarAlreadyProposed = actions.some(
        (item) => item.kind === 'calendar_changes',
      );
      return (
        <div className="workspace-map-actions streamed-component" key={action.id}>
          <button
            type="button"
            className="workspace-map-action"
            disabled={generationActive || busy || action.status === 'cancelled'}
            onClick={() => void onAction(action, 'activate_map')}
          >
            {busy ? t('openingMap') : action.payload.action_text || t('viewPlacesOnMap')}
          </button>
          {action.payload.calendar_offer && !calendarAlreadyProposed && (
            <button
              type="button"
              className="workspace-map-action"
              disabled={generationActive || Boolean(busyKey)}
              onClick={() => { void onRouteCalendarProposal(action); }}
            >
              {busyKey === `calendar:${action.id}` ? t('processing') : t('addSchedule')}
            </button>
          )}
        </div>
      );
    }
    if (action.kind === 'image_generate' && action.status !== 'awaiting_confirmation') {
      return (
        <div className="streamed-component" key={action.id}>
          <ImageStudioCard
          action={action}
          conversationId={conversationId}
          onUpdated={onReplace}
          disabled={generationActive}
          />
        </div>
      );
    }
    if (action.kind === 'meeting_create') {
      return <div className="streamed-component" key={action.id}>
        {renderMeeting(action, busy || generationActive)}
      </div>;
    }
    const title = action.kind === 'calendar_changes'
      ? action.payload.summary || t('applyCalendarChanges')
      : t('generateImagePrompt', { prompt: String(action.payload.prompt || '') });
    const result = action.result || {};
    return (
      <div key={action.id} className="workspace-confirm-card streamed-component">
        <div className="workspace-confirm-title">{title}</div>
        {action.payload.warnings?.map((warning) => (
          <div key={warning} className="workspace-confirm-warning">{t('warningContinue', { warning })}</div>
        ))}
        {action.status === 'awaiting_confirmation' ? (
          <div className="workspace-confirm-actions">
            <Button size="small" theme="primary" loading={busy} disabled={generationActive} onClick={() => void onAction(action, 'confirm_action')}>{t('confirm')}</Button>
            <Button size="small" variant="outline" disabled={generationActive || busy} onClick={() => void onAction(action, 'cancel_action')}>{t('cancel')}</Button>
          </div>
        ) : (
          <div className={`workspace-action-status status-${action.status}`}>
            {action.status === 'succeeded' ? t('completed') : action.status === 'cancelled' ? t('cancelled') : action.status === 'reconciliation_required' ? t('needsReview', { error: action.error || t('externalResultUnknown') }) : action.status === 'failed' ? t('failedWithReason', { error: action.error || t('executionFailed') }) : t('processing')}
          </div>
        )}
        {typeof result.join_url === 'string' && result.join_url && <a href={result.join_url} target="_blank" rel="noreferrer">{t('joinTencentMeeting')}</a>}
        {typeof result.trace_id === 'string' && result.trace_id && <div className="workspace-confirm-meta">{t('traceId', { id: result.trace_id })}</div>}
        {typeof result.image_url === 'string' && result.image_url && <img className="workspace-generated-image" src={result.image_url} alt={String(action.payload.prompt || t('generatedImage'))} />}
      </div>
    );
  })}</>;
}

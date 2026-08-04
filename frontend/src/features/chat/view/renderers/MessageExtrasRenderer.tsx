import { Button } from 'tdesign-react';

import type { MessageBubbleController } from '../../controller/useMessageBubbleController';
import { useLanguage } from '../../../../i18n';
import type { ChatMessage } from '../../model';
import { PaperRenderer } from './PaperRenderer';

interface Props {
  message: ChatMessage;
  isUser: boolean;
  isLastAiMessage: boolean;
  followUpWidth?: number;
  controller: MessageBubbleController;
}

export function MessageExtrasRenderer({
  message,
  isUser,
  isLastAiMessage,
  followUpWidth,
  controller,
}: Props) {
  const { t } = useLanguage();
  const {
    actionId,
    handleCancelAction,
    handleFollowUp,
    handleSkillAction,
    imageGenerating,
    imageResult,
    intent,
    meetingCreating,
    meetingResult,
    meetingStatusText,
    skill,
    skillActioned,
    workspaceActions,
  } = controller;

  return <>
    {!isUser && intent === 'meeting' && meetingResult?.ok && <div className="followup-section">
      <div className="travel-intent-card" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 8 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>
          {t('meetingCreated', { subject: meetingResult.subject || t('unnamedMeeting') })}
        </div>
        {meetingResult.meeting_code && <div style={{ fontSize: 13, color: 'var(--app-text-2)' }}>
          {t('meetingCode', { code: meetingResult.meeting_code })}
        </div>}
        {meetingResult.join_url && <a
          href={meetingResult.join_url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 13, color: '#2b5aed', wordBreak: 'break-all' }}
        >{meetingResult.join_url}</a>}
        {meetingResult.start_time && <div style={{ fontSize: 12, color: 'var(--app-text-3)' }}>
          {t('startTimeValue', { time: meetingResult.start_time })}
        </div>}
      </div>
    </div>}

    {!isUser && intent === 'meeting' && meetingResult && !meetingResult.ok
      && <div className="followup-section">
        <div className="travel-intent-card" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 12, borderColor: 'var(--td-warning-color)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 20 }}>⚠️</span>
            <span style={{ fontWeight: 600, fontSize: 14 }}>{t('creationFailed')}</span>
          </div>
          <div className="travel-intent-text">
            <span className="travel-intent-icon">⚠️</span>
            <span style={{ fontSize: 13 }}>{meetingResult.error}</span>
          </div>
        </div>
      </div>}

    {!isUser
      && skill
      && skill.mode !== 'immediate'
      && !meetingResult
      && !imageResult
      && !skillActioned
      && <div className="followup-section">
        <div className="travel-intent-card">
          <div className="travel-intent-text">
            <span className="travel-intent-icon">{skill.icon}</span>
            {skill.content}
          </div>
          <Button
            theme="primary"
            size="small"
            loading={(meetingCreating && intent === 'meeting')
              || (imageGenerating && intent === 'image')}
            onClick={handleSkillAction}
          >
            {meetingCreating && intent === 'meeting'
              ? meetingStatusText || t('processing')
              : imageGenerating && intent === 'image'
                ? t('generatingEllipsis')
                : skill.action_label}
          </Button>
          {actionId && (intent === 'meeting' || intent === 'image') && <Button
            variant="outline"
            size="small"
            onClick={() => { void handleCancelAction(); }}
          >{t('cancel')}</Button>}
        </div>
      </div>}

    {!isUser
      && intent === 'image'
      && !workspaceActions.some((action) => action.kind === 'image_generate')
      && imageResult?.ok
      && imageResult.image_url
      && <div className="followup-section">
        <div className="message-generated-image">
          <img src={imageResult.image_url} alt={imageResult.prompt || t('generatedImageAlt')} />
        </div>
      </div>}

    {!isUser && intent === 'image' && imageResult && !imageResult.ok
      && <div className="followup-section">
        <div className="travel-intent-card" style={{ borderColor: 'var(--td-error-color)' }}>
          <div className="travel-intent-text">
            <span className="travel-intent-icon">⚠️</span>
            {imageResult.error}
          </div>
        </div>
      </div>}

    <PaperRenderer message={message} />

    {!isUser
      && !message.streaming
      && isLastAiMessage
      && Boolean(message.followUps?.length)
      && <div
        className="followup-section answer-followups"
        style={followUpWidth ? { width: followUpWidth } : undefined}
      >
        <div className="followup-label">{t('followUpLabel')}</div>
        <div className="followup-list">
          {message.followUps?.map((question, index) => <button
            key={`${index}:${question}`}
            className="followup-chip"
            onClick={() => handleFollowUp(question)}
          >{question}</button>)}
        </div>
      </div>}
  </>;
}

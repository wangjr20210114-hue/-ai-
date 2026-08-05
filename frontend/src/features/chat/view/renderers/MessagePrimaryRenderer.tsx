import type { RefObject } from 'react';
import { CheckIcon, CopyIcon, ImageIcon } from 'tdesign-icons-react';

import type { MessageBubbleController } from '../../controller/useMessageBubbleController';
import { publicAssistantMarkdown, streamingMarkdownAnswer, workspaceActionsReady } from '../../../../components/chat/streamingAnswer';
import { useLanguage } from '../../../../i18n';
import type { ChatClient } from '../../../../services/chatClient';
import type { ChatMessage, ProactiveState } from '../../model';
import { ClarificationCard } from './ClarificationCard';
import { MeetingConfirmationCard } from './MeetingConfirmationCard';
import { ProgressRenderer } from './ProgressRenderer';
import { ProactiveRenderer } from './ProactiveRenderer';
import { TextRenderer } from './TextRenderer';
import { WorkspaceActionRenderer } from './WorkspaceActionRenderer';

interface Props {
  message: ChatMessage;
  client: RefObject<ChatClient | null>;
  bubbleRef: RefObject<HTMLDivElement | null>;
  clarificationAnswered: boolean;
  generationActive: boolean;
  conversationId: string;
  previousUserMessage?: ChatMessage;
  proactive: ProactiveState | null;
  assistantChainTail: boolean;
  authIsGuest: boolean;
  controller: MessageBubbleController;
}

const SKILL_NAME_KEYS = {
  'web-search': 'skillSearchName',
  vision: 'skillVisionName',
  'image-studio': 'skillImageName',
  maps: 'skillMapsName',
  calendar: 'skillCalendarName',
  'proactive-agent': 'skillProactiveName',
  'paper-reading': 'skillPaperName',
  'tencent-meeting': 'skillMeetingName',
} as const;

export function MessagePrimaryRenderer({
  message,
  client,
  bubbleRef,
  clarificationAnswered,
  generationActive,
  conversationId,
  previousUserMessage,
  proactive,
  assistantChainTail,
  authIsGuest,
  controller,
}: Props) {
  const { t } = useLanguage();
  const markdown = publicAssistantMarkdown(
    message.streaming ? streamingMarkdownAnswer(message.content) : message.content,
  );
  return <>
    <ProgressRenderer message={message} />
    {markdown && <TextRenderer
      content={markdown}
      searchMeta={message.searchResults}
      streaming={Boolean(message.streaming)}
    />}
    {!message.streaming && message.experienceHints?.map((hint, index) => {
      const loginRequired = hint.login_required && authIsGuest;
      const names = hint.skill_ids.map((skillId) => {
        const key = SKILL_NAME_KEYS[skillId as keyof typeof SKILL_NAME_KEYS];
        return key ? t(key) : skillId;
      }).join('、');
      return <small className="answer-experience-hint" key={`${hint.kind}-${index}`}>
        {hint.kind === 'freshness'
          ? t(loginRequired ? 'answerFreshnessLoginHint' : 'answerFreshnessHint')
          : t(loginRequired ? 'answerSkillLoginHint' : 'answerSkillHint', { skills: names })}
      </small>;
    })}
    {message.clarification && <ClarificationCard
      clarification={message.clarification}
      messageId={message.id}
      client={client}
      answered={clarificationAnswered}
      generationActive={generationActive}
    />}
    <ProactiveRenderer
      message={message}
      proactive={proactive}
      controller={controller}
    />
    {message.failed && previousUserMessage && <button
      type="button"
      className="chat-retry-button"
      disabled={controller.retryingAnswer || generationActive}
      onPointerDown={(event) => event.stopPropagation()}
      onClick={() => { void controller.retryFailedAnswer(); }}
    >
      {controller.retryingAnswer ? t('retrying') : t('retryGeneration')}
    </button>}
    {workspaceActionsReady(message.streaming) && <WorkspaceActionRenderer
      actions={controller.workspaceActions}
      busyKey={controller.workspaceBusy}
      conversationId={conversationId}
      generationActive={generationActive}
      onAction={controller.handleWorkspaceAction}
      onRouteCalendarProposal={controller.requestRouteCalendarProposal}
      onReplace={controller.replaceWorkspaceAction}
      renderMeeting={(action, busy) => <MeetingConfirmationCard
        action={action}
        busy={busy}
        onUpdate={(input) => controller.handleWorkspaceAction(
          action,
          'update_meeting_action',
          input,
        )}
        onConfirm={() => controller.handleWorkspaceAction(action, 'confirm_action')}
        onCancel={() => controller.handleWorkspaceAction(action, 'cancel_action')}
      />}
    />}
    {!message.streaming && markdown.trim() && assistantChainTail && <div className="answer-action-group">
      <button
        type="button"
        className="answer-action-button"
        title={t('saveImage')}
        aria-label={t('saveImage')}
        disabled={controller.answerSaving}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => { void controller.saveAnswerImage(bubbleRef.current); }}
      >
        <ImageIcon aria-hidden="true" />
      </button>
      <button
        type="button"
        className={`answer-action-button answer-copy-button${controller.answerCopied ? ' is-copied' : ''}`}
        title={t('copy')}
        aria-label={t('copy')}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => { void controller.copyAnswerText(); }}
      >
        {controller.answerCopied
          ? <CheckIcon aria-hidden="true" />
          : <CopyIcon aria-hidden="true" />}
      </button>
    </div>}
    {message.streaming && message.content && <span className="typing-cursor">▊</span>}
  </>;
}

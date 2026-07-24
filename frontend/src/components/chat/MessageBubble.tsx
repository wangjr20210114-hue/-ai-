import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { CheckIcon, CopyIcon, ImageIcon } from 'tdesign-icons-react';
import { toBlob } from 'html-to-image';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ChatMessage, ClarificationPrompt, TravelPlan, SkillInfo, MeetingResult, ScheduleItem, WorkspaceAction } from '../../types';
import type { ChatClient } from '../../services/chatClient';
import { proactiveOperation, workspaceOperation } from '../../services/api';
import TravelPlanCard from '../travel/TravelPlanCard';
import PaperListCard from '../paper/PaperListCard';
import PaperInlineReader from '../paper/PaperInlineReader';
import ImageStudioCard from '../image/ImageStudioCard';
import MarkdownRenderer from '../common/MarkdownRenderer';
import { followUpDraftAction } from './followUps';
import { generatedImageOpportunitySignal, nextWholeHourRange, usableMapPlaces } from './workspaceUi';
import { hasTextSelectionInside } from './scrollSelection';
import { streamingMarkdownAnswer } from './streamingAnswer';
import { clarificationSubmissionText } from './clarificationSubmission';
import { loadProactiveDocumentContext } from '../../services/proactiveDocument';
import type { ProactiveNotification } from '../../types';
import { markdownToPlainText } from '../common/richContent';
import { getStoredLanguage, translate, useLanguage } from '../../i18n';

interface Props {
  message: ChatMessage;
  client: React.RefObject<ChatClient | null>;
}

function imageGroup(action: WorkspaceAction): string {
  return action.kind === 'image_generate' ? String(action.payload.group_id || action.id) : '';
}

function consolidateActions(actions: WorkspaceAction[]): WorkspaceAction[] {
  const output: WorkspaceAction[] = [];
  const imageIndex = new Map<string, number>();
  for (const action of actions) {
    const group = imageGroup(action);
    if (!group) { output.push(action); continue; }
    const previous = imageIndex.get(group);
    if (previous === undefined) {
      imageIndex.set(group, output.length); output.push(action);
    } else {
      output[previous] = action;
    }
  }
  return output;
}

function meetingInputValue(value?: string): string {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function saveElementAsImage(element: HTMLElement): Promise<void> {
  const unavailable = `<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="100%" height="100%" rx="18" fill="#eef1f8"/><text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" fill="#75809a" font-family="sans-serif" font-size="24">${translate('imageUnavailable')}</text></svg>`;
  const rect = element.getBoundingClientRect();
  const backgroundColor = getComputedStyle(element).backgroundColor || '#ffffff';
  const png = await toBlob(element, {
    cacheBust: true,
    width: Math.ceil(rect.width),
    height: Math.ceil(rect.height),
    pixelRatio: Math.min(2, Math.max(1, window.devicePixelRatio || 1)),
    backgroundColor,
    // The bubble's border is a visual affordance, not answer content. Export
    // without it so an anti-aliased border can never be a different size than
    // the rendered content (and the saved image remains clean on all themes).
    style: {
      border: 'none',
      boxShadow: 'none',
      borderRadius: '0',
      backgroundColor,
    },
    imagePlaceholder: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(unavailable)}`,
    skipFonts: true,
    filter: (node) => !(node instanceof HTMLElement)
      || (!node.classList.contains('answer-action-group') && !node.classList.contains('typing-cursor')),
  });
  if (!png) throw new Error('png unavailable');
  triggerDownload(png, translate('answerFileName', { time: new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-') }));
}

function ClarificationCard({
  clarification,
  client,
  answered,
}: {
  clarification: ClarificationPrompt;
  client: React.RefObject<ChatClient | null>;
  answered: boolean;
}) {
  const { messages } = useAppState();
  const { t } = useLanguage();
  const [values, setValues] = useState<Record<string, string | string[]>>({});
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isSubmitted = submitted || answered;
  const setValue = (id: string, value: string | string[]) => setValues((current) => ({ ...current, [id]: value }));
  const generationActive = messages.some((item) => item.streaming);
  const complete = clarification.fields.every((field) => {
    if (!field.required) return true;
    const value = values[field.id];
    return Array.isArray(value) ? value.length > 0 : Boolean(String(value || '').trim());
  });
  const submit = async () => {
    if (!client.current || !complete || isSubmitted || submitting || generationActive) {
      if (!client.current) MessagePlugin.warning(t('connectionNotReady'));
      return;
    }
    const content = clarificationSubmissionText(clarification, values, t('clarificationAnswerIntro'));
    const userMessage: ChatMessage = {
      id: `clarification-${clarification.id}-${Date.now()}`,
      role: 'user',
      content,
      ts: Date.now(),
    };
    setSubmitted(true);
    setSubmitting(true);
    MessagePlugin.success(t('askContinue'));
    try {
      await Promise.resolve(client.current.send({
        type: 'user_activity',
        payload: {
          activity: 'clarification_answered',
          text: content,
          message_id: userMessage.id,
          client_message_id: userMessage.id,
          client_message: userMessage,
          reference_images: [],
          response_language: getStoredLanguage(),
        },
      }));
    } catch {
      setSubmitted(false);
      MessagePlugin.error(t('serviceError'));
    } finally {
      setSubmitting(false);
    }
  };
  return <div className="clarification-card">
    <strong>{clarification.title}</strong>
    <p>{clarification.prompt}</p>
    {clarification.fields.map((field) => {
      const value = values[field.id];
      if (field.type === 'single' || field.type === 'boolean') {
        const options = field.type === 'boolean' ? [t('yes'), t('no')] : (field.options || []);
        return <fieldset className="clarification-field" key={field.id} disabled={isSubmitted}>
          <legend>{field.label}{field.required ? t('requiredSingle') : ''}</legend>
          <div className="clarification-option-list">{options.map((option) => <label key={option} className="clarification-option">
            <input type="radio" name={`${clarification.id}-${field.id}`} checked={value === option} onChange={() => setValue(field.id, option)} />{option}
          </label>)}</div>
        </fieldset>;
      }
      if (field.type === 'multi') return <fieldset className="clarification-field" key={field.id} disabled={isSubmitted}>
        <legend>{field.label}{field.required ? t('requiredMulti') : ''}</legend>
        <div className="clarification-option-list">{(field.options || []).map((option) => {
          const selected = Array.isArray(value) && value.includes(option);
          return <label key={option} className="clarification-option"><input type="checkbox" checked={selected} onChange={(event) => {
            const current = Array.isArray(value) ? value : [];
            setValue(field.id, event.target.checked ? [...current, option] : current.filter((item) => item !== option));
          }} />{option}</label>;
        })}</div>
      </fieldset>;
      return <label className="clarification-field" key={field.id}><span>{field.label}{field.required ? t('requiredField') : ''}</span><input
        type={field.type === 'date' ? 'date' : field.type === 'time' ? 'time' : field.type === 'datetime' ? 'datetime-local' : 'text'}
        value={typeof value === 'string' ? value : ''}
        placeholder={field.placeholder}
        disabled={isSubmitted}
        onChange={(event) => setValue(field.id, event.target.value)}
      /></label>;
    })}
    <div className="clarification-actions"><Button size="small" theme="primary" loading={submitting} disabled={!complete || isSubmitted || generationActive} onClick={() => { void submit(); }}>{isSubmitted ? t('filledInput') : t('completeAndContinue')}</Button></div>
  </div>;
}

function MeetingConfirmationCard({
  action,
  busy,
  onUpdate,
  onConfirm,
  onCancel,
}: {
  action: WorkspaceAction;
  busy: boolean;
  onUpdate: (input: Record<string, unknown>) => Promise<void>;
  onConfirm: () => Promise<void>;
  onCancel: () => Promise<void>;
}) {
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
  const currentStart = meetingInputValue(action.payload.start_time);
  const currentEnd = meetingInputValue(action.payload.end_time);
  const dirty = normalizedSubject !== String(action.payload.subject || t('tencentMeeting'))
    || startTime !== currentStart
    || endTime !== currentEnd;
  const timesComplete = Boolean(startTime && endTime && new Date(endTime).getTime() > new Date(startTime).getTime());
  const needsValidation = dirty || Boolean(action.payload.missing_fields?.length) || validationErrors.length > 0;
  const warningsAccepted = warnings.every((warning) => acknowledged.includes(warning));
  const useSuggestedTime = () => {
    const range = nextWholeHourRange();
    setStartTime(meetingInputValue(range.start));
    setEndTime(meetingInputValue(range.end));
  };
  const useOneHourDuration = () => {
    if (!startTime) return;
    setEndTime(meetingInputValue(new Date(new Date(startTime).getTime() + 60 * 60_000).toISOString()));
  };

  if (action.status !== 'awaiting_confirmation') {
    return <div className="workspace-confirm-card meeting-confirm-card">
      <div className="workspace-confirm-title">{t('meetingNamed', { subject: String(action.payload.subject || t('unnamedMeeting')) })}</div>
      <div className={`workspace-action-status status-${action.status}`}>
        {action.status === 'succeeded' ? t('meetingCreatedCalendar') : action.status === 'cancelled' ? t('cancelled') : action.status === 'reconciliation_required' ? t('needsReview', { error: action.error || t('externalResultUnknown') }) : action.status === 'failed' ? t('failedWithReason', { error: action.error || t('executionFailed') }) : t('processing')}
      </div>
      {typeof result.join_url === 'string' && result.join_url && <a href={result.join_url} target="_blank" rel="noreferrer">{t('joinTencentMeeting')}</a>}
      {typeof result.trace_id === 'string' && result.trace_id && <div className="workspace-confirm-meta">{t('traceId', { id: result.trace_id })}</div>}
    </div>;
  }

  return <div className="workspace-confirm-card meeting-confirm-card">
    <div className="workspace-confirm-title">{t('createTencentMeeting')}</div>
    <p className="meeting-confirm-help">{t('meetingConfirmHelp')}</p>
    <label>{t('meetingSubject')}<input value={subject} maxLength={120} onInput={(event) => setSubject(event.currentTarget.value)} /></label>
    <div className="meeting-confirm-times">
      <label>{t('startTime')}<input ref={startInputRef} type="datetime-local" value={startTime} onInput={(event) => setStartTime(event.currentTarget.value)} /></label>
      <label>{t('endTime')}<input type="datetime-local" value={endTime} onInput={(event) => setEndTime(event.currentTarget.value)} /></label>
    </div>
    {validationErrors.map((message) => <div key={message} className="meeting-confirm-error">{message}</div>)}
    {!startTime && <div className="meeting-confirm-error">{t('chooseStartTime')}</div>}
    {!endTime && <div className="meeting-confirm-error">{t('chooseEndTime')}</div>}
    {startTime && endTime && !timesComplete && <div className="meeting-confirm-error">{t('endAfterStart')}</div>}
    {(!startTime || !endTime) && <div className="meeting-quick-actions">
      <span>{t('quickFill')}</span>
      <Button size="small" variant="text" disabled={busy} onClick={useSuggestedTime}>{t('nextHourOneHour')}</Button>
      {startTime && !endTime && <Button size="small" variant="text" disabled={busy} onClick={useOneHourDuration}>{t('oneHourFromStart')}</Button>}
    </div>}
    {!needsValidation && warnings.map((warning) => <label key={warning} className="meeting-warning-choice">
      <input
        type="checkbox"
        checked={acknowledged.includes(warning)}
        onChange={(event) => setAcknowledged((items) => event.target.checked ? [...items, warning] : items.filter((item) => item !== warning))}
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
      {needsValidation ? <Button
        size="small"
        theme="primary"
        loading={busy}
        disabled={!timesComplete}
        onClick={() => void onUpdate({
          subject: normalizedSubject,
          start_time: new Date(startTime).toISOString(),
          end_time: new Date(endTime).toISOString(),
        })}
      >{t('saveCheckConflicts')}</Button> : <>
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

/** 单条消息气泡。AI 消息下方根据 skill.intent 渲染不同卡片。 */
export default function MessageBubble({ message, client }: Props) {
  const isUser = message.role === 'user';
  const bubbleRef = useRef<HTMLDivElement>(null);
  const [followUpWidth, setFollowUpWidth] = useState<number>();
  const dispatch = useAppDispatch();
  const { t } = useLanguage();
  const { conversationId, messages, proactive } = useAppState();
  // 追问只在最后一条 AI 消息显示
  const isLastAIMessage = !isUser && messages[messages.length - 1]?.id === message.id;
  const messageIndex = messages.findIndex((item) => item.id === message.id);
  const clarificationAnswered = Boolean(message.clarification)
    && messages.slice(messageIndex + 1).some((item) => item.role === 'user');
  const previousUserMessage = messageIndex > 0
    ? [...messages.slice(0, messageIndex)].reverse().find((item) => item.role === 'user')
    : undefined;

  // 旅游状态
  const [travelPlan, setTravelPlan] = useState<TravelPlan | null>(message.travelPlanData || null);
  const [travelStartTs] = useState<number | undefined>(message.travelStartTs);
  const [parsedSchedules] = useState<Partial<ScheduleItem>[]>(message.parsedSchedules || []);

  // 会议状态
  const [meetingCreating, setMeetingCreating] = useState(false);
  const [meetingResult, setMeetingResult] = useState<MeetingResult | null>(null);
  const [meetingStatusText, setMeetingStatusText] = useState('');

  // 通用技能执行状态
  const [skillActioned, setSkillActioned] = useState(false);
  const [workspaceActions, setWorkspaceActions] = useState<WorkspaceAction[]>(consolidateActions(message.workspaceActions || []));
  const [workspaceBusy, setWorkspaceBusy] = useState('');
  const [proactiveBusy, setProactiveBusy] = useState('');
  const [answerCopied, setAnswerCopied] = useState(false);
  const [answerSaving, setAnswerSaving] = useState(false);
  const [retryingAnswer, setRetryingAnswer] = useState(false);

  const mutateProactive = async (key: string, operation: string, input: Record<string, unknown>) => {
    setProactiveBusy(key);
    try {
      const next = await proactiveOperation(conversationId, operation, input);
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('proactiveOperationFailed'));
    } finally { setProactiveBusy(''); }
  };

  const applyProactiveSuggestion = async (item: ProactiveNotification) => {
    setProactiveBusy(`read:${item.id}`);
    try {
      const documentContext = await loadProactiveDocumentContext(item);
      dispatch({ type: 'SET_DOCUMENT_CONTEXT', payload: documentContext });
      dispatch({ type: 'SET_DRAFT', payload: item.action_prompt || t('helpMeHandle', { title: item.title }) });
      const next = await proactiveOperation(conversationId, 'mark_read', { notification_id: item.id });
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('proactiveSuggestionFailed'));
    } finally {
      setProactiveBusy('');
    }
  };

  // Tool actions arrive after the streaming message bubble has mounted. Keep
  // the local interactive copy in sync instead of freezing the initial empty
  // array for the lifetime of the bubble.
  useEffect(() => {
    setWorkspaceActions(consolidateActions(message.workspaceActions || []));
  }, [message.workspaceActions]);

  useLayoutEffect(() => {
    if (isUser || message.streaming || !message.followUps?.length || !bubbleRef.current) {
      setFollowUpWidth(undefined);
      return;
    }
    const bubble = bubbleRef.current;
    const update = () => {
      if (hasTextSelectionInside(bubble, window.getSelection())) return;
      // Preserve fractional CSS pixels so the follow-up border tracks the
      // answer bubble exactly instead of introducing a one-pixel seam.
      const width = bubble.getBoundingClientRect().width;
      setFollowUpWidth(Number(width.toFixed(2)));
    };
    update();
    // The message row has a short reveal transform. Re-measure after it ends
    // because ResizeObserver reports layout changes, not transform changes.
    const settleTimer = window.setTimeout(update, 360);
    const observer = new ResizeObserver(update);
    observer.observe(bubble);
    return () => {
      window.clearTimeout(settleTimer);
      observer.disconnect();
    };
  }, [isUser, message.streaming, message.followUps]);

  const skill: SkillInfo | undefined = message.skill;
  const intent = skill?.intent;

  const handleFollowUp = (question: string) => {
    // Suggestions are editable prompts, not commands. The user must still
    // explicitly press Send before any message is persisted or reaches Agent.
    dispatch(followUpDraftAction(question));
  };

  const copyAnswerText = async () => {
    const plainText = markdownToPlainText(message.content, message.searchResults?.results || []);
    if (!plainText) {
      MessagePlugin.warning(t('noPlainText'));
      return;
    }
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(plainText);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = plainText;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        if (!document.execCommand('copy')) throw new Error('copy failed');
        textarea.remove();
      }
      setAnswerCopied(true);
      window.setTimeout(() => setAnswerCopied(false), 1600);
      MessagePlugin.success(t('plainTextCopied'));
    } catch {
      MessagePlugin.error(t('clipboardDenied'));
    }
  };

  const saveAnswerImage = async () => {
    if (!bubbleRef.current || answerSaving) return;
    setAnswerSaving(true);
    try {
      await saveElementAsImage(bubbleRef.current);
      MessagePlugin.success(t('answerImageSaved'));
    } catch {
      MessagePlugin.error(t('answerImageSaveFailed'));
    } finally {
      setAnswerSaving(false);
    }
  };

  const retryFailedAnswer = async () => {
    if (!previousUserMessage || retryingAnswer || messages.some((item) => item.streaming)) return;
    if (!client.current) {
      dispatch({ type: 'SET_DRAFT', payload: previousUserMessage.content });
      MessagePlugin.warning(t('connectionNotReady'));
      return;
    }
    const retryMessage: ChatMessage = {
      id: `retry-${Date.now()}`,
      role: 'user',
      content: previousUserMessage.content,
      ts: Date.now(),
    };
    setRetryingAnswer(true);
    try {
      await Promise.resolve(client.current.send({
        type: 'user_activity',
        payload: {
          activity: 'retried',
          text: retryMessage.content,
          message_id: retryMessage.id,
          client_message_id: retryMessage.id,
          client_message: retryMessage,
          reference_images: [],
          response_language: getStoredLanguage(),
        },
      }));
    } finally {
      setRetryingAnswer(false);
    }
  };

  type ImageActionResult = { ok: boolean; image_url?: string; prompt?: string; error?: string };
  const [imageGenerating, setImageGenerating] = useState(false);
  const [imageResult, setImageResult] = useState<ImageActionResult | null>(null);

  const actionId = typeof skill?.data?.action_id === 'string' ? skill.data.action_id : '';
  const actionVersion = typeof skill?.data?.action_version === 'number'
    ? skill.data.action_version
    : Number(skill?.data?.action_version || 0);

  const executeConfirmedAction = async () => {
    if (!actionId || actionVersion < 1) {
      throw new Error(t('missingActionSnapshot'));
    }
    const response = await workspaceOperation(conversationId, 'confirm_action', {
      action_id: actionId,
      version: actionVersion,
    });
    if (!response.action) throw new Error(t('workspaceNoResult'));
    return response.action;
  };

  const ingestGeneratedImage = (action: WorkspaceAction) => {
    const signal = generatedImageOpportunitySignal(action);
    if (!signal) return;
    void proactiveOperation(conversationId, 'ingest_signal', {
      ...signal,
    }).then((next) => dispatch({ type: 'HYDRATE_PROACTIVE', payload: next }))
      .catch((error) => console.warn('image opportunity ingestion failed', error));
  };

  const handleCreateMeeting = async () => {
    setMeetingCreating(true);
    setMeetingStatusText(t('confirmedWaitingExecutor'));
    try {
      const action = await executeConfirmedAction();
      const data = action.result || {};
      if (action.status === 'succeeded') {
        const result: MeetingResult = {
          ok: true,
          meeting_id: typeof data.meeting_id === 'string' ? data.meeting_id : undefined,
          meeting_code: typeof data.meeting_code === 'string' ? data.meeting_code : undefined,
          join_url: typeof data.join_url === 'string' ? data.join_url : undefined,
          subject: typeof data.subject === 'string' ? data.subject : undefined,
          start_time: typeof data.start_time === 'string' ? data.start_time : undefined,
        };
        setMeetingResult(result);
        MessagePlugin.success(t('meetingCreatedSuccess'));
      } else {
        const error = action.error || t('creationFailed');
        setMeetingResult({ ok: false, error });
        MessagePlugin.warning(error);
      }
    } catch (error) {
      const text = error instanceof Error ? error.message : t('createMeetingFailed');
      setMeetingResult({ ok: false, error: text });
      MessagePlugin.error(text);
    } finally {
      setMeetingCreating(false);
      setMeetingStatusText('');
    }
  };

  const handleGenerateImage = async () => {
    setImageGenerating(true);
    try {
      const action = await executeConfirmedAction();
      const data = action.result || {};
      if (action.status === 'succeeded') {
        const result: ImageActionResult = {
          ok: true,
          image_url: typeof data.image_url === 'string' ? data.image_url : undefined,
          prompt: typeof data.prompt === 'string' ? data.prompt : undefined,
        };
        setImageResult(result);
        ingestGeneratedImage(action);
        MessagePlugin.success(t('imageCreatedSuccess'));
      } else {
        const error = action.error || t('generationFailedShort');
        setImageResult({ ok: false, error });
        MessagePlugin.warning(error);
      }
    } catch (error) {
      const text = error instanceof Error ? error.message : t('imageGenerationFailedShort');
      setImageResult({ ok: false, error: text });
      MessagePlugin.error(text);
    } finally {
      setImageGenerating(false);
    }
  };

  const handleCancelAction = async () => {
    if (!actionId) return;
    try {
      await workspaceOperation(conversationId, 'cancel_action', {
        action_id: actionId,
        version: actionVersion,
      });
      setSkillActioned(true);
      MessagePlugin.success(t('actionCancelled'));
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('cancelFailed'));
    }
  };

  const replaceWorkspaceAction = (next: WorkspaceAction) => {
    setWorkspaceActions((items) => {
      const group = imageGroup(next);
      if (group) return [...items.filter((item) => imageGroup(item) !== group), next];
      return items.some((item) => item.id === next.id)
        ? items.map((item) => item.id === next.id ? next : item)
        : [...items, next];
    });
  };

  const handleWorkspaceAction = async (
    action: WorkspaceAction,
    operation: 'activate_map' | 'update_meeting_action' | 'confirm_action' | 'cancel_action',
    input: Record<string, unknown> = {},
  ) => {
    const mapSnapshot = operation === 'activate_map' ? usableMapPlaces(action) : [];
    if (operation === 'activate_map' && mapSnapshot.length) {
      // The Action already contains a frozen, server-verified place snapshot.
      // Reveal it immediately so a slow/transient activation write cannot make
      // a valid click look ineffective; the request below persists the choice.
      dispatch({
        type: 'SET_MAP_PLACES',
        payload: { places: mapSnapshot, title: action.payload.title, reveal: true },
      });
    }
    setWorkspaceBusy(action.id);
    try {
      const response = await workspaceOperation(conversationId, operation, {
        action_id: action.id,
        version: action.version,
        ...input,
      });
      if (response.action) replaceWorkspaceAction(response.action);
      if (operation === 'activate_map' && response.map?.places?.length) {
        dispatch({ type: 'SET_MAP_PLACES', payload: { places: response.map.places, title: response.map.title, reveal: true } });
        MessagePlugin.success(t('mapShown'));
      } else if (operation === 'activate_map') {
        if (!mapSnapshot.length) throw new Error(t('mapSnapshotUnavailable'));
        MessagePlugin.warning(t('mapSnapshotNotSaved'));
      }
      if (operation === 'update_meeting_action') MessagePlugin.success(t('meetingChecked'));
      if (operation === 'confirm_action' && action.kind === 'calendar_changes') {
        dispatch({ type: 'SET_SCHEDULES', payload: response.schedules || [] });
        const changed = response.changed?.filter((item) => !item.deleted) || [];
        if (changed.length) {
          const first = new Date(changed[0].start_time * 1000);
          const date = [first.getFullYear(), String(first.getMonth() + 1).padStart(2, '0'), String(first.getDate()).padStart(2, '0')].join('-');
          dispatch({ type: 'PULSE_CALENDAR', payload: { date, count: changed.length } });
        }
        MessagePlugin.success(t('calendarChangesApplied'));
      }
      if (operation === 'confirm_action' && action.kind === 'meeting_create') {
        const result = response.action?.result || {};
        if (response.action?.status === 'succeeded') MessagePlugin.success(t('meetingCreatedSuccess'));
        else MessagePlugin.warning(String(response.action?.error || result.error || t('createMeetingFailed')));
      }
      if (operation === 'confirm_action' && action.kind === 'image_generate') {
        if (response.action?.status === 'succeeded') {
          ingestGeneratedImage(response.action);
          MessagePlugin.success(t('imageCreatedSuccess'));
        }
        else MessagePlugin.warning(String(response.action?.error || t('imageGenerationFailedShort')));
      }
      if (operation === 'cancel_action') MessagePlugin.success(t('actionCancelled'));
    } catch (error) {
      const text = error instanceof Error ? error.message : t('operationFailed');
      if (operation === 'activate_map' && mapSnapshot.length) {
        MessagePlugin.warning(t('activatedSnapshotNotSaved', { error: text }));
      } else {
        MessagePlugin.error(text);
      }
    } finally {
      setWorkspaceBusy('');
    }
  };


  /** 通用技能动作处理 */
  const handleSkillAction = () => {
    if (!intent) return;
    setSkillActioned(true);

    switch (intent) {
      case 'travel':
        handleFollowUp(skill?.content || t('continueTravelPlanning'));
        MessagePlugin.info(t('travelDraftReady'));
        break;
      case 'meeting':
        handleCreateMeeting();
        break;
      case 'image':
        handleGenerateImage();
        break;
      case 'translation':
      case 'news':
      case 'paper':
        MessagePlugin.info(t('developing', { action: skill?.action_label || t('execute') }));
        setSkillActioned(false);
        break;
      default:
        break;
    }
  };

  const searchStatus = typeof message.skill?.data?.statusText === 'string'
    ? message.skill.data.statusText
    : t('understandingRequest');
  const progressStatus = message.content
    ? (message.skill?.intent === 'search'
      ? (message.searchResults?.media_pending
        ? t('writingReviewing')
        : t('organizingVerifiedAnswer'))
      : t('organizingAnswer'))
    : searchStatus;
  const markdownRender = {
    content: message.streaming ? streamingMarkdownAnswer(message.content) : message.content,
    searchMeta: message.searchResults,
    streaming: Boolean(message.streaming),
  };
  return (
    <div className={`msg-row ${isUser ? 'user' : 'ai'}`}>
      <div className={`msg-avatar ${isUser ? 'user' : 'ai'}`}>
        {isUser ? t('me') : <img src="/floris-avatar.png" alt="Floris" />}
      </div>
      <div className="msg-content-wrap">
        <div
          ref={bubbleRef}
          className={`msg-bubble ${isUser ? 'user' : 'ai'} ${message.failed ? 'is-error' : ''} ${!isUser && !message.streaming && message.content.trim() ? 'has-copy-action' : ''}`}
        >
          {isUser ? (
            message.content
          ) : (
            <>
              {!message.streaming && message.content.trim() && <div className="answer-action-group">
                <button type="button" className="answer-action-button" title={t('saveImage')} aria-label={t('saveImage')} disabled={answerSaving} onPointerDown={(event) => event.stopPropagation()} onClick={() => { void saveAnswerImage(); }}>
                  <ImageIcon aria-hidden="true" />
                </button>
                <button type="button" className={`answer-action-button answer-copy-button${answerCopied ? ' is-copied' : ''}`} title={t('copy')} aria-label={t('copy')} onPointerDown={(event) => event.stopPropagation()} onClick={() => { void copyAnswerText(); }}>
                  {answerCopied ? <CheckIcon aria-hidden="true" /> : <CopyIcon aria-hidden="true" />}
                </button>
              </div>}
              {/* 搜索动画 */}
              {!isUser && message.streaming && (
                message.skill?.intent === 'image' || progressStatus.includes('生成图片') || progressStatus.includes('绘制') ? <ImageCreationProgress message={message} /> : <div className={`search-progress ${message.content ? 'has-content' : ''}`}>
                  <div className="image-generating-spinner" />
                  <span className="search-progress-status" title={progressStatus}>{progressStatus}</span>
                  <span className="image-generating-dots"><span>.</span><span>.</span><span>.</span></span>
                </div>
              )}
              {message.content && <MarkdownRenderer
                content={markdownRender.content}
                searchMeta={markdownRender.searchMeta}
                streaming={markdownRender.streaming}
              />}
              {message.clarification && <ClarificationCard clarification={message.clarification} client={client} answered={clarificationAnswered} />}
              {message.proactive && proactive && <div className="proactive-conversation-actions">
                {(proactive.notifications || []).filter((item) => item.status !== 'dismissed').slice(0, 3).map((item) => <div className="proactive-conversation-item" key={item.id}>
                  <span>{item.title}</span>
                  <div>
                    <Button size="small" variant="text" loading={proactiveBusy === `read:${item.id}`} onClick={() => { void applyProactiveSuggestion(item); }}>{t('handleForMe')}</Button>
                    <Button size="small" variant="text" loading={proactiveBusy === `snooze:${item.id}`} onClick={() => void mutateProactive(`snooze:${item.id}`, 'snooze', { notification_id: item.id, until: Math.floor(Date.now() / 1000) + 3600 })}>{t('remindInHour')}</Button>
                    <Button size="small" variant="text" loading={proactiveBusy === `dismiss:${item.id}`} onClick={() => void mutateProactive(`dismiss:${item.id}`, 'dismiss', { notification_id: item.id })}>{t('ignore')}</Button>
                  </div>
                </div>)}
                {(proactive.workflows || []).filter((item) => item.status === 'awaiting_confirmation').map((workflow) => <div className="proactive-conversation-item" key={workflow.id}>
                  <span>{t('ongoingTask', { title: workflow.title })}</span><small>{workflow.reason}</small>
                  <div>
                    <Button size="small" theme="primary" loading={proactiveBusy === `workflow:${workflow.id}`} onClick={() => void mutateProactive(`workflow:${workflow.id}`, 'confirm_workflow', { workflow_id: workflow.id, version: workflow.version })}>{t('enableWorkflow')}</Button>
                    <Button size="small" variant="text" onClick={() => void mutateProactive(`workflow:${workflow.id}`, 'reject_workflow', { workflow_id: workflow.id, version: workflow.version })}>{t('notNow')}</Button>
                  </div>
                </div>)}
                {(proactive.workflows || []).filter((item) => item.status === 'active').map((workflow) => {
                  const step = workflow.steps.find((item) => !['completed', 'skipped', 'compensated'].includes(item.status));
                  return <div className="proactive-conversation-item" key={workflow.id}>
                    <span>{t('activeWorkflow', { title: workflow.title })}</span>
                    <small>{step ? t('currentStep', { title: step.title }) : t('workflowSyncing')}</small>
                    <div>
                      {step && ['pending', 'notified'].includes(step.status) && <>
                        <Button size="small" theme="success" loading={proactiveBusy === `complete:${step.id}`} onClick={() => void mutateProactive(`complete:${step.id}`, 'complete_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('completeStep')}</Button>
                        <Button size="small" variant="text" loading={proactiveBusy === `skip:${step.id}`} onClick={() => void mutateProactive(`skip:${step.id}`, 'skip_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('skipStep')}</Button>
                        <Button size="small" variant="text" loading={proactiveBusy === `fail:${step.id}`} onClick={() => void mutateProactive(`fail:${step.id}`, 'fail_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('markFailed')}</Button>
                      </>}
                      {step?.status === 'compensating' && <Button size="small" theme="success" loading={proactiveBusy === `compensate:${step.id}`} onClick={() => void mutateProactive(`compensate:${step.id}`, 'compensate_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('compensationComplete')}</Button>}
                      {step && ['failed', 'attention_required'].includes(step.status) && <Button size="small" variant="outline" loading={proactiveBusy === `retry:${step.id}`} onClick={() => void mutateProactive(`retry:${step.id}`, 'retry_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>{t('retryStep')}</Button>}
                      <Button size="small" variant="text" loading={proactiveBusy === `cancel:${workflow.id}`} onClick={() => void mutateProactive(`cancel:${workflow.id}`, 'cancel_workflow', { workflow_id: workflow.id, version: workflow.version })}>{t('stopWorkflow')}</Button>
                    </div>
                  </div>;
                })}
              </div>}
              {message.failed && previousUserMessage && (
                <button
                  type="button"
                  className="chat-retry-button"
                  disabled={retryingAnswer || messages.some((item) => item.streaming)}
                  onPointerDown={(event) => event.stopPropagation()}
                  onClick={() => { void retryFailedAnswer(); }}
                >
                  {retryingAnswer ? t('retrying') : t('retryGeneration')}
                </button>
              )}
              {!message.streaming && workspaceActions.map((action) => {
                const busy = workspaceBusy === action.id;
                if (action.kind === 'map_recommendation') {
                  return (
                    <button
                      key={action.id}
                      type="button"
                      className="workspace-map-action"
                      disabled={busy || action.status === 'cancelled'}
                      onClick={() => void handleWorkspaceAction(action, 'activate_map')}
                    >
                      {busy ? t('openingMap') : action.payload.action_text || t('viewPlacesOnMap')}
                    </button>
                  );
                }
                if (action.kind === 'image_generate' && action.status !== 'awaiting_confirmation') {
                  return (
                    <ImageStudioCard
                      key={action.id}
                      action={action}
                      conversationId={conversationId}
                      onUpdated={replaceWorkspaceAction}
                    />
                  );
                }
                if (action.kind === 'meeting_create') {
                  return <MeetingConfirmationCard
                    key={action.id}
                    action={action}
                    busy={busy}
                    onUpdate={(input) => handleWorkspaceAction(action, 'update_meeting_action', input)}
                    onConfirm={() => handleWorkspaceAction(action, 'confirm_action')}
                    onCancel={() => handleWorkspaceAction(action, 'cancel_action')}
                  />;
                }
                const title = action.kind === 'calendar_changes'
                  ? action.payload.summary || t('applyCalendarChanges')
                  : t('generateImagePrompt', { prompt: String(action.payload.prompt || '') });
                const result = action.result || {};
                return (
                  <div key={action.id} className="workspace-confirm-card">
                    <div className="workspace-confirm-title">{title}</div>
                    {action.payload.warnings?.map((warning) => (
                      <div key={warning} className="workspace-confirm-warning">{t('warningContinue', { warning })}</div>
                    ))}
                    {action.status === 'awaiting_confirmation' ? (
                      <div className="workspace-confirm-actions">
                        <Button size="small" theme="primary" loading={busy} onClick={() => void handleWorkspaceAction(action, 'confirm_action')}>{t('confirm')}</Button>
                        <Button size="small" variant="outline" disabled={busy} onClick={() => void handleWorkspaceAction(action, 'cancel_action')}>{t('cancel')}</Button>
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
              })}
              {message.streaming && message.content && (
                <span className="typing-cursor">▊</span>
              )}
            </>
          )}
        </div>

        {/* === 旅游：计划卡片 === */}
        {travelPlan && (
          <div style={{ marginTop: 12, maxWidth: '100%' }}>
            <TravelPlanCard
              plan={travelPlan}
              startTs={travelStartTs}
              parsedSchedules={parsedSchedules}
              onSaved={(updated) => setTravelPlan(updated)}
            />
          </div>
        )}

        {/* === 会议：创建结果 === */}
        {!isUser && intent === 'meeting' && meetingResult && meetingResult.ok && (
          <div className="followup-section">
            <div className="travel-intent-card" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 8 }}>
              <div style={{ fontWeight: 600, fontSize: 14 }}>
                {t('meetingCreated', { subject: meetingResult.subject || t('unnamedMeeting') })}
              </div>
              {meetingResult.meeting_code && (
                <div style={{ fontSize: 13, color: 'var(--app-text-2)' }}>
                  {t('meetingCode', { code: meetingResult.meeting_code })}
                </div>
              )}
              {meetingResult.join_url && (
                <a
                  href={meetingResult.join_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: 13, color: '#2b5aed', wordBreak: 'break-all' }}
                >
                  {meetingResult.join_url}
                </a>
              )}
              {meetingResult.start_time && (
                <div style={{ fontSize: 12, color: 'var(--app-text-3)' }}>
                  {t('startTimeValue', { time: meetingResult.start_time })}
                </div>
              )}
            </div>
          </div>
        )}

        {/* 会议创建失败：友好引导卡片 */}
        {!isUser && intent === 'meeting' && meetingResult && !meetingResult.ok && (
          <div className="followup-section">
            <div
              className="travel-intent-card"
              style={{
                flexDirection: 'column',
                alignItems: 'flex-start',
                gap: 12,
                borderColor: 'var(--td-warning-color)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 20 }}>⚠️</span>
                <span style={{ fontWeight: 600, fontSize: 14 }}>{t('creationFailed')}</span>
              </div>
              <div className="travel-intent-text">
                <span className="travel-intent-icon">⚠️</span>
                <span style={{ fontSize: 13 }}>{meetingResult.error}</span>
              </div>
            </div>
          </div>
        )}

        {/* === 通用技能建议卡片（suggest 模式 + 未执行） === */}
        {!isUser && skill && skill.mode !== 'immediate' && !travelPlan && !meetingResult && !imageResult && !skillActioned && (
          <div className="followup-section">
            <div className="travel-intent-card">
              <div className="travel-intent-text">
                <span className="travel-intent-icon">{skill.icon}</span>
                {skill.content}
              </div>
              <Button
                theme="primary"
                size="small"
                loading={(meetingCreating && intent === 'meeting') || (imageGenerating && intent === 'image')}
                onClick={handleSkillAction}
              >
                {(meetingCreating && intent === 'meeting')
                  ? (meetingStatusText || t('processing'))
                  : (imageGenerating && intent === 'image')
                  ? t('generatingEllipsis')
                  : skill.action_label}
              </Button>
              {actionId && (intent === 'meeting' || intent === 'image') && (
                <Button variant="outline" size="small" onClick={() => { void handleCancelAction(); }}>
                  {t('cancel')}
                </Button>
              )}
            </div>
          </div>
        )}

        {/* === 生图结果 === */}
        {!isUser && intent === 'image' && !workspaceActions.some((action) => action.kind === 'image_generate') && imageResult && imageResult.ok && imageResult.image_url && (
          <div className="followup-section">
            <div className="message-generated-image">
              <img
                src={imageResult.image_url}
                alt={imageResult.prompt || t('generatedImageAlt')}
              />
            </div>
          </div>
        )}

        {!isUser && intent === 'image' && imageResult && !imageResult.ok && (
          <div className="followup-section">
            <div className="travel-intent-card" style={{ borderColor: 'var(--td-error-color)' }}>
              <div className="travel-intent-text">
                <span className="travel-intent-icon">⚠️</span>
                {imageResult.error}
              </div>
            </div>
          </div>
        )}

        {/* === 论文列表 + 内联阅读器（气泡下方） === */}
        {message.papers && message.papers.length > 0 && !message.streaming && (
          <div style={{ marginTop: 12, width: '100%' }}>
            <PaperListCard message={message} />
          </div>
        )}

        {message.paperFileId && !message.streaming && (
          <PaperInlineReader
            fileId={message.paperFileId}
            fileName={message.paperFileName || t('pdfDocument')}
            title={message.paperTitle || message.paperFileName || t('pdfReading')}
            assistantEnabled={message.paperIsPaper ?? message.content.includes('已识别为论文')}
          />
        )}

        {/* 搜索结果不再单独展示卡片，已由 AI 自然穿插在 Markdown 回答中 */}

        {/* === 追问建议（只在最后一条 AI 消息显示） === */}
        {!isUser && !message.streaming && isLastAIMessage && message.followUps && message.followUps.length > 0 && (
          <div className="followup-section answer-followups" style={followUpWidth ? { width: followUpWidth } : undefined}>
            <div className="followup-label">{t('followUpLabel')}</div>
            <div className="followup-list">
              {message.followUps.map((q, i) => (
                <button key={i} className="followup-chip" onClick={() => handleFollowUp(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

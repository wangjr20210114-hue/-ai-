import { useEffect, useState } from 'react';
import { MessagePlugin } from 'tdesign-react';
import { toBlob } from 'html-to-image';

import { workspaceOperation } from '../../calendar/model/client';
import { proactiveOperation } from '../../settings/model/client';
import { followUpDraftAction } from '../../../components/chat/followUps';
import {
  generatedImageOpportunitySignal,
  usableMapPlaces,
} from '../../../components/chat/workspaceUi';
import { publicAssistantMarkdown } from '../../../components/chat/streamingAnswer';
import { markdownToPlainText } from '../../../components/common/richContent';
import { getStoredLanguage, translate, useLanguage } from '../../../i18n';
import { loadProactiveDocumentContext } from '../../../services/proactiveDocument';
import type { ChatClient } from '../../../services/chatClient';
import { requestRightWorkspaceOpen } from '../../../services/workspaceEvents';
import { useAppDispatch } from '../../../store/appState';
import type {
  ChatMessage,
  MeetingResult,
  ProactiveNotification,
  ScheduleItem,
  SkillInfo,
  TravelPlan,
  WorkspaceAction,
} from '../../../shared/types';

export interface MessageBubbleControllerInput {
  message: ChatMessage;
  client: React.RefObject<ChatClient | null>;
  previousUserMessage?: ChatMessage;
  generationActive: boolean;
  conversationId: string;
}

export type ImageActionResult = {
  ok: boolean;
  image_url?: string;
  prompt?: string;
  error?: string;
};

function imageGroup(action: WorkspaceAction): string {
  return action.kind === 'image_generate'
    ? String(action.payload.group_id || action.id)
    : '';
}

export function consolidateActions(actions: WorkspaceAction[]): WorkspaceAction[] {
  const output: WorkspaceAction[] = [];
  const imageIndex = new Map<string, number>();
  for (const action of actions) {
    const group = imageGroup(action);
    if (!group) {
      output.push(action);
      continue;
    }
    const previous = imageIndex.get(group);
    if (previous === undefined) {
      imageIndex.set(group, output.length);
      output.push(action);
    } else {
      output[previous] = action;
    }
  }
  return output;
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
    style: {
      border: 'none',
      boxShadow: 'none',
      borderRadius: '0',
      backgroundColor,
    },
    imagePlaceholder: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(unavailable)}`,
    skipFonts: true,
    filter: (node) => !(node instanceof HTMLElement)
      || (!node.classList.contains('answer-action-group')
        && !node.classList.contains('typing-cursor')),
  });
  if (!png) throw new Error('png unavailable');
  triggerDownload(png, translate('answerFileName', {
    time: new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-'),
  }));
}

export function useMessageBubbleController({
  message,
  client,
  previousUserMessage,
  generationActive,
  conversationId,
}: MessageBubbleControllerInput) {
  const dispatch = useAppDispatch();
  const { t } = useLanguage();
  const [travelPlan, setTravelPlan] = useState<TravelPlan | null>(
    message.travelPlanData || null,
  );
  const [travelStartTs] = useState<number | undefined>(message.travelStartTs);
  const [parsedSchedules] = useState<Partial<ScheduleItem>[]>(
    message.parsedSchedules || [],
  );
  const [meetingCreating, setMeetingCreating] = useState(false);
  const [meetingResult, setMeetingResult] = useState<MeetingResult | null>(null);
  const [meetingStatusText, setMeetingStatusText] = useState('');
  const [skillActioned, setSkillActioned] = useState(false);
  const [workspaceActions, setWorkspaceActions] = useState<WorkspaceAction[]>(
    consolidateActions(message.workspaceActions || []),
  );
  const [workspaceBusy, setWorkspaceBusy] = useState('');
  const [proactiveBusy, setProactiveBusy] = useState('');
  const [answerCopied, setAnswerCopied] = useState(false);
  const [answerSaving, setAnswerSaving] = useState(false);
  const [retryingAnswer, setRetryingAnswer] = useState(false);
  const [imageGenerating, setImageGenerating] = useState(false);
  const [imageResult, setImageResult] = useState<ImageActionResult | null>(null);

  const skill: SkillInfo | undefined = message.skill;
  const intent = skill?.intent;
  const actionId = typeof skill?.data?.action_id === 'string'
    ? skill.data.action_id
    : '';
  const actionVersion = typeof skill?.data?.action_version === 'number'
    ? skill.data.action_version
    : Number(skill?.data?.action_version || 0);

  useEffect(() => {
    setWorkspaceActions(consolidateActions(message.workspaceActions || []));
  }, [message.workspaceActions]);

  const handleFollowUp = (question: string) => {
    dispatch(followUpDraftAction(question));
  };

  const mutateProactive = async (
    key: string,
    operation: string,
    input: Record<string, unknown>,
  ) => {
    setProactiveBusy(key);
    try {
      const next = await proactiveOperation(conversationId, operation, input);
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch {
      MessagePlugin.error(t('proactiveOperationFailed'));
    } finally {
      setProactiveBusy('');
    }
  };

  const applyProactiveSuggestion = async (item: ProactiveNotification) => {
    setProactiveBusy(`read:${item.id}`);
    try {
      const documentContext = await loadProactiveDocumentContext(item);
      dispatch({ type: 'SET_DOCUMENT_CONTEXT', payload: documentContext });
      dispatch({
        type: 'SET_DRAFT',
        payload: item.action_prompt || t('helpMeHandle', { title: item.title }),
      });
      const next = await proactiveOperation(conversationId, 'mark_read', {
        notification_id: item.id,
      });
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch {
      MessagePlugin.error(t('proactiveSuggestionFailed'));
    } finally {
      setProactiveBusy('');
    }
  };

  const copyAnswerText = async () => {
    const plainText = markdownToPlainText(
      publicAssistantMarkdown(message.content),
      message.searchResults?.results || [],
    );
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

  const saveAnswerImage = async (element: HTMLElement | null) => {
    if (!element || answerSaving) return;
    setAnswerSaving(true);
    try {
      await saveElementAsImage(element);
      MessagePlugin.success(t('answerImageSaved'));
    } catch {
      MessagePlugin.error(t('answerImageSaveFailed'));
    } finally {
      setAnswerSaving(false);
    }
  };

  const retryFailedAnswer = async () => {
    if (!previousUserMessage || retryingAnswer || generationActive) return;
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

  const requestRouteCalendarProposal = async (action: WorkspaceAction) => {
    if (generationActive || workspaceBusy) return;
    const content = t('routeCalendarRequest');
    if (!client.current) {
      dispatch({ type: 'SET_DRAFT', payload: content });
      MessagePlugin.warning(t('connectionNotReady'));
      return;
    }
    const requestMessage: ChatMessage = {
      id: `route-calendar-${Date.now()}`,
      role: 'user',
      content,
      ts: Date.now(),
    };
    setWorkspaceBusy(`calendar:${action.id}`);
    try {
      await Promise.resolve(client.current.send({
        type: 'user_activity',
        payload: {
          activity: 'route_calendar_offer_accepted',
          text: requestMessage.content,
          message_id: requestMessage.id,
          client_message_id: requestMessage.id,
          client_message: requestMessage,
          reference_images: [],
          response_language: getStoredLanguage(),
          route_plan_id: action.payload.route_plan_id,
        },
      }));
    } catch {
      dispatch({ type: 'SET_DRAFT', payload: content });
      MessagePlugin.error(t('serviceError'));
    } finally {
      setWorkspaceBusy('');
    }
  };

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
    void proactiveOperation(conversationId, 'ingest_signal', signal)
      .then((next) => dispatch({ type: 'HYDRATE_PROACTIVE', payload: next }))
      .catch((error) => console.warn('image opportunity ingestion failed', error));
  };

  const handleCreateMeeting = async () => {
    setMeetingCreating(true);
    setMeetingStatusText(t('confirmedWaitingExecutor'));
    try {
      const action = await executeConfirmedAction();
      const data = action.result || {};
      if (action.status === 'succeeded') {
        setMeetingResult({
          ok: true,
          meeting_id: typeof data.meeting_id === 'string' ? data.meeting_id : undefined,
          meeting_code: typeof data.meeting_code === 'string' ? data.meeting_code : undefined,
          join_url: typeof data.join_url === 'string' ? data.join_url : undefined,
          subject: typeof data.subject === 'string' ? data.subject : undefined,
          start_time: typeof data.start_time === 'string' ? data.start_time : undefined,
        });
        MessagePlugin.success(t('meetingCreatedSuccess'));
      } else {
        setMeetingResult({ ok: false, error: action.error || t('creationFailed') });
        MessagePlugin.warning(t('createMeetingFailed'));
      }
    } catch (error) {
      setMeetingResult({
        ok: false,
        error: error instanceof Error ? error.message : t('createMeetingFailed'),
      });
      MessagePlugin.error(t('createMeetingFailed'));
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
        setImageResult({
          ok: true,
          image_url: typeof data.image_url === 'string' ? data.image_url : undefined,
          prompt: typeof data.prompt === 'string' ? data.prompt : undefined,
        });
        ingestGeneratedImage(action);
        MessagePlugin.success(t('imageCreatedSuccess'));
      } else {
        setImageResult({ ok: false, error: action.error || t('generationFailedShort') });
        MessagePlugin.warning(t('imageGenerationFailedShort'));
      }
    } catch (error) {
      setImageResult({
        ok: false,
        error: error instanceof Error ? error.message : t('imageGenerationFailedShort'),
      });
      MessagePlugin.error(t('imageGenerationFailedShort'));
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
    } catch {
      MessagePlugin.error(t('cancelFailed'));
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
      dispatch({
        type: 'SET_MAP_PLACES',
        payload: {
          places: mapSnapshot,
          title: action.payload.title,
          routeMode: action.payload.route_mode,
          routeStrategy: action.payload.route_strategy,
          showRoute: action.payload.show_route,
          reveal: true,
        },
      });
      requestRightWorkspaceOpen(window);
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
        dispatch({
          type: 'SET_MAP_PLACES',
          payload: {
            places: response.map.places,
            title: response.map.title,
            routeMode: response.map.route_mode || undefined,
            routeStrategy: response.map.route_strategy || undefined,
            showRoute: response.map.show_route,
            reveal: true,
          },
        });
        requestRightWorkspaceOpen(window);
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
          const date = [
            first.getFullYear(),
            String(first.getMonth() + 1).padStart(2, '0'),
            String(first.getDate()).padStart(2, '0'),
          ].join('-');
          dispatch({ type: 'PULSE_CALENDAR', payload: { date, count: changed.length } });
        }
        if (response.action?.status === 'succeeded') {
          MessagePlugin.success(t('calendarChangesApplied'));
        } else {
          MessagePlugin.warning(response.action?.error || t('calendarChangesUnavailable'));
        }
      }
      if (operation === 'confirm_action' && action.kind === 'meeting_create') {
        if (response.action?.status === 'succeeded') MessagePlugin.success(t('meetingCreatedSuccess'));
        else MessagePlugin.warning(t('createMeetingFailed'));
      }
      if (operation === 'confirm_action' && action.kind === 'image_generate') {
        if (response.action?.status === 'succeeded') {
          ingestGeneratedImage(response.action);
          MessagePlugin.success(t('imageCreatedSuccess'));
        } else {
          MessagePlugin.warning(t('imageGenerationFailedShort'));
        }
      }
      if (operation === 'cancel_action') MessagePlugin.success(t('actionCancelled'));
    } catch {
      if (operation === 'activate_map' && mapSnapshot.length) {
        MessagePlugin.warning(t('activatedSnapshotNotSaved'));
      } else {
        MessagePlugin.error(t('operationRetry'));
      }
    } finally {
      setWorkspaceBusy('');
    }
  };

  const handleSkillAction = () => {
    if (!intent) return;
    setSkillActioned(true);
    if (intent === 'travel') {
      handleFollowUp(skill?.content || t('continueTravelPlanning'));
      MessagePlugin.info(t('travelDraftReady'));
    } else if (intent === 'meeting') {
      void handleCreateMeeting();
    } else if (intent === 'image') {
      void handleGenerateImage();
    } else if (['translation', 'news', 'paper'].includes(intent)) {
      MessagePlugin.info(t('developing', {
        action: skill?.action_label || t('execute'),
      }));
      setSkillActioned(false);
    }
  };

  return {
    actionId,
    answerCopied,
    answerSaving,
    applyProactiveSuggestion,
    copyAnswerText,
    handleCancelAction,
    handleFollowUp,
    handleSkillAction,
    handleWorkspaceAction,
    imageGenerating,
    imageResult,
    intent,
    meetingCreating,
    meetingResult,
    meetingStatusText,
    mutateProactive,
    parsedSchedules,
    proactiveBusy,
    replaceWorkspaceAction,
    requestRouteCalendarProposal,
    retryFailedAnswer,
    retryingAnswer,
    saveAnswerImage,
    setTravelPlan,
    skill,
    skillActioned,
    travelPlan,
    travelStartTs,
    workspaceActions,
    workspaceBusy,
  };
}

export type MessageBubbleController = ReturnType<typeof useMessageBubbleController>;

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
import { loadProactiveDocumentContext } from '../../services/proactiveDocument';
import type { ProactiveNotification } from '../../types';
import { markdownToPlainText } from '../common/richContent';
import { getStoredLanguage, useLanguage } from '../../i18n';

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
  const unavailable = '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540"><rect width="100%" height="100%" rx="18" fill="#eef1f8"/><text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" fill="#75809a" font-family="sans-serif" font-size="24">图片暂不可用</text></svg>';
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
  triggerDownload(png, `回答-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`);
}

function ClarificationCard({ clarification }: { clarification: ClarificationPrompt }) {
  const dispatch = useAppDispatch();
  const { t } = useLanguage();
  const [values, setValues] = useState<Record<string, string | string[]>>({});
  const [submitted, setSubmitted] = useState(false);
  const setValue = (id: string, value: string | string[]) => setValues((current) => ({ ...current, [id]: value }));
  const complete = clarification.fields.every((field) => {
    if (!field.required) return true;
    const value = values[field.id];
    return Array.isArray(value) ? value.length > 0 : Boolean(String(value || '').trim());
  });
  const submit = () => {
    const answer = clarification.fields.map((field) => {
      const value = values[field.id];
      return `${field.label}：${Array.isArray(value) ? value.join('、') : String(value || '').trim()}`;
    }).join('\n');
    dispatch({ type: 'SET_DRAFT', payload: `${clarification.prompt}\n${answer}` });
    setSubmitted(true);
    MessagePlugin.success(t('askContinue'));
  };
  return <div className="clarification-card">
    <strong>{clarification.title}</strong>
    <p>{clarification.prompt}</p>
    {clarification.fields.map((field) => {
      const value = values[field.id];
      if (field.type === 'single' || field.type === 'boolean') {
        const options = field.type === 'boolean' ? ['是', '否'] : (field.options || []);
        return <fieldset className="clarification-field" key={field.id} disabled={submitted}>
          <legend>{field.label}{field.required ? '（必选）' : ''}</legend>
          <div className="clarification-option-list">{options.map((option) => <label key={option} className="clarification-option">
            <input type="radio" name={`${clarification.id}-${field.id}`} checked={value === option} onChange={() => setValue(field.id, option)} />{option}
          </label>)}</div>
        </fieldset>;
      }
      if (field.type === 'multi') return <fieldset className="clarification-field" key={field.id} disabled={submitted}>
        <legend>{field.label}{field.required ? '（至少选一项）' : ''}</legend>
        <div className="clarification-option-list">{(field.options || []).map((option) => {
          const selected = Array.isArray(value) && value.includes(option);
          return <label key={option} className="clarification-option"><input type="checkbox" checked={selected} onChange={(event) => {
            const current = Array.isArray(value) ? value : [];
            setValue(field.id, event.target.checked ? [...current, option] : current.filter((item) => item !== option));
          }} />{option}</label>;
        })}</div>
      </fieldset>;
      return <label className="clarification-field" key={field.id}><span>{field.label}{field.required ? '（必填）' : ''}</span><input
        type={field.type === 'date' ? 'date' : field.type === 'datetime' ? 'datetime-local' : 'text'}
        value={typeof value === 'string' ? value : ''}
        placeholder={field.placeholder}
        disabled={submitted}
        onChange={(event) => setValue(field.id, event.target.value)}
      /></label>;
    })}
    <div className="clarification-actions"><Button size="small" theme="primary" disabled={!complete || submitted} onClick={submit}>{submitted ? '已填入输入框' : '填好并继续'}</Button></div>
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
  const startInputRef = useRef<HTMLInputElement>(null);
  const [subject, setSubject] = useState(String(action.payload.subject || '腾讯会议'));
  const [startTime, setStartTime] = useState(meetingInputValue(action.payload.start_time));
  const [endTime, setEndTime] = useState(meetingInputValue(action.payload.end_time));
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const warnings = action.payload.warnings || [];
  const validationErrors = action.payload.validation_errors || [];
  const result = action.result || {};

  useEffect(() => {
    setSubject(String(action.payload.subject || '腾讯会议'));
    setStartTime(meetingInputValue(action.payload.start_time));
    setEndTime(meetingInputValue(action.payload.end_time));
    setAcknowledged([]);
  }, [action.id, action.version, action.payload.subject, action.payload.start_time, action.payload.end_time]);

  const normalizedSubject = subject.trim() || '腾讯会议';
  const currentStart = meetingInputValue(action.payload.start_time);
  const currentEnd = meetingInputValue(action.payload.end_time);
  const dirty = normalizedSubject !== String(action.payload.subject || '腾讯会议')
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
      <div className="workspace-confirm-title">腾讯会议：{action.payload.subject || '未命名会议'}</div>
      <div className={`workspace-action-status status-${action.status}`}>
        {action.status === 'succeeded' ? '✓ 已创建并写入日程' : action.status === 'cancelled' ? '已取消' : action.status === 'reconciliation_required' ? `需要人工核对：${action.error || '外部结果未知'}` : action.status === 'failed' ? `失败：${action.error || '执行失败'}` : '处理中…'}
      </div>
      {typeof result.join_url === 'string' && result.join_url && <a href={result.join_url} target="_blank" rel="noreferrer">加入腾讯会议</a>}
      {typeof result.trace_id === 'string' && result.trace_id && <div className="workspace-confirm-meta">追踪号：{result.trace_id}</div>}
    </div>;
  }

  return <div className="workspace-confirm-card meeting-confirm-card">
    <div className="workspace-confirm-title">创建腾讯会议</div>
    <p className="meeting-confirm-help">请逐项检查或修改；信息不足时无需在聊天里反复回答。</p>
    <label>会议主题<input value={subject} maxLength={120} onInput={(event) => setSubject(event.currentTarget.value)} /></label>
    <div className="meeting-confirm-times">
      <label>开始时间<input ref={startInputRef} type="datetime-local" value={startTime} onInput={(event) => setStartTime(event.currentTarget.value)} /></label>
      <label>结束时间<input type="datetime-local" value={endTime} onInput={(event) => setEndTime(event.currentTarget.value)} /></label>
    </div>
    {validationErrors.map((message) => <div key={message} className="meeting-confirm-error">{message}</div>)}
    {!startTime && <div className="meeting-confirm-error">请选择开始时间</div>}
    {!endTime && <div className="meeting-confirm-error">请选择结束时间</div>}
    {startTime && endTime && !timesComplete && <div className="meeting-confirm-error">结束时间必须晚于开始时间</div>}
    {(!startTime || !endTime) && <div className="meeting-quick-actions">
      <span>快捷补全：</span>
      <Button size="small" variant="text" disabled={busy} onClick={useSuggestedTime}>下一个整点开始，时长 1 小时</Button>
      {startTime && !endTime && <Button size="small" variant="text" disabled={busy} onClick={useOneHourDuration}>从开始时间起 1 小时</Button>}
    </div>}
    {!needsValidation && warnings.map((warning) => <label key={warning} className="meeting-warning-choice">
      <input
        type="checkbox"
        checked={acknowledged.includes(warning)}
        onChange={(event) => setAcknowledged((items) => event.target.checked ? [...items, warning] : items.filter((item) => item !== warning))}
      />
      <span><b>日程提醒</b>{warning}<small>勾选后表示已了解该冲突，仍可继续创建。</small></span>
    </label>)}
    {!needsValidation && warnings.length > 1 && !warningsAccepted && <Button
      size="small"
      variant="text"
      disabled={busy}
      onClick={() => setAcknowledged([...warnings])}
    >接受全部 {warnings.length} 项冲突提醒</Button>}
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
      >保存并检查冲突</Button> : <>
        {warnings.length > 0 && <Button size="small" variant="outline" disabled={busy} onClick={() => startInputRef.current?.focus()}>修改时间</Button>}
        <Button
          size="small"
          theme="primary"
          loading={busy}
          disabled={!timesComplete || !warningsAccepted}
          onClick={() => void onConfirm()}
        >{warnings.length ? '接受已勾选冲突并创建' : '创建腾讯会议'}</Button>
      </>}
      <Button size="small" variant="outline" disabled={busy} onClick={() => void onCancel()}>取消</Button>
    </div>
  </div>;
}

function ImageCreationProgress({ message }: { message: ChatMessage }) {
  const reference = message.searchResults?.media?.[0];
  const [step, setStep] = useState(0);
  const steps = reference?.alt
    ? [`正在参考“${reference.alt.slice(0, 28)}${reference.alt.length > 28 ? '…' : ''}”的真实特征`, '正在重新组织卡通构图与神态', '正在细化线条、色彩和光影', '画面正在逐层显影']
    : ['正在理解画面中的主体与氛围', '正在搭建构图与视觉层次', '正在细化线条、色彩和光影', '画面正在逐层显影'];
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
          <small>图片工坊正在绘制，请稍候</small>
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
      MessagePlugin.error(error instanceof Error ? error.message : '主动服务操作失败');
    } finally { setProactiveBusy(''); }
  };

  const applyProactiveSuggestion = async (item: ProactiveNotification) => {
    setProactiveBusy(`read:${item.id}`);
    try {
      const documentContext = await loadProactiveDocumentContext(item);
      dispatch({ type: 'SET_DOCUMENT_CONTEXT', payload: documentContext });
      dispatch({ type: 'SET_DRAFT', payload: item.action_prompt || `请帮我处理：${item.title}` });
      const next = await proactiveOperation(conversationId, 'mark_read', { notification_id: item.id });
      dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '无法准备主动建议');
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

  // 兼容：从 skill 或旧字段获取意图
  const skill: SkillInfo | undefined = message.skill;
  const intent = skill?.intent
    || (message.travelIntent ? 'travel' : undefined)
    || (message.meetingIntent ? 'meeting' : undefined);

  const handleFollowUp = (question: string) => {
    // Suggestions are editable prompts, not commands. The user must still
    // explicitly press Send before any message is persisted or reaches Agent.
    dispatch(followUpDraftAction(question));
  };

  const copyAnswerText = async () => {
    const plainText = markdownToPlainText(message.content, message.searchResults?.results || []);
    if (!plainText) {
      MessagePlugin.warning('当前回答没有可复制的纯文字内容');
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
      MessagePlugin.success('已复制纯文字回答');
    } catch {
      MessagePlugin.error('浏览器不允许自动复制，请手动选择文字复制');
    }
  };

  const saveAnswerImage = async () => {
    if (!bubbleRef.current || answerSaving) return;
    setAnswerSaving(true);
    try {
      await saveElementAsImage(bubbleRef.current);
      MessagePlugin.success('回答图片已保存');
    } catch {
      MessagePlugin.error('回答图片保存失败，请稍后重试');
    } finally {
      setAnswerSaving(false);
    }
  };

  const retryFailedAnswer = async () => {
    if (!previousUserMessage || retryingAnswer || messages.some((item) => item.streaming)) return;
    if (!client.current) {
      dispatch({ type: 'SET_DRAFT', payload: previousUserMessage.content });
      MessagePlugin.warning('连接尚未就绪，原问题已放回输入框');
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
          web_search: true,
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
      throw new Error('该建议卡缺少后端 Action 快照，请重新发送需求');
    }
    const response = await workspaceOperation(conversationId, 'confirm_action', {
      action_id: actionId,
      version: actionVersion,
    });
    if (!response.action) throw new Error('Makers Workspace 未返回操作结果');
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
    setMeetingStatusText('已确认，等待后台 Executor...');
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
        MessagePlugin.success('腾讯会议创建成功！');
      } else {
        const error = action.error || '创建失败';
        setMeetingResult({ ok: false, error });
        MessagePlugin.warning(error);
      }
    } catch (error) {
      const text = error instanceof Error ? error.message : '创建会议失败';
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
        MessagePlugin.success('图片生成成功！');
      } else {
        const error = action.error || '生成失败';
        setImageResult({ ok: false, error });
        MessagePlugin.warning(error);
      }
    } catch (error) {
      const text = error instanceof Error ? error.message : '生图失败';
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
      MessagePlugin.success('已取消该操作');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '取消失败');
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
        MessagePlugin.success('已在右侧地图显示这些地点');
      } else if (operation === 'activate_map') {
        if (!mapSnapshot.length) throw new Error('地点数据暂时不可用，请重新生成地点推荐');
        MessagePlugin.warning('已显示已核实地点，但本次激活状态未保存');
      }
      if (operation === 'update_meeting_action') MessagePlugin.success('会议信息已检查，请确认后创建');
      if (operation === 'confirm_action' && action.kind === 'calendar_changes') {
        dispatch({ type: 'SET_SCHEDULES', payload: response.schedules || [] });
        const changed = response.changed?.filter((item) => !item.deleted) || [];
        if (changed.length) {
          const first = new Date(changed[0].start_time * 1000);
          const date = [first.getFullYear(), String(first.getMonth() + 1).padStart(2, '0'), String(first.getDate()).padStart(2, '0')].join('-');
          dispatch({ type: 'PULSE_CALENDAR', payload: { date, count: changed.length } });
        }
        MessagePlugin.success('日程变更已确认并写入');
      }
      if (operation === 'confirm_action' && action.kind === 'meeting_create') {
        const result = response.action?.result || {};
        if (response.action?.status === 'succeeded') MessagePlugin.success('腾讯会议创建成功');
        else MessagePlugin.warning(String(response.action?.error || result.error || '会议创建失败'));
      }
      if (operation === 'confirm_action' && action.kind === 'image_generate') {
        if (response.action?.status === 'succeeded') {
          ingestGeneratedImage(response.action);
          MessagePlugin.success('图片生成成功');
        }
        else MessagePlugin.warning(String(response.action?.error || '图片生成失败'));
      }
      if (operation === 'cancel_action') MessagePlugin.success('已取消该操作');
    } catch (error) {
      const text = error instanceof Error ? error.message : '操作失败';
      if (operation === 'activate_map' && mapSnapshot.length) {
        MessagePlugin.warning(`已用核实快照显示地点；激活状态暂未保存：${text}`);
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
        handleFollowUp(compatSkill?.content || '请继续帮我规划这次旅行，并在需要时询问缺少的信息');
        MessagePlugin.info('旅行需求已填入输入框；发送后由 Makers Agent 继续规划');
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
        MessagePlugin.info(`${skill?.action_label || '执行'}功能开发中，敬请期待`);
        setSkillActioned(false);
        break;
      default:
        break;
    }
  };

  // 兼容旧消息（有 travelIntent/meetingIntent 但没有 skill）
  const compatSkill: SkillInfo | undefined = skill || (intent ? {
    intent,
    mode: intent === 'travel' ? 'auto' : 'suggest',
    content: message.travelIntent?.prompt || message.meetingIntent?.prompt || message.content,
    icon: intent === 'travel' ? '✈️' : intent === 'meeting' ? '📅' : '✨',
    action_label: intent === 'travel' ? '规划行程' : intent === 'meeting' ? '创建腾讯会议' : '执行',
    params: {
      user_message: message.travelIntent?.user_message,
      message: message.meetingIntent?.message,
      destination: message.travelIntent?.destination,
    },
    data: {},
  } : undefined);

  const searchStatus = typeof message.skill?.data?.statusText === 'string'
    ? message.skill.data.statusText
    : '正在理解你想解决的问题…';
  const progressStatus = message.content
    ? (message.skill?.intent === 'search'
      ? (message.searchResults?.media_pending
        ? '正在边写边核对图片和出处…'
        : '正在把核实后的信息整理成回答…')
      : '正在逐步组织回答…')
    : searchStatus;
  const markdownRender = {
    content: message.streaming ? streamingMarkdownAnswer(message.content) : message.content,
    searchMeta: message.searchResults,
    streaming: Boolean(message.streaming),
  };
  return (
    <div className={`msg-row ${isUser ? 'user' : 'ai'}`}>
      <div className={`msg-avatar ${isUser ? 'user' : 'ai'}`}>
        {isUser ? '我' : <img src="/floris-avatar.png" alt="Floris" />}
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
              {message.clarification && <ClarificationCard clarification={message.clarification} />}
              {message.proactive && proactive && <div className="proactive-conversation-actions">
                {(proactive.notifications || []).filter((item) => item.status !== 'dismissed').slice(0, 3).map((item) => <div className="proactive-conversation-item" key={item.id}>
                  <span>{item.title}</span>
                  <div>
                    <Button size="small" variant="text" loading={proactiveBusy === `read:${item.id}`} onClick={() => { void applyProactiveSuggestion(item); }}>帮我处理</Button>
                    <Button size="small" variant="text" loading={proactiveBusy === `snooze:${item.id}`} onClick={() => void mutateProactive(`snooze:${item.id}`, 'snooze', { notification_id: item.id, until: Math.floor(Date.now() / 1000) + 3600 })}>1 小时后提醒</Button>
                    <Button size="small" variant="text" loading={proactiveBusy === `dismiss:${item.id}`} onClick={() => void mutateProactive(`dismiss:${item.id}`, 'dismiss', { notification_id: item.id })}>忽略</Button>
                  </div>
                </div>)}
                {(proactive.workflows || []).filter((item) => item.status === 'awaiting_confirmation').map((workflow) => <div className="proactive-conversation-item" key={workflow.id}>
                  <span>持续任务：{workflow.title}</span><small>{workflow.reason}</small>
                  <div>
                    <Button size="small" theme="primary" loading={proactiveBusy === `workflow:${workflow.id}`} onClick={() => void mutateProactive(`workflow:${workflow.id}`, 'confirm_workflow', { workflow_id: workflow.id, version: workflow.version })}>确认启用</Button>
                    <Button size="small" variant="text" onClick={() => void mutateProactive(`workflow:${workflow.id}`, 'reject_workflow', { workflow_id: workflow.id, version: workflow.version })}>暂不启用</Button>
                  </div>
                </div>)}
                {(proactive.workflows || []).filter((item) => item.status === 'active').map((workflow) => {
                  const step = workflow.steps.find((item) => !['completed', 'skipped', 'compensated'].includes(item.status));
                  return <div className="proactive-conversation-item" key={workflow.id}>
                    <span>进行中的持续任务：{workflow.title}</span>
                    <small>{step ? `当前步骤：${step.title}` : '所有步骤已处理，等待状态同步'}</small>
                    <div>
                      {step && ['pending', 'notified'].includes(step.status) && <>
                        <Button size="small" theme="success" loading={proactiveBusy === `complete:${step.id}`} onClick={() => void mutateProactive(`complete:${step.id}`, 'complete_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>完成步骤</Button>
                        <Button size="small" variant="text" loading={proactiveBusy === `skip:${step.id}`} onClick={() => void mutateProactive(`skip:${step.id}`, 'skip_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>跳过步骤</Button>
                        <Button size="small" variant="text" loading={proactiveBusy === `fail:${step.id}`} onClick={() => void mutateProactive(`fail:${step.id}`, 'fail_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>标记失败</Button>
                      </>}
                      {step?.status === 'compensating' && <Button size="small" theme="success" loading={proactiveBusy === `compensate:${step.id}`} onClick={() => void mutateProactive(`compensate:${step.id}`, 'compensate_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>补偿已完成</Button>}
                      {step && ['failed', 'attention_required'].includes(step.status) && <Button size="small" variant="outline" loading={proactiveBusy === `retry:${step.id}`} onClick={() => void mutateProactive(`retry:${step.id}`, 'retry_workflow_step', { workflow_id: workflow.id, step_id: step.id })}>重试步骤</Button>}
                      <Button size="small" variant="text" loading={proactiveBusy === `cancel:${workflow.id}`} onClick={() => void mutateProactive(`cancel:${workflow.id}`, 'cancel_workflow', { workflow_id: workflow.id, version: workflow.version })}>停止工作流</Button>
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
                  {retryingAnswer ? '正在重试…' : '重试生成'}
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
                      {busy ? '正在打开地图…' : action.payload.action_text || '在右侧地图查看这些地点'}
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
                  ? action.payload.summary || '是否应用这组日程变更？'
                  : `生成图片：${action.payload.prompt || ''}`;
                const result = action.result || {};
                return (
                  <div key={action.id} className="workspace-confirm-card">
                    <div className="workspace-confirm-title">{title}</div>
                    {action.payload.warnings?.map((warning) => (
                      <div key={warning} className="workspace-confirm-warning">⚠ {warning}，请确认是否仍要继续</div>
                    ))}
                    {action.status === 'awaiting_confirmation' ? (
                      <div className="workspace-confirm-actions">
                        <Button size="small" theme="primary" loading={busy} onClick={() => void handleWorkspaceAction(action, 'confirm_action')}>确认</Button>
                        <Button size="small" variant="outline" disabled={busy} onClick={() => void handleWorkspaceAction(action, 'cancel_action')}>取消</Button>
                      </div>
                    ) : (
                      <div className={`workspace-action-status status-${action.status}`}>
                        {action.status === 'succeeded' ? '✓ 已完成' : action.status === 'cancelled' ? '已取消' : action.status === 'reconciliation_required' ? `需要人工核对：${action.error || '外部结果未知'}` : action.status === 'failed' ? `失败：${action.error || '执行失败'}` : '处理中…'}
                      </div>
                    )}
                    {typeof result.join_url === 'string' && result.join_url && <a href={result.join_url} target="_blank" rel="noreferrer">加入腾讯会议</a>}
                    {typeof result.trace_id === 'string' && result.trace_id && <div className="workspace-confirm-meta">追踪号：{result.trace_id}</div>}
                    {typeof result.image_url === 'string' && result.image_url && <img className="workspace-generated-image" src={result.image_url} alt={String(action.payload.prompt || '生成图片')} />}
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
                ✅ 会议已创建：{meetingResult.subject}
              </div>
              {meetingResult.meeting_code && (
                <div style={{ fontSize: 13, color: 'var(--app-text-2)' }}>
                  会议号：{meetingResult.meeting_code}
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
                  开始时间：{meetingResult.start_time}
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
                <span style={{ fontWeight: 600, fontSize: 14 }}>创建失败</span>
              </div>
              <div className="travel-intent-text">
                <span className="travel-intent-icon">⚠️</span>
                <span style={{ fontSize: 13 }}>{meetingResult.error}</span>
              </div>
            </div>
          </div>
        )}

        {/* === 通用技能建议卡片（suggest 模式 + 未执行） === */}
        {!isUser && compatSkill && compatSkill.mode !== 'immediate' && !travelPlan && !meetingResult && !imageResult && !skillActioned && (
          <div className="followup-section">
            <div className="travel-intent-card">
              <div className="travel-intent-text">
                <span className="travel-intent-icon">{compatSkill.icon}</span>
                {compatSkill.content}
              </div>
              <Button
                theme="primary"
                size="small"
                loading={(meetingCreating && intent === 'meeting') || (imageGenerating && intent === 'image')}
                onClick={handleSkillAction}
              >
                {(meetingCreating && intent === 'meeting')
                  ? (meetingStatusText || '处理中...')
                  : (imageGenerating && intent === 'image')
                  ? '生成中...'
                  : compatSkill.action_label}
              </Button>
              {actionId && (intent === 'meeting' || intent === 'image') && (
                <Button variant="outline" size="small" onClick={() => { void handleCancelAction(); }}>
                  取消
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
                alt={imageResult.prompt || '生成的图片'}
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
            fileName={message.paperFileName || 'PDF 文档'}
            title={message.paperTitle || message.paperFileName || 'PDF 阅读'}
            assistantEnabled={message.paperIsPaper ?? message.content.includes('已识别为论文')}
          />
        )}

        {/* 搜索结果不再单独展示卡片，已由 AI 自然穿插在 Markdown 回答中 */}

        {/* === 追问建议（只在最后一条 AI 消息显示） === */}
        {!isUser && !message.streaming && isLastAIMessage && message.followUps && message.followUps.length > 0 && (
          <div className="followup-section answer-followups" style={followUpWidth ? { width: followUpWidth } : undefined}>
            <div className="followup-label">猜你想继续问</div>
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

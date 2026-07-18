import { useEffect, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ChatMessage, TravelPlan, SkillInfo, MeetingResult, ScheduleItem, WorkspaceAction } from '../../types';
import type { ChatClient } from '../../services/chatClient';
import { workspaceOperation } from '../../services/api';
import TravelPlanCard from '../travel/TravelPlanCard';
import PaperListCard from '../paper/PaperListCard';
import PaperInlineReader from '../paper/PaperInlineReader';
import ImageStudioCard from '../image/ImageStudioCard';
import MarkdownRenderer from '../common/MarkdownRenderer';
import { followUpDraftAction } from './followUps';

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
      <div className="image-painting-overlay"><span /></div>
    </div>
    <strong>{steps[step]}</strong><small>图片工坊正在绘制，请稍候</small>
  </div>;
}
/** 单条消息气泡。AI 消息下方根据 skill.intent 渲染不同卡片。 */
export default function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';
  const dispatch = useAppDispatch();
  const { conversationId, messages } = useAppState();
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

  // Tool actions arrive after the streaming message bubble has mounted. Keep
  // the local interactive copy in sync instead of freezing the initial empty
  // array for the lifetime of the bubble.
  useEffect(() => {
    setWorkspaceActions(consolidateActions(message.workspaceActions || []));
  }, [message.workspaceActions]);

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

  const handleWorkspaceAction = async (action: WorkspaceAction, operation: 'activate_map' | 'confirm_action' | 'cancel_action') => {
    setWorkspaceBusy(action.id);
    try {
      const response = await workspaceOperation(conversationId, operation, {
        action_id: action.id,
        version: action.version,
      });
      if (response.action) replaceWorkspaceAction(response.action);
      if (operation === 'activate_map' && response.map?.places?.length) {
        dispatch({ type: 'SET_MAP_PLACES', payload: { places: response.map.places, title: response.map.title } });
        MessagePlugin.success('已在右侧地图显示这些地点');
      }
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
        if (response.action?.status === 'succeeded') MessagePlugin.success('图片生成成功');
        else MessagePlugin.warning(String(response.action?.error || '图片生成失败'));
      }
      if (operation === 'cancel_action') MessagePlugin.success('已取消该操作');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '操作失败');
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
    : '正在搜索';
  const progressStatus = message.content && searchStatus === '思考中…' ? '正在继续生成回答…' : searchStatus;
  return (
    <div className={`msg-row ${isUser ? 'user' : 'ai'}`}>
      <div className={`msg-avatar ${isUser ? 'user' : 'ai'}`}>{isUser ? '我' : 'AI'}</div>
      <div className="msg-content-wrap">
        <div className={`msg-bubble ${isUser ? 'user' : 'ai'} ${message.failed ? 'is-error' : ''}`}>
          {isUser ? (
            message.content
          ) : (
            <>
              {/* 搜索动画 */}
              {!isUser && message.streaming && (
                message.skill?.intent === 'image' || progressStatus.includes('生成图片') || progressStatus.includes('绘制') ? <ImageCreationProgress message={message} /> : <div className={`search-progress ${message.content ? 'has-content' : ''}`}>
                  <div className="image-generating-spinner" />
                  <span className="search-progress-status" title={progressStatus}>{progressStatus}</span>
                  <span className="image-generating-dots"><span>.</span><span>.</span><span>.</span></span>
                </div>
              )}
              {message.content && <MarkdownRenderer content={message.content} searchMeta={message.searchResults} />}
              {message.failed && previousUserMessage && (
                <button
                  type="button"
                  className="chat-retry-button"
                  onClick={() => {
                    dispatch({ type: 'SET_DRAFT', payload: previousUserMessage.content });
                    MessagePlugin.info('原问题已放回输入框，确认后可重新发送');
                  }}
                >
                  重新编辑原问题
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
                const title = action.kind === 'calendar_changes'
                  ? action.payload.summary || '是否应用这组日程变更？'
                  : action.kind === 'meeting_create'
                    ? `创建腾讯会议：${action.payload.subject || '未命名会议'}`
                    : `生成图片：${action.payload.prompt || ''}`;
                const result = action.result || {};
                return (
                  <div key={action.id} className="workspace-confirm-card">
                    <div className="workspace-confirm-title">{title}</div>
                    {action.kind === 'meeting_create' && action.payload.start_time && (
                      <div className="workspace-confirm-meta">{new Date(action.payload.start_time).toLocaleString('zh-CN')}</div>
                    )}
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
            <div style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--app-border)', maxWidth: 280 }}>
              <img
                src={imageResult.image_url}
                alt={imageResult.prompt || '生成的图片'}
                style={{ width: '100%', maxHeight: 280, objectFit: 'contain', display: 'block' }}
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
            messageId={message.id}
          />
        )}

        {/* 搜索结果不再单独展示卡片，已由 AI 自然穿插在 Markdown 回答中 */}

        {/* === 追问建议（只在最后一条 AI 消息显示） === */}
        {!isUser && isLastAIMessage && message.followUps && message.followUps.length > 0 && (
          <div className="followup-section">
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

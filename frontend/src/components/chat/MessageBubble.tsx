import { useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ChatMessage, TravelPlan, WSMessage, SkillInfo, MeetingResult, ScheduleItem } from '../../types';
import type { WSClient } from '../../services/websocket';
import { cancelPendingAction, confirmPendingAction, saveConversationMessage, waitForPendingAction } from '../../services/api';
import TravelPlanCard from '../travel/TravelPlanCard';
import TravelChatAssistant from '../travel/TravelChatAssistant';
import PaperListCard from '../paper/PaperListCard';
import MarkdownRenderer from '../common/MarkdownRenderer';

interface Props {
  message: ChatMessage;
  client: React.RefObject<WSClient | null>;
}
/** 单条消息气泡。AI 消息下方根据 skill.intent 渲染不同卡片。 */
export default function MessageBubble({ message, client }: Props) {
  const isUser = message.role === 'user';
  const dispatch = useAppDispatch();
  const { conversationId, messages } = useAppState();
  // 追问只在最后一条 AI 消息显示
  const isLastAIMessage = !isUser && messages[messages.length - 1]?.id === message.id;

  // 旅游状态
  const [travelPlan, setTravelPlan] = useState<TravelPlan | null>(message.travelPlanData || null);
  const [travelStartTs] = useState<number | undefined>(message.travelStartTs);
  const [parsedSchedules] = useState<Partial<ScheduleItem>[]>(message.parsedSchedules || []);
  const [showTravelAssistant, setShowTravelAssistant] = useState(
    message.autoShowTravelAssistant || message.skill?.intent === 'travel'
  );
  const [assistantCompleted, setAssistantCompleted] = useState(false);

  // 会议状态
  const [meetingCreating, setMeetingCreating] = useState(false);
  const [meetingResult, setMeetingResult] = useState<MeetingResult | null>(null);
  const [meetingStatusText, setMeetingStatusText] = useState('');

  // 通用技能执行状态
  const [skillActioned, setSkillActioned] = useState(false);

  // 兼容：从 skill 或旧字段获取意图
  const skill: SkillInfo | undefined = message.skill;
  const intent = skill?.intent
    || (message.travelIntent ? 'travel' : undefined)
    || (message.meetingIntent ? 'meeting' : undefined);

  const handleFollowUp = async (question: string) => {
    const followUpMessage = { id: Date.now().toString(), role: 'user' as const, content: question, ts: Date.now() };
    try {
      await saveConversationMessage(conversationId, followUpMessage);
      dispatch({ type: 'ADD_MESSAGE', payload: followUpMessage });
      const msg: WSMessage = {
        type: 'user_activity',
        payload: { activity: 'asked', text: question, message_id: followUpMessage.id },
      };
      client.current?.send(msg);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '消息保存失败');
    }
  };

  const handleTravelPlanComplete = (plan: TravelPlan, startTs?: number, parsed?: Partial<ScheduleItem>[]) => {
    setShowTravelAssistant(false);
    setAssistantCompleted(true);
    dispatch({
      type: 'ADD_MESSAGE',
      payload: {
        id: 'ai-travel-' + Date.now(),
        role: 'ai',
        content: '为你生成了以下旅游行程，确认无误可以写入我的日程：',
        ts: Date.now(),
        travelPlanData: plan,
        travelStartTs: startTs,
        parsedSchedules: parsed || [],
      },
    });
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
    await confirmPendingAction(actionId, actionVersion);
    return waitForPendingAction(actionId);
  };

  const handleCreateMeeting = async () => {
    setMeetingCreating(true);
    setMeetingStatusText('已确认，等待后台 Executor...');
    try {
      const action = await executeConfirmedAction();
      const data = action.result_json?.data || {};
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
        setMeetingResult({ ok: false, error, need_auth: error.includes('授权') });
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
      const data = action.result_json?.data || {};
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
      await cancelPendingAction(actionId);
      setSkillActioned(true);
      MessagePlugin.success('已取消该操作');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '取消失败');
    }
  };


  /** 通用技能动作处理 */
  const handleSkillAction = () => {
    if (!intent) return;
    setSkillActioned(true);

    switch (intent) {
      case 'travel':
        setShowTravelAssistant(true);
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
  const dataDestination = typeof compatSkill?.data?.destination === 'string'
    ? compatSkill.data.destination
    : undefined;

  return (
    <div className={`msg-row ${isUser ? 'user' : 'ai'}`}>
      <div className={`msg-avatar ${isUser ? 'user' : 'ai'}`}>{isUser ? '我' : 'AI'}</div>
      <div className="msg-content-wrap">
        <div className={`msg-bubble ${isUser ? 'user' : 'ai'}`}>
          {isUser ? (
            message.content
          ) : (
            <>
              {/* 生图动画：内容为空且正在流式 */}
              {!isUser && intent === 'image' && message.streaming && !message.content && (
                <div className="image-generating-anim">
                  <div className="image-generating-spinner" />
                  <span>正在生成图片</span>
                  <span className="image-generating-dots">
                    <span>.</span><span>.</span><span>.</span>
                  </span>
                </div>
              )}
              {/* 搜索动画：内容为空且正在搜索 */}
              {!isUser && intent === 'search' && message.streaming && !message.content && (
                <div className="image-generating-anim">
                  <div className="image-generating-spinner" />
                  <span>{searchStatus}</span>
                  <span className="image-generating-dots">
                    <span>.</span><span>.</span><span>.</span>
                  </span>
                </div>
              )}
              {/* 搜索来源列表（回答顶部，可展开） */}
              {!isUser && message.searchResults && message.searchResults.total > 0 && (
                <div className="search-sources-bar">
                  <details>
                    <summary className="search-sources-label">
                      已搜索 {message.searchResults.total} 个来源
                      <span className="search-sources-types">
                        {Array.from(new Set(message.searchResults.results.map(r => r.source))).map(s => {
                          const labels: Record<string, string> = { wechat: '公众号', zhihu: '知乎', baike: '百科', web: '网页', wsa: '联网' };
                          return <span key={s} className="search-source-type">{labels[s] || s}</span>;
                        })}
                      </span>
                    </summary>
                    <div className="search-sources-list">
                      {message.searchResults.results.map((r, i) => {
                        const labels: Record<string, string> = { wechat: '公众号', zhihu: '知乎', baike: '百科', web: '网页', wsa: '联网' };
                        const typeLabel = labels[r.source] || '网页';
                        const displayTitle = r.title || r.url || '';
                        return (
                          <a
                            key={i}
                            href={r.url}
                            target="_blank"
                            rel="noreferrer"
                            className="search-source-chip"
                          >
                            <span className="search-source-type">{typeLabel}</span>
                            <span className="search-source-title">{displayTitle.length > 30 ? displayTitle.slice(0, 30) + '…' : displayTitle}</span>
                          </a>
                        );
                      })}
                    </div>
                  </details>
                </div>
              )}
              {message.content && <MarkdownRenderer content={message.content} />}
              {message.streaming && message.content && (
                <span className="typing-cursor">▊</span>
              )}
            </>
          )}
        </div>

        {/* === 旅游：对话式助手 === */}
        {!isUser && intent === 'travel' && showTravelAssistant && (
          <div className="travel-chat-wrapper">
            <TravelChatAssistant
              initialDestination={
                compatSkill?.params?.destination ||
                compatSkill?.params?.user_message ||
                dataDestination
              }
              userMessage={compatSkill?.params?.user_message || compatSkill?.params?.message}
              onComplete={handleTravelPlanComplete}
              onCancel={() => setShowTravelAssistant(false)}
            />
          </div>
        )}

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
                borderColor: meetingResult.need_auth ? '#2b5aed' : 'var(--td-warning-color)',
                background: meetingResult.need_auth
                  ? 'linear-gradient(135deg, rgba(43,90,237,0.04), rgba(124,92,255,0.04))'
                  : undefined,
              }}
            >
              {/* 标题行 */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 20 }}>
                  {meetingResult.need_auth ? '🔐' : '⚠️'}
                </span>
                <span style={{ fontWeight: 600, fontSize: 14 }}>
                  {meetingResult.need_auth ? '需要授权腾讯会议' : '创建失败'}
                </span>
              </div>

              {/* 需要授权 */}
              {meetingResult.need_auth ? (
                <>
                  <div style={{ fontSize: 13, color: 'var(--app-text-2)', lineHeight: 1.7 }}>
                    创建腾讯会议需要先完成一次授权（仅一次，之后永久生效）：
                  </div>

                  {/* 步骤引导 */}
                  <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{
                      display: 'flex', alignItems: 'center', gap: 10,
                      padding: '10px 12px',
                      background: 'var(--app-bg)',
                      borderRadius: 8,
                      border: '1px solid var(--app-border)',
                    }}>
                      <span style={{
                        width: 22, height: 22, borderRadius: '50%',
                        background: '#2b5aed', color: '#fff',
                        fontSize: 12, fontWeight: 700,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>1</span>
                      <code style={{
                        fontSize: 12.5,
                        fontFamily: 'ui-monospace, monospace',
                        background: 'rgba(43,90,237,0.08)',
                        padding: '4px 10px',
                        borderRadius: 6,
                        color: '#2b5aed',
                        flex: 1,
                      }}>
                        tmeet auth login
                      </code>
                      <button
                        onClick={() => {
                          navigator.clipboard?.writeText('tmeet auth login');
                          MessagePlugin.success('已复制');
                        }}
                        style={{
                          border: 'none', background: 'none', cursor: 'pointer',
                          fontSize: 12, color: 'var(--app-text-3)', padding: '4px 8px',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        📋 复制
                      </button>
                    </div>

                    <div style={{
                      display: 'flex', alignItems: 'flex-start', gap: 10,
                      padding: '10px 12px',
                      background: 'var(--app-bg)',
                      borderRadius: 8,
                      border: '1px solid var(--app-border)',
                    }}>
                      <span style={{
                        width: 22, height: 22, borderRadius: '50%',
                        background: '#2b5aed', color: '#fff',
                        fontSize: 12, fontWeight: 700,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>2</span>
                      <span style={{ fontSize: 12.5, color: 'var(--app-text-2)', lineHeight: 1.6, paddingTop: 2 }}>
                        浏览器会自动弹出扫码页面，用<span style={{ color: '#2b5aed', fontWeight: 600 }}>&nbsp;腾讯会议 APP&nbsp;</span>扫码授权
                      </span>
                    </div>

                    <div style={{
                      display: 'flex', alignItems: 'flex-start', gap: 10,
                      padding: '10px 12px',
                      background: 'var(--app-bg)',
                      borderRadius: 8,
                      border: '1px solid var(--app-border)',
                    }}>
                      <span style={{
                        width: 22, height: 22, borderRadius: '50%',
                        background: '#00a870', color: '#fff',
                        fontSize: 12, fontWeight: 700,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}>✓</span>
                      <span style={{ fontSize: 12.5, color: 'var(--app-text-2)', lineHeight: 1.6, paddingTop: 2 }}>
                        授权完成后，回来点击下方按钮即可创建会议
                      </span>
                    </div>
                  </div>

                  {/* 重试按钮 */}
                  <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <Button
                      theme="primary"
                      size="small"
                      onClick={() => {
                        setMeetingResult(null);
                        handleCreateMeeting();
                      }}
                    >
                      🔑 已授权，重新创建
                    </Button>
                  </div>
                </>
              ) : (
                /* 其他错误 */
                <div className="travel-intent-text">
                  <span className="travel-intent-icon">⚠️</span>
                  <span style={{ fontSize: 13 }}>{meetingResult.error}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* === 通用技能建议卡片（suggest 模式 + 未执行） === */}
        {!isUser && compatSkill && compatSkill.mode !== 'immediate' && !showTravelAssistant && !travelPlan && !assistantCompleted && !meetingResult && !imageResult && !skillActioned && (
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
        {!isUser && intent === 'image' && imageResult && imageResult.ok && imageResult.image_url && (
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

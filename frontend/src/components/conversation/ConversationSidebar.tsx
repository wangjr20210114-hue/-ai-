import { useCallback, useEffect, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { createNewConversation, listConversations } from '../../services/api';
import { canReusePendingConversation, setActiveConversationId } from '../../services/conversation';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ConversationSummary } from '../../types';
import { formatConversationTime } from '../../services/time';
import ProactiveBriefPanel from '../profile/ProactiveBriefPanel';
import AgentIntelligencePanel from '../profile/AgentIntelligencePanel';
import LibrarySettingsButton from '../profile/LibrarySettingsButton';

interface Props {
  open: boolean;
  onClose: () => void;
}

function pendingConversation(conversationId: string): ConversationSummary {
  const now = Date.now();
  return {
    id: conversationId,
    title: '新对话',
    createdAt: now,
    updatedAt: now,
    messageCount: 0,
    pending: true,
  };
}

export default function ConversationSidebar({ open, onClose }: Props) {
  const { conversationId, conversations, messages } = useAppState();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState('');

  const load = useCallback(async () => {
    setLoadError('');
    try {
      const stored = await listConversations();
      // Makers conversation indexing is eventually consistent. Preserve all
      // locally known conversations until the remote list catches up instead
      // of relabeling a real conversation as a new empty one.
      const remoteWithActivity = stored.map((remote) => {
        const local = conversations.find((item) => item.id === remote.id);
        return remote.activityStatus ? remote : (local?.activityStatus ? { ...remote, activityStatus: local.activityStatus } : remote);
      });
      const localMissing = conversations.filter((item) => !remoteWithActivity.some((remote) => remote.id === item.id));
      const activeFallback = remoteWithActivity.some((item) => item.id === conversationId) || localMissing.some((item) => item.id === conversationId)
        ? []
        : [{ ...pendingConversation(conversationId), messageCount: 0 }];
      const withCurrent = [...remoteWithActivity, ...localMissing, ...activeFallback]
        .sort((a, b) => b.updatedAt - a.updatedAt);
      dispatch({ type: 'SET_CONVERSATIONS', payload: withCurrent });
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : '读取历史对话失败');
      if (!conversations.some((item) => item.id === conversationId)) {
        dispatch({ type: 'UPSERT_CONVERSATION', payload: pendingConversation(conversationId) });
      }
    } finally {
      setLoading(false);
    }
  }, [conversationId, conversations, dispatch]);

  useEffect(() => {
    void load();
    // Conversation updates are handled by the explicit save event below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  useEffect(() => {
    let timer = 0;
    const handleSaved = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => { void load(); }, 120);
    };
    window.addEventListener('yuanbao:conversation-saved', handleSaved);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('yuanbao:conversation-saved', handleSaved);
    };
  }, [load]);

  const activate = async (id: string) => {
    if (id === conversationId) {
      onClose();
      return;
    }
    setActiveConversationId(id);
    dispatch({ type: 'SET_CONVERSATION_ID', payload: id });
    onClose();
  };

  const create = async () => {
    if (creating) return;
    const reusable = conversations.find((item) => (
      canReusePendingConversation(item, conversationId, messages)
    ));
    if (reusable) {
      if (reusable.id !== conversationId) {
        setActiveConversationId(reusable.id);
        dispatch({ type: 'SET_CONVERSATION_ID', payload: reusable.id });
      }
      onClose();
      return;
    }
    setCreating(true);
    try {
      // Running conversations remain active in the background. The active
      // transport ref is switched without cancelling their request.
      const conversation = await createNewConversation();
      dispatch({ type: 'UPSERT_CONVERSATION', payload: conversation });
      setActiveConversationId(conversation.id);
      dispatch({ type: 'SET_CONVERSATION_ID', payload: conversation.id });
      onClose();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '新建对话失败');
    } finally { setCreating(false); }
  };

  return (
    <>
      <button
        type="button"
        className={`conversation-sidebar-backdrop ${open ? 'is-open' : ''}`}
        aria-label="关闭历史对话"
        onClick={onClose}
      />
      <aside className={`conversation-sidebar panel ${open ? 'is-open' : ''}`} aria-label="对话历史">
        <div className="conversation-sidebar-header">
          <div className="conversation-sidebar-title">对话</div>
          <button type="button" className="conversation-sidebar-close" onClick={onClose} aria-label="关闭">×</button>
        </div>

        <Button block theme="primary" loading={creating} onClick={() => { void create(); }}>
          ＋ 新建对话
        </Button>

        <div className="conversation-history-label">历史对话</div>
        <div className="conversation-list">
          {loading && conversations.length === 0 && (
            <div className="conversation-list-empty">正在读取…</div>
          )}
          {loadError && (
            <button type="button" className="conversation-list-error" onClick={() => { void load(); }}>
              {loadError}，点击重试
            </button>
          )}
          {conversations.map((conversation) => (
            <button
              type="button"
              key={conversation.id}
              className={`conversation-item ${conversation.id === conversationId ? 'is-active' : ''}`}
              onClick={() => { void activate(conversation.id); }}
              title={conversation.title}
            >
              <span className={`conversation-item-icon status-${conversation.activityStatus || 'idle'}`} aria-label={conversation.activityStatus === 'running' ? '生成中' : conversation.activityStatus === 'failed' ? '生成失败' : '空闲'}>
                {conversation.activityStatus === 'running' ? '◌' : conversation.activityStatus === 'failed' ? '!' : '◇'}
              </span>
              <span className="conversation-item-content">
                <span className="conversation-item-title">{conversation.title}</span>
                <span className="conversation-item-meta">
                  {conversation.activityStatus === 'running'
                    ? '正在生成回答…'
                    : conversation.activityStatus === 'failed'
                      ? '上次生成失败，可进入重试'
                      : conversation.pending
                    ? '尚未发送消息'
                    : `${conversation.messageCount ? `${conversation.messageCount} 条消息 · ` : ''}${formatConversationTime(conversation.updatedAt)}`}
                </span>
              </span>
            </button>
          ))}
        </div>
        <div className="conversation-sidebar-tools">
          <ProactiveBriefPanel />
          <AgentIntelligencePanel />
          <LibrarySettingsButton />
        </div>
      </aside>
    </>
  );
}

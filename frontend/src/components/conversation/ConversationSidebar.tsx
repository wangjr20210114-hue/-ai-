import { lazy, Suspense, useCallback, useEffect, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import {
  createNewConversation,
  listConversations,
} from '../../features/chat/model/client';
import { reconcileConversationSummary, setActiveConversationId } from '../../services/conversation';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ConversationSummary } from '../../shared/types';
import { formatConversationTime } from '../../services/time';
import ProactiveBriefPanel from '../../features/settings/view/ProactiveBriefPanel';
import { translate, useLanguage } from '../../i18n';

const AppSettingsButton = lazy(
  () => import('../../features/settings/view/AppSettingsButton'),
);
const SkillsMarketplaceButton = lazy(
  () => import('../../features/skills/view/SkillsMarketplaceButton'),
);
const COMPACT_SIDEBAR_QUERY = '(max-width: 860px)';

interface Props {
  open: boolean;
  onClose: () => void;
}

function pendingConversation(conversationId: string): ConversationSummary {
  const now = Date.now();
  return {
    id: conversationId,
    title: translate('newConversation'),
    createdAt: now,
    updatedAt: now,
    messageCount: 0,
    pending: true,
  };
}

export default function ConversationSidebar({ open, onClose }: Props) {
  const { conversationId, conversations } = useAppState();
  const { t } = useLanguage();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [toolsLoaded, setToolsLoaded] = useState(
    () => !window.matchMedia(COMPACT_SIDEBAR_QUERY).matches,
  );

  useEffect(() => {
    if (open) setToolsLoaded(true);
  }, [open]);

  const load = useCallback(async () => {
    setLoadError('');
    try {
      const stored = await listConversations();
      // Makers conversation indexing is eventually consistent. Preserve all
      // locally known conversations until the remote list catches up instead
      // of relabeling a real conversation as a new empty one.
      const remoteWithActivity = stored.map((remote) => {
        const local = conversations.find((item) => item.id === remote.id);
        return reconcileConversationSummary(remote, local);
      });
      const localMissing = conversations.filter((item) => !remoteWithActivity.some((remote) => remote.id === item.id));
      const activeFallback = remoteWithActivity.some((item) => item.id === conversationId) || localMissing.some((item) => item.id === conversationId)
        ? []
        : [{ ...pendingConversation(conversationId), messageCount: 0 }];
      const withCurrent = [...remoteWithActivity, ...localMissing, ...activeFallback]
        .sort((a, b) => b.updatedAt - a.updatedAt);
      dispatch({ type: 'SET_CONVERSATIONS', payload: withCurrent });
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : t('readConversationsFailed'));
      if (!conversations.some((item) => item.id === conversationId)) {
        dispatch({ type: 'UPSERT_CONVERSATION', payload: pendingConversation(conversationId) });
      }
    } finally {
      setLoading(false);
    }
  }, [conversationId, conversations, dispatch, t]);

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
    setCreating(true);
    try {
      // Running conversations remain active in the background. The active
      // transport ref is switched without cancelling their request.
      const conversation = await createNewConversation();
      dispatch({ type: 'UPSERT_CONVERSATION', payload: conversation });
      setActiveConversationId(conversation.id);
      dispatch({ type: 'SET_CONVERSATION_ID', payload: conversation.id });
      onClose();
    } catch {
      MessagePlugin.error(t('createConversationFailed'));
    } finally { setCreating(false); }
  };

  return (
    <>
      <button
        type="button"
        className={`conversation-sidebar-backdrop ${open ? 'is-open' : ''}`}
        aria-label={t('closeConversations')}
        onClick={onClose}
      />
      <aside className={`conversation-sidebar panel ${open ? 'is-open' : ''}`} aria-label={t('conversationHistory')}>
        <div className="conversation-sidebar-header">
          <div className="conversation-sidebar-title">{t('conversations')}</div>
          <button type="button" className="conversation-sidebar-close" onClick={onClose} aria-label={t('close')} title={t('close')}>×</button>
        </div>

        <Button data-onboarding="new-conversation" block theme="primary" loading={creating} onClick={() => { void create(); }}>
          ＋ {t('newConversation')}
        </Button>

        <div className="conversation-history-label">{t('history')}</div>
        <div className="conversation-list" data-onboarding="conversation-history">
          {loading && conversations.length === 0 && (
            <div className="skeleton-list" role="status" aria-label={t('loading')}>
              {[0, 1, 2, 3].map((row) => (
                <div className="skeleton-conversation-item" key={row}>
                  <span className="skeleton skeleton-dot" aria-hidden="true" />
                  <span className="skeleton-lines" aria-hidden="true">
                    <span className="skeleton skeleton-line" style={{ width: '74%' }} />
                    <span className="skeleton skeleton-line" style={{ width: '46%' }} />
                  </span>
                </div>
              ))}
            </div>
          )}
          {loadError && (
            <button type="button" className="conversation-list-error" onClick={() => { void load(); }}>
              {t('clickToRetry', { message: loadError })}
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
              <span className={`conversation-item-icon status-${conversation.activityStatus || 'idle'}`} aria-label={conversation.activityStatus === 'running' ? t('generating') : conversation.activityStatus === 'failed' ? t('generationFailedShort') : t('idle')}>
                {conversation.activityStatus === 'running' ? '◌' : conversation.activityStatus === 'failed' ? '!' : '◇'}
              </span>
              <span className="conversation-item-content">
                <span className="conversation-item-title">{conversation.title}</span>
                <span className="conversation-item-meta">
                  {conversation.activityStatus === 'running'
                    ? t('generatingAnswer')
                    : conversation.activityStatus === 'failed'
                      ? t('previousGenerationFailed')
                      : conversation.pending
                    ? t('noMessagesYet')
                    : `${conversation.messageCount ? t('messageCount', { count: conversation.messageCount }) : ''}${formatConversationTime(conversation.updatedAt)}`}
                </span>
              </span>
            </button>
          ))}
        </div>
        <ProactiveBriefPanel />
        <div className="conversation-sidebar-tools">
          {toolsLoaded && (
            <Suspense fallback={(
              <div className="sidebar-tools-loading" role="status" aria-label={t('loading')}>
                <span className="skeleton skeleton-line" />
                <span className="skeleton skeleton-line" />
              </div>
            )}>
              <SkillsMarketplaceButton />
              <AppSettingsButton />
            </Suspense>
          )}
        </div>
      </aside>
    </>
  );
}

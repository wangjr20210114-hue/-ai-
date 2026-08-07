import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MessagePlugin } from 'tdesign-react';
import {
  createNewConversation,
  listConversations,
  renameConversation,
} from '../../features/chat/model/client';
import { isPristinePendingConversation, reconcileConversationSummary, setActiveConversationId } from '../../services/conversation';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ConversationSummary } from '../../features/chat/model';
import { formatConversationTime, normalizeTimestamp } from '../../services/time';
import ProactiveBriefPanel from '../../features/settings/view/ProactiveBriefPanel';
import { translate, useLanguage, type TranslationKey } from '../../i18n';
import { CheckIcon, CloseIcon, EditIcon, SearchIcon } from 'tdesign-icons-react';

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
  const { conversationId, conversations, messages } = useAppState();
  const { t } = useLanguage();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const creatingRef = useRef(false);
  const [loadError, setLoadError] = useState('');
  const [renamingId, setRenamingId] = useState('');
  const [renameValue, setRenameValue] = useState('');
  const [historyQuery, setHistoryQuery] = useState('');
  const [savingRename, setSavingRename] = useState(false);
  const [toolsLoaded, setToolsLoaded] = useState(
    () => !window.matchMedia(COMPACT_SIDEBAR_QUERY).matches,
  );
  const groupedConversations = useMemo(() => {
    const query = historyQuery.replace(/\s+/g, ' ').trim().toLocaleLowerCase();
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const groups = new Map<TranslationKey, ConversationSummary[]>();
    conversations.filter((conversation) => (
      !query || conversation.title.toLocaleLowerCase().includes(query)
    )).forEach((conversation) => {
      const age = today - normalizeTimestamp(conversation.updatedAt, 0);
      const key: TranslationKey = age < 86_400_000 ? 'historyToday'
        : age < 2 * 86_400_000 ? 'historyYesterday'
          : age < 7 * 86_400_000 ? 'historyLastSevenDays'
            : 'historyEarlier';
      groups.set(key, [...(groups.get(key) || []), conversation]);
    });
    return [...groups.entries()];
  }, [conversations, historyQuery]);

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

  const activate = (id: string) => {
    if (id === conversationId) {
      onClose();
      return;
    }
    setActiveConversationId(id);
    dispatch({ type: 'SET_CONVERSATION_ID', payload: id });
    onClose();
  };

  const create = () => {
    if (creatingRef.current) return;
    creatingRef.current = true;
    try {
      const current = conversations.find((item) => item.id === conversationId);
      if (isPristinePendingConversation(current, messages)) {
        const reused = { ...current!, updatedAt: Date.now() };
        dispatch({ type: 'UPSERT_CONVERSATION', payload: reused });
        setActiveConversationId(reused.id);
        onClose();
        return;
      }
      // Running conversations remain active in the background. The active
      // transport ref is switched without cancelling their request.
      const conversation = createNewConversation();
      dispatch({ type: 'UPSERT_CONVERSATION', payload: conversation });
      setActiveConversationId(conversation.id);
      dispatch({ type: 'SET_CONVERSATION_ID', payload: conversation.id });
      onClose();
    } catch {
      MessagePlugin.error(t('createConversationFailed'));
    } finally {
      window.setTimeout(() => { creatingRef.current = false; }, 0);
    }
  };

  const startRename = (conversation: ConversationSummary) => {
    setRenamingId(conversation.id);
    setRenameValue(conversation.title);
  };

  const saveRename = async (conversation: ConversationSummary) => {
    const title = renameValue.replace(/\s+/g, ' ').trim().slice(0, 64);
    if (!title) return;
    if (title === conversation.title) {
      setRenamingId('');
      return;
    }
    const optimistic = { ...conversation, title, updatedAt: Date.now() };
    dispatch({ type: 'UPSERT_CONVERSATION', payload: optimistic });
    setRenamingId('');
    setSavingRename(true);
    try {
      const saved = await renameConversation(conversation.id, title);
      dispatch({ type: 'UPSERT_CONVERSATION', payload: reconcileConversationSummary(saved, optimistic) });
    } catch {
      dispatch({ type: 'UPSERT_CONVERSATION', payload: conversation });
      MessagePlugin.error(t('renameConversationFailed'));
    } finally {
      setSavingRename(false);
    }
  };

  const conversationMeta = (conversation: ConversationSummary) => (
    conversation.activityStatus === 'running'
      ? t('generatingAnswer')
      : conversation.activityStatus === 'failed'
        ? t('previousGenerationFailed')
        : conversation.pending
          ? t('noMessagesYet')
          : `${conversation.messageCount ? t('messageCount', { count: conversation.messageCount }) : ''}${formatConversationTime(conversation.updatedAt)}`
  );

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

        <button
          type="button"
          className="conversation-create-button"
          data-onboarding="new-conversation"
          onClick={create}
        >
          <span aria-hidden="true">＋</span>
          {t('newConversation')}
        </button>

        <div className="conversation-history-label">{t('history')}</div>
        <label className="conversation-history-search">
          <SearchIcon aria-hidden="true" />
          <input
            value={historyQuery}
            onChange={(event) => setHistoryQuery(event.target.value)}
            placeholder={t('searchConversations')}
            aria-label={t('searchConversations')}
          />
        </label>
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
          {!loading && groupedConversations.length === 0 && (
            <div className="conversation-list-empty">{t('noMatchingConversations')}</div>
          )}
          {groupedConversations.map(([group, items]) => <section className="conversation-history-group" key={group}>
            <h3>{t(group)}</h3>
            {items.map((conversation) => (
            <div
              key={conversation.id}
              className={`conversation-item ${conversation.id === conversationId ? 'is-active' : ''}`}
              title={conversation.title}
            >
              {renamingId === conversation.id ? (
                <div className="conversation-item-main">
                  <span className={`conversation-item-icon status-${conversation.activityStatus || 'idle'}`} aria-hidden="true">
                    {conversation.activityStatus === 'running' ? '◌' : conversation.activityStatus === 'failed' ? '!' : '◇'}
                  </span>
                  <span className="conversation-item-content">
                    <input
                      className="conversation-rename-input"
                      value={renameValue}
                      maxLength={64}
                      aria-label={t('conversationName')}
                      autoFocus
                      onChange={(event) => setRenameValue(event.target.value)}
                      onClick={(event) => event.stopPropagation()}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') { event.preventDefault(); void saveRename(conversation); }
                        if (event.key === 'Escape') setRenamingId('');
                      }}
                    />
                    <span className="conversation-item-meta">{conversationMeta(conversation)}</span>
                  </span>
                </div>
              ) : (
                <button type="button" className="conversation-item-main" onClick={() => { activate(conversation.id); }}>
                  <span className={`conversation-item-icon status-${conversation.activityStatus || 'idle'}`} aria-label={conversation.activityStatus === 'running' ? t('generating') : conversation.activityStatus === 'failed' ? t('generationFailedShort') : t('idle')}>
                    {conversation.activityStatus === 'running' ? '◌' : conversation.activityStatus === 'failed' ? '!' : '◇'}
                  </span>
                  <span className="conversation-item-content">
                    <span className="conversation-item-title">{conversation.title}</span>
                    <span className="conversation-item-meta">{conversationMeta(conversation)}</span>
                  </span>
                </button>
              )}
              {renamingId === conversation.id ? (
                <span className="conversation-item-actions">
                  <button type="button" disabled={savingRename} onClick={() => { void saveRename(conversation); }} aria-label={t('saveName')} title={t('saveName')}><CheckIcon /></button>
                  <button type="button" onClick={() => setRenamingId('')} aria-label={t('cancel')} title={t('cancel')}><CloseIcon /></button>
                </span>
              ) : (
                <button type="button" className="conversation-rename-button" onClick={() => startRename(conversation)} aria-label={t('renameConversation')} title={t('renameConversation')}><EditIcon /></button>
              )}
            </div>
            ))}
          </section>)}
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

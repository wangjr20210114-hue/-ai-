import { useEffect, useState } from 'react';
import { Button, Checkbox, MessagePlugin, Textarea, Upload } from 'tdesign-react';
import { SendIcon, AttachIcon } from 'tdesign-icons-react';
import type { UploadFile } from 'tdesign-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ChatMessage, WSMessage } from '../../types';
import type { ChatClient } from '../../services/chatClient';
import { proactiveOperation, saveConversationMessage, uploadDocument } from '../../services/api';
import { registerReadingItem } from '../../services/paperApi';

interface Props {
  client: React.RefObject<ChatClient | null>;
}

/** 底部输入栏：文本输入 + 文档上传 + 发送（场景由后端自动推断）。 */
export default function InputBar({ client }: Props) {
  const { draft, conversationId, conversations } = useAppState();
  const dispatch = useAppDispatch();
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [webSearch, setWebSearch] = useState(true);

  // 点击空态引导词 → 回填输入框
  useEffect(() => {
    if (draft) {
      setText(draft);
      dispatch({ type: 'SET_DRAFT', payload: '' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const sendActivity = (message: ChatMessage, activity: string) => {
    const msg: WSMessage = {
      type: 'user_activity',
      payload: {
        activity,
        text: message.content,
        message_id: message.id,
        web_search: webSearch,
        client_message: message,
      },
    };
    client.current?.send(msg);
  };

  const handleSend = async () => {
    const content = text.trim();
    if (!content || sending) return;
    const message = {
      id: Date.now().toString(),
      role: 'user' as const,
      content,
      ts: Date.now(),
    };
    setSending(true);
    // Optimistically render and seed the SSE cache before any network await;
    // otherwise stream_start can hydrate from an older cache and hide this row.
    dispatch({ type: 'ADD_MESSAGE', payload: message });
    const previous = conversations.find((item) => item.id === conversationId);
    dispatch({
      type: 'UPSERT_CONVERSATION',
      payload: {
        id: conversationId,
        title: previous?.pending ? (content.length > 32 ? `${content.slice(0, 32)}…` : content) : (previous?.title || content.slice(0, 32)),
        createdAt: previous?.createdAt || Date.now(),
        updatedAt: Date.now(),
        messageCount: Math.max(1, Number(previous?.messageCount || 0) + 1),
        pending: false,
      },
    });
    setText('');
    sendActivity(message, 'asked');
    setSending(false);
    void saveConversationMessage(conversationId, message).catch((error) => {
      MessagePlugin.error(error instanceof Error ? error.message : '消息同步失败');
    });
  };

  const handleUpload = async (files: UploadFile[]) => {
    const f = files[0];
    if (!f?.raw) return;
    setUploading(true);
    try {
      const stored = await uploadDocument(conversationId, f.raw);
      let detectedPaper = false;
      if (stored.storage_key && (f.raw.type === 'application/pdf' || f.raw.name.toLowerCase().endsWith('.pdf'))) {
        try {
          const { inspectPdf } = await import('../../services/reading');
          const inspection = await inspectPdf(f.raw);
          detectedPaper = inspection.isPaper;
          await registerReadingItem({
            storage_key: stored.storage_key,
            filename: stored.original_name,
            title: inspection.title,
            mime_type: stored.mime_type,
            is_paper: inspection.isPaper,
            page_count: inspection.pageCount,
            preview: inspection.preview,
          });
        } catch {
          await registerReadingItem({
            storage_key: stored.storage_key,
            filename: stored.original_name,
            title: stored.original_name,
            mime_type: stored.mime_type,
            is_paper: false,
          });
        }
      }
      const userMessage = {
        id: `upload-${Date.now()}`,
        role: 'user',
        content: `已上传文档：${stored.original_name}`,
        ts: Date.now(),
      } as const;
      const aiMessage = {
        id: `file-${Date.now()}`,
        role: 'ai',
        content: `${detectedPaper ? '已识别为论文并加入“我的阅读”，可使用选词翻译、全文分析与问答。' : 'PDF 已加入“我的阅读”。'}\n\n[打开 ${stored.original_name}](${stored.content_url})`,
        ts: Date.now() + 1,
        paperFileId: stored.id,
        paperFileName: stored.original_name,
      } as const;
      dispatch({ type: 'ADD_MESSAGE', payload: userMessage });
      dispatch({ type: 'ADD_MESSAGE', payload: aiMessage });
      await Promise.all([
        saveConversationMessage(conversationId, userMessage),
        saveConversationMessage(conversationId, aiMessage),
      ]);
      void proactiveOperation(conversationId, 'ingest_signal', {
        signal_type: 'file_uploaded',
        dedup_key: stored.storage_key || stored.id,
        payload: {
          file_id: stored.id,
          storage_key: stored.storage_key,
          filename: stored.original_name,
          mime_type: stored.mime_type,
          is_paper: detectedPaper,
        },
      }).then((proactive) => dispatch({ type: 'HYDRATE_PROACTIVE', payload: proactive }))
        .catch((error) => console.warn('file signal ingestion failed', error));
      MessagePlugin.success(stored.storage_key ? (detectedPaper ? '论文已加入我的阅读' : 'PDF 已加入我的阅读') : 'PDF 已上传并建立持久索引');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '上传失败');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="input-wrap">
      <div className="input-box">
        <Textarea
          value={text}
          onChange={(v) => setText(v as string)}
          placeholder="输入消息…（Enter 发送，Shift+Enter 换行）"
          autosize={{ minRows: 1, maxRows: 5 }}
          style={{ width: '100%' }}
          onKeydown={(_, ctx) => {
            const e = ctx.e as React.KeyboardEvent;
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              void handleSend();
            }
          }}
        />
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 8,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Upload
              theme="custom"
              accept=".pdf,application/pdf"
              autoUpload={false}
              requestMethod={() => Promise.resolve({ status: 'success', response: {} })}
              onChange={(files) => { void handleUpload(files as UploadFile[]); }}
            >
              <Button variant="text" size="small" icon={<AttachIcon />} loading={uploading}>
                上传文档
              </Button>
            </Upload>
            <Checkbox checked={webSearch} onChange={(v) => setWebSearch(v as boolean)}>
              联网搜索
            </Checkbox>
          </div>
          <Button
            theme="primary"
            icon={<SendIcon />}
            onClick={() => { void handleSend(); }}
            loading={sending}
            disabled={!text.trim() || sending}
          >
            发送
          </Button>
        </div>
      </div>
    </div>
  );
}

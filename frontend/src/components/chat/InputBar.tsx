import { useEffect, useState } from 'react';
import { Button, MessagePlugin, Textarea, Upload } from 'tdesign-react';
import { SendIcon, AttachIcon } from 'tdesign-icons-react';
import type { UploadFile } from 'tdesign-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { WSMessage } from '../../types';
import type { WSClient } from '../../services/websocket';
import { saveConversationMessage, uploadDocument } from '../../services/api';

interface Props {
  client: React.RefObject<WSClient | null>;
}

/** 底部输入栏：文本输入 + 文档上传 + 发送（场景由后端自动推断）。 */
export default function InputBar({ client }: Props) {
  const { draft, conversationId } = useAppState();
  const dispatch = useAppDispatch();
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);

  // 点击空态引导词 → 回填输入框
  useEffect(() => {
    if (draft) {
      setText(draft);
      dispatch({ type: 'SET_DRAFT', payload: '' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const sendActivity = (content: string, activity: string) => {
    const msg: WSMessage = {
      type: 'user_activity',
      payload: { activity, text: content },
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
    try {
      await saveConversationMessage(conversationId, message);
      dispatch({ type: 'ADD_MESSAGE', payload: message });
      sendActivity(content, 'asked');
      setText('');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '消息保存失败');
    } finally {
      setSending(false);
    }
  };

  const handleUpload = async (files: UploadFile[]) => {
    const f = files[0];
    if (!f?.raw) return;
    setUploading(true);
    try {
      const stored = await uploadDocument(conversationId, f.raw);
      const userMessage = {
        id: `upload-${Date.now()}`,
        role: 'user',
        content: `已上传文档：${stored.original_name}`,
        ts: Date.now(),
      } as const;
      const aiMessage = {
        id: `file-${Date.now()}`,
        role: 'ai',
        content: `PDF 已安全保存并提取文本：${stored.page_count} 页，共 ${stored.total_chars} 字。\n\n[打开 ${stored.original_name}](/api/files/${stored.id}/content)\n\n> ${stored.preview.slice(0, 240).replace(/\s+/g, ' ')}…`,
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
      MessagePlugin.success('PDF 已上传并建立持久索引');
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
      <div
        style={{
          textAlign: 'center',
          fontSize: 11.5,
          color: 'var(--app-text-3)',
          marginTop: 8,
        }}
      >
        输入消息，AI 会自动识别旅游或会议意图
      </div>
    </div>
  );
}

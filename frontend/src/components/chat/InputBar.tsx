import { useEffect, useState } from 'react';
import { Button, Checkbox, MessagePlugin, Textarea, Upload } from 'tdesign-react';
import { SendIcon, AttachIcon } from 'tdesign-icons-react';
import type { UploadFile } from 'tdesign-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ChatClient } from '../../services/chatClient';
import { uploadDocument } from '../../services/api';

interface Props {
  client: React.RefObject<ChatClient | null>;
}

/** Bottom input for the EdgeOne Makers chat and Blob upload endpoints. */
export default function InputBar({ client }: Props) {
  const { draft, conversationId, userId } = useAppState();
  const dispatch = useAppDispatch();
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [webSearch, setWebSearch] = useState(true);

  useEffect(() => {
    if (draft) {
      setText(draft);
      dispatch({ type: 'SET_DRAFT', payload: '' });
    }
  }, [draft, dispatch]);

  const handleSend = () => {
    const content = text.trim();
    if (!content) return;
    const message = {
      id: Date.now().toString(),
      role: 'user' as const,
      content,
      ts: Date.now(),
    };
    dispatch({ type: 'ADD_MESSAGE', payload: message });
    void client.current?.send({
      type: 'user_activity',
      payload: {
        activity: 'asked',
        text: content,
        message_id: message.id,
        web_search: webSearch,
        user_id: userId,
      },
    });
    setText('');
  };

  const handleUpload = async (files: UploadFile[]) => {
    const file = files[0]?.raw;
    if (!file) return;
    setUploading(true);
    try {
      const stored = await uploadDocument(conversationId, file);
      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: `upload-${Date.now()}`,
          role: 'user',
          content: `已上传文档：${stored.original_name}`,
          ts: Date.now(),
        },
      });
      dispatch({
        type: 'ADD_MESSAGE',
        payload: {
          id: `file-${Date.now()}`,
          role: 'ai',
          content: `PDF 已安全保存到 EdgeOne Makers Blob。\n\n[打开 ${stored.original_name}](${stored.content_url})`,
          ts: Date.now() + 1,
        },
      });
      MessagePlugin.success('PDF 已上传到 Makers Blob');
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
          onChange={(value) => setText(value as string)}
          placeholder="输入消息…（Enter 发送，Shift+Enter 换行）"
          autosize={{ minRows: 1, maxRows: 5 }}
          style={{ width: '100%' }}
          onKeydown={(_, context) => {
            const event = context.e as React.KeyboardEvent;
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              handleSend();
            }
          }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
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
            <Checkbox checked={webSearch} onChange={(value) => setWebSearch(value as boolean)}>
              联网搜索
            </Checkbox>
          </div>
          <Button theme="primary" icon={<SendIcon />} onClick={handleSend} disabled={!text.trim()}>
            发送
          </Button>
        </div>
      </div>
      <div style={{ textAlign: 'center', fontSize: 11.5, color: 'var(--app-text-3)', marginTop: 8 }}>
        会话、运行轨迹与联网工具由 EdgeOne Makers 托管
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { Button, Textarea, Upload } from 'tdesign-react';
import { SendIcon, AttachIcon } from 'tdesign-icons-react';
import type { UploadFile } from 'tdesign-react';
import { useAppDispatch, useAppState } from '../../store/AppContext';
import type { WSMessage } from '../../types';
import type { WSClient } from '../../services/websocket';

interface Props {
  client: React.RefObject<WSClient | null>;
}

/** 底部输入栏：文本输入 + 文档上传 + 发送（场景由后端自动推断）。 */
export default function InputBar({ client }: Props) {
  const { draft } = useAppState();
  const dispatch = useAppDispatch();
  const [text, setText] = useState('');

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

  const handleSend = () => {
    const content = text.trim();
    if (!content) return;
    dispatch({
      type: 'ADD_MESSAGE',
      payload: { id: Date.now().toString(), role: 'user', content, ts: Date.now() },
    });
    sendActivity(content, 'asked');
    setText('');
  };

  const handleUpload = (files: UploadFile[]) => {
    const f = files[0];
    if (!f) return;
    const name = f.name || '文档.pdf';
    dispatch({
      type: 'ADD_MESSAGE',
      payload: {
        id: Date.now().toString(),
        role: 'user',
        content: `已上传文档：${name}`,
        ts: Date.now(),
      },
    });
    sendActivity(`请总结文档《${name}》的核心内容`, 'asked');
    return files;
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
              handleSend();
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
            autoUpload={false}
            requestMethod={() => Promise.resolve({ status: 'success', response: {} })}
            onChange={handleUpload}
          >
            <Button variant="text" size="small" icon={<AttachIcon />}>
              上传文档
            </Button>
          </Upload>
          <Button theme="primary" icon={<SendIcon />} onClick={handleSend} disabled={!text.trim()}>
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

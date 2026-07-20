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

async function imageReferenceDataUrl(file: File): Promise<string> {
  const source = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error('无法读取参考图片'));
      element.src = source;
    });
    const scale = Math.min(1, 1280 / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('浏览器无法处理参考图片');
    context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.78);
    if (dataUrl.length > 1_800_000) throw new Error('参考图片处理后仍过大，请换一张较小的图片');
    return dataUrl;
  } finally { URL.revokeObjectURL(source); }
}

/** 底部输入栏：文本输入 + 文档上传 + 发送（场景由后端自动推断）。 */
export default function InputBar({ client }: Props) {
  const { draft, conversationId, conversations, messages } = useAppState();
  const dispatch = useAppDispatch();
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [webSearch, setWebSearch] = useState(true);
  const [referenceImage, setReferenceImage] = useState<{ name: string; dataUrl: string } | null>(null);
  const activeStreaming = messages.some((message) => message.streaming);

  // 点击空态引导词 → 回填输入框
  useEffect(() => {
    if (draft) {
      setText(draft);
      dispatch({ type: 'SET_DRAFT', payload: '' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const sendActivity = (message: ChatMessage, activity: string, referenceImages: string[] = []) => {
    const msg: WSMessage = {
      type: 'user_activity',
      payload: {
        activity,
        text: message.content,
        message_id: message.id,
        client_message_id: message.id,
        web_search: webSearch,
        client_message: message,
        reference_images: referenceImages,
      },
    };
    client.current?.send(msg);
  };

  const handleSend = async () => {
    const content = text.trim();
    if (!content || sending || stopping || activeStreaming) return;
    const message = {
      id: Date.now().toString(),
      role: 'user' as const,
      content: referenceImage ? `${content}\n\n📎 已附参考图片：${referenceImage.name}` : content,
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
    sendActivity(message, 'asked', referenceImage ? [referenceImage.dataUrl] : []);
    setReferenceImage(null);
    setSending(false);
  };

  const handleStop = async () => {
    if (!activeStreaming || stopping || !client.current?.stop) return;
    setStopping(true);
    try {
      await client.current.stop();
      MessagePlugin.info('已停止生成');
    } catch {
      MessagePlugin.warning('停止请求未确认，请稍后重试');
    } finally { setStopping(false); }
  };

  const handleUpload = async (files: UploadFile[]) => {
    const f = files[0];
    if (!f?.raw) return;
    setUploading(true);
    try {
      const stored = await uploadDocument(conversationId, f.raw);
      if (f.raw.type.startsWith('image/')) {
        const dataUrl = await imageReferenceDataUrl(f.raw);
        setReferenceImage({ name: stored.original_name, dataUrl });
        MessagePlugin.success('参考图片已附加；输入修改或生成要求后发送');
        return;
      }
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
        content: detectedPaper ? '已识别为论文并加入“我的阅读”，已在下方打开论文助读。' : 'PDF 已加入“我的阅读”，已在下方打开阅读器。',
        ts: Date.now() + 1,
        paperFileId: stored.id,
        paperFileName: stored.original_name,
        paperTitle: stored.original_name,
        showPaperReader: true,
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
      <div className="input-box" onPaste={(event) => {
        const image = Array.from(event.clipboardData.files).find((file) => file.type.startsWith('image/'));
        if (!image) return;
        event.preventDefault();
        void handleUpload([{ raw: image, name: image.name || `粘贴图片-${Date.now()}.png` } as UploadFile]);
      }}>
        {referenceImage && <div className="chat-reference-image">
          <img src={referenceImage.dataUrl} alt="待发送参考图" />
          <span>{referenceImage.name}<small>发送时作为生图参考，不会显示数据内容</small></span>
          <button type="button" onClick={() => setReferenceImage(null)} aria-label="移除参考图片">×</button>
        </div>}
        <Textarea
          value={text}
          onChange={(v) => setText(v as string)}
          disabled={stopping}
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
              accept=".pdf,application/pdf,.png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
              autoUpload={false}
              requestMethod={() => Promise.resolve({ status: 'success', response: {} })}
              onChange={(files) => { void handleUpload(files as UploadFile[]); }}
            >
              <Button variant="text" size="small" icon={<AttachIcon />} loading={uploading}>
                上传文件
              </Button>
            </Upload>
            <Checkbox checked={webSearch} onChange={(v) => setWebSearch(v as boolean)}>
              联网搜索
            </Checkbox>
          </div>
          {activeStreaming || stopping ? (
            <Button theme="danger" variant="outline" loading={stopping} disabled={stopping} onClick={() => { void handleStop(); }} aria-label={stopping ? '正在停止生成' : '停止生成'}>
              {stopping ? '正在停止…' : '■ 停止生成'}
            </Button>
          ) : (
            <Button
              theme="primary"
              icon={<SendIcon />}
              onClick={() => { void handleSend(); }}
              loading={sending}
              disabled={!text.trim() || sending}
            >
              发送
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

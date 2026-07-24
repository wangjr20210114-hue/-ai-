import { useEffect, useState } from 'react';
import { Button, MessagePlugin, Textarea, Upload } from 'tdesign-react';
import { SendIcon, AttachIcon } from 'tdesign-icons-react';
import type { UploadFile } from 'tdesign-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ChatMessage, WSMessage } from '../../types';
import type { ChatClient } from '../../services/chatClient';
import { proactiveOperation, saveConversationMessage, uploadDocument } from '../../services/api';
import { registerReadingItem } from '../../services/paperApi';
import { getStoredLanguage, translate, useLanguage } from '../../i18n';

interface Props {
  client: React.RefObject<ChatClient | null>;
}

async function imageReferenceDataUrl(file: File): Promise<string> {
  const source = URL.createObjectURL(file);
  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const element = new Image();
      element.onload = () => resolve(element);
      element.onerror = () => reject(new Error(translate('cannotReadReferenceImage')));
      element.src = source;
    });
    const scale = Math.min(1, 1280 / Math.max(image.naturalWidth, image.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error(translate('cannotProcessReferenceImage'));
    context.fillStyle = '#fff'; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.78);
    if (dataUrl.length > 1_800_000) throw new Error(translate('referenceImageTooLarge'));
    return dataUrl;
  } finally { URL.revokeObjectURL(source); }
}

/** 底部输入栏：文本输入 + 文档上传 + 发送（场景由后端自动推断）。 */
export default function InputBar({ client }: Props) {
  const { draft, documentContext, conversationId, conversations, messages } = useAppState();
  const { t } = useLanguage();
  const dispatch = useAppDispatch();
  const [text, setText] = useState('');
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState(false);
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
        client_message: message,
        reference_images: referenceImages,
        document_context: documentContext ? {
          filename: documentContext.filename,
          text: documentContext.text,
        } : undefined,
        response_language: getStoredLanguage(),
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
      content: referenceImage ? `${content}\n\n${t('attachedReference', { name: referenceImage.name })}` : content,
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
    dispatch({ type: 'SET_DOCUMENT_CONTEXT', payload: null });
    setSending(false);
  };

  const handleStop = async () => {
    if (!activeStreaming || stopping || !client.current?.stop) return;
    setStopping(true);
    try {
      const status = await client.current.stop();
      if (status === 'confirmed') {
        MessagePlugin.info(t('stoppedGeneration'));
      } else {
        MessagePlugin.warning(t('stoppedLocally'));
      }
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
        MessagePlugin.success(t('attachReferenceImage'));
        return;
      }
      let detectedPaper = false;
      let documentPreview = '';
      if (stored.storage_key && (f.raw.type === 'application/pdf' || f.raw.name.toLowerCase().endsWith('.pdf'))) {
        try {
          const { inspectPdf } = await import('../../services/reading');
          const inspection = await inspectPdf(f.raw);
          detectedPaper = inspection.isPaper;
          documentPreview = inspection.preview;
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
        content: t('uploadedDocument', { name: stored.original_name }),
        ts: Date.now(),
      } as const;
      const aiMessage = {
        id: `file-${Date.now()}`,
        role: 'ai',
        content: detectedPaper ? t('paperOpened') : t('pdfOpened'),
        ts: Date.now() + 1,
        paperFileId: stored.id,
        paperFileName: stored.original_name,
        paperTitle: stored.original_name,
        paperIsPaper: detectedPaper,
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
          preview: documentPreview,
          ui_language: getStoredLanguage(),
        },
      }).then((proactive) => dispatch({ type: 'HYDRATE_PROACTIVE', payload: proactive }))
        .catch((error) => console.warn('file signal ingestion failed', error));
      MessagePlugin.success(stored.storage_key ? (detectedPaper ? t('paperAdded') : t('pdfAdded')) : t('pdfIndexed'));
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('uploadFailed'));
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
        void handleUpload([{ raw: image, name: image.name || t('pastedImageName', { time: Date.now() }) } as UploadFile]);
      }}>
        {documentContext && <div className="chat-reference-document">
          <b>PDF</b>
          <span>{documentContext.filename}<small>{t('documentContextHint')}</small></span>
          <button type="button" onClick={() => dispatch({ type: 'SET_DOCUMENT_CONTEXT', payload: null })} aria-label={t('removeDocumentContext')} title={t('removeDocumentContext')}>×</button>
        </div>}
        {referenceImage && <div className="chat-reference-image">
          <img src={referenceImage.dataUrl} alt={t('pendingReferenceImage')} />
          <span>{referenceImage.name}<small>{t('referenceImageHint')}</small></span>
          <button type="button" onClick={() => setReferenceImage(null)} aria-label={t('removeReferenceImage')} title={t('removeReferenceImage')}>×</button>
        </div>}
        <Textarea
          value={text}
          onChange={(v) => setText(v as string)}
          disabled={stopping}
          placeholder={t('inputPlaceholder')}
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
        <div className="input-toolbar">
          <div className="input-options">
            <Upload
              theme="custom"
              accept=".pdf,application/pdf,.png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
              autoUpload={false}
              requestMethod={() => Promise.resolve({ status: 'success', response: {} })}
              onChange={(files) => { void handleUpload(files as UploadFile[]); }}
            >
              <Button className="input-attachment-button" variant="text" size="small" icon={<AttachIcon />} loading={uploading}>
                {t('upload')}
              </Button>
            </Upload>
          </div>
          {activeStreaming || stopping ? (
            <Button className="input-submit-button" theme="danger" variant="outline" loading={stopping} disabled={stopping} onClick={() => { void handleStop(); }} aria-label={stopping ? t('stoppingGeneration') : t('stopGeneration')}>
              {stopping ? t('stoppingGeneration') : `■ ${t('stopGeneration')}`}
            </Button>
          ) : (
            <Button
              className="input-submit-button"
              theme="primary"
              icon={<SendIcon />}
              onClick={() => { void handleSend(); }}
              loading={sending}
              disabled={!text.trim() || sending}
            >
              {t('send')}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * 对话中的 PDF 兼容预览。论文会额外提供明确的「论文助读」入口。
 */
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button, Loading, MessagePlugin } from 'tdesign-react';
import { BookOpenIcon, FullscreenIcon } from 'tdesign-icons-react';
import { fetchPaperFile } from '../../services/paperApi';
import PaperFullReader from './PaperFullReader';
import { useLanguage } from '../../i18n';

interface Props {
  fileId: string;
  fileName: string;
  title: string;
  assistantEnabled?: boolean;
}

export default function PaperInlineReader({
  fileId,
  fileName,
  title,
  assistantEnabled = false,
}: Props) {
  const { t } = useLanguage();
  const [objectUrl, setObjectUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    void (async () => {
      try {
        setLoading(true);
        setLoadError('');
        const response = await fetchPaperFile(fileId, controller.signal);
        if (!response.ok) throw new Error(t('pdfLoadStatusFailed', { status: response.status }));
        const nextUrl = URL.createObjectURL(await response.blob());
        if (cancelled) {
          URL.revokeObjectURL(nextUrl);
          return;
        }
        setObjectUrl(nextUrl);
      } catch (error) {
        if (!cancelled && !(error instanceof DOMException && error.name === 'AbortError')) {
          const text = error instanceof Error ? error.message : t('pdfLoadFailed');
          setLoadError(text);
          MessagePlugin.error(t('pdfLoadFailed'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [fileId, t]);

  useEffect(() => () => {
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  }, [objectUrl]);

  return (
    <div className="paper-inline-reader">
      <div className="paper-inline-toolbar">
        <span title={title || fileName}>📄 {title || fileName}</span>
        <div>
          {assistantEnabled && (
            <Button
              className="paper-control"
              size="small"
              theme="primary"
              icon={<BookOpenIcon />}
              onClick={() => setExpanded(true)}
            >
              {t('paperAssistant')}
            </Button>
          )}
          <Button
            className="paper-control"
            size="small"
            variant="outline"
            icon={<FullscreenIcon />}
            onClick={() => setExpanded(true)}
          >
            {t('fullscreenReading')}
          </Button>
        </div>
      </div>
      <div className="paper-inline-preview">
        {loading && <div className="paper-loading-state"><Loading /><span>{t('openingCompatiblePreview')}</span></div>}
        {loadError && <div className="paper-load-error"><strong>{t('pdfOpenFailed')}</strong><span>{loadError}</span></div>}
        {objectUrl && <iframe className="paper-native-frame paper-inline-frame" src={objectUrl} title={title || fileName} />}
      </div>
      {expanded && createPortal(
        <PaperFullReader
          fileId={fileId}
          title={title || fileName}
          assistantEnabled={assistantEnabled}
          onClose={() => setExpanded(false)}
        />,
        document.body,
      )}
    </div>
  );
}

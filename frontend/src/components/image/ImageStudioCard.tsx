import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { ChevronLeftIcon, ChevronRightIcon, DownloadIcon } from 'tdesign-icons-react';
import { streamImageEdit } from '../../services/api';
import { withEdgeOneAuth } from '../../services/auth';
import { createZip } from '../../services/zip';
import type { WorkspaceAction } from '../../types';
import { useLanguage, type TranslationKey } from '../../i18n';

interface ImageVersion {
  id: string;
  prompt: string;
  image_url: string;
  storage_key?: string;
  parent_action_id?: string;
  created_at?: number;
}

interface Props {
  action: WorkspaceAction;
  conversationId: string;
  onUpdated: (action: WorkspaceAction) => void;
}

function versionsFrom(action: WorkspaceAction): ImageVersion[] {
  const result = action.result || {};
  const versions = Array.isArray(result.versions) ? result.versions as ImageVersion[] : [];
  if (versions.length) return versions.filter((item) => item?.id && item?.image_url);
  if (typeof result.image_url === 'string' && result.image_url) {
    return [{
      id: action.id,
      prompt: String(action.payload.prompt || ''),
      image_url: result.image_url,
      storage_key: typeof result.storage_key === 'string' ? result.storage_key : '',
      created_at: action.created_at,
    }];
  }
  return [];
}

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

const PAINTING_STEPS: TranslationKey[] = [
  'paintingUnderstand',
  'paintingCompose',
  'paintingDetail',
  'paintingReveal',
];

function PaintingStatus() {
  const [step, setStep] = useState(0);
  const { t } = useLanguage();
  useEffect(() => {
    const timer = window.setInterval(() => setStep((value) => (value + 1) % PAINTING_STEPS.length), 1800);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <div className="image-painting-copy" aria-live="polite">
      <strong>{t(PAINTING_STEPS[step])}</strong>
      <small>{t('paintingWait')}</small>
    </div>
  );
}

export default function ImageStudioCard({ action, conversationId, onUpdated }: Props) {
  const { t } = useLanguage();
  const [currentAction, setCurrentAction] = useState(action);
  const [index, setIndex] = useState(0);
  const [instruction, setInstruction] = useState('');
  const [generating, setGenerating] = useState(false);
  const [loadedUrls, setLoadedUrls] = useState<Set<string>>(() => new Set());
  const [cacheRevision, setCacheRevision] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const loadedUrlsRef = useRef<Set<string>>(new Set());
  const downloadCacheRef = useRef<Map<string, { blob: Blob; objectUrl: string }>>(new Map());
  const versions = useMemo(() => versionsFrom(currentAction), [currentAction]);
  const selected = versions[Math.min(index, Math.max(0, versions.length - 1))];
  const selectedSrc = selected
    ? downloadCacheRef.current.get(selected.image_url)?.objectUrl || withEdgeOneAuth(selected.image_url)
    : '';
  const imageReady = Boolean(selected && loadedUrls.has(selected.image_url));
  const originalPrompt = versions[0]?.prompt || selected?.prompt || '';
  const editHint = originalPrompt
    ? t('editImageHint', { prompt: `${originalPrompt.slice(0, 36)}${originalPrompt.length > 36 ? '…' : ''}` })
    : t('describeImageEdit');

  useEffect(() => {
    setCurrentAction(action);
    const next = versionsFrom(action);
    setIndex(Math.max(0, next.length - 1));
  }, [action]);

  useEffect(() => {
    let cancelled = false;
    for (const version of versions) {
      if (loadedUrlsRef.current.has(version.image_url)) continue;
      const image = new Image();
      image.decoding = 'async';
      image.onload = () => {
        if (cancelled) return;
        setLoadedUrls((current) => {
          if (current.has(version.image_url)) return current;
          loadedUrlsRef.current.add(version.image_url);
          const next = new Set(current);
          next.add(version.image_url);
          return next;
        });
      };
      image.src = downloadCacheRef.current.get(version.image_url)?.objectUrl || withEdgeOneAuth(version.image_url);
    }
    return () => { cancelled = true; };
  }, [versions, cacheRevision]);

  useEffect(() => () => {
    for (const cached of downloadCacheRef.current.values()) URL.revokeObjectURL(cached.objectUrl);
    downloadCacheRef.current.clear();
  }, []);

  const fetchVersionBlob = async (version: ImageVersion): Promise<Blob> => {
    const cached = downloadCacheRef.current.get(version.image_url);
    if (cached) return cached.blob;
    const response = await fetch(withEdgeOneAuth(version.image_url));
    if (!response.ok) throw new Error(t('imageDownloadFailed'));
    const blob = await response.blob();
    downloadCacheRef.current.set(version.image_url, { blob, objectUrl: URL.createObjectURL(blob) });
    loadedUrlsRef.current.add(version.image_url);
    setLoadedUrls((current) => new Set(current).add(version.image_url));
    setCacheRevision((value) => value + 1);
    return blob;
  };

  const generateEdit = async () => {
    const prompt = instruction.trim();
    if (!prompt || !selected) return;
    setGenerating(true);
    let waitingForImage = false;
    try {
      const action = await streamImageEdit(conversationId, prompt, selected.id);
      setCurrentAction(action);
      onUpdated(action);
      const next = versionsFrom(action);
      setIndex(Math.max(0, next.length - 1));
      setInstruction('');
      if (action.status === 'failed') throw new Error(action.error || t('imageEditFailed'));
      waitingForImage = true;
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('imageEditFailed'));
    } finally {
      if (!waitingForImage) setGenerating(false);
    }
  };

  const downloadOne = async () => {
    if (!selected) return;
    try {
      saveBlob(await fetchVersionBlob(selected), `Floris-image-${index + 1}.png`);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('imageDownloadFailed'));
    }
  };

  const downloadAll = async () => {
    if (!versions.length) return;
    setDownloading(true);
    try {
      const entries = await Promise.all(versions.map(async (version, versionIndex) => {
        try {
          return { name: `Floris-image-${versionIndex + 1}.png`, data: new Uint8Array(await (await fetchVersionBlob(version)).arrayBuffer()) };
        } catch {
          throw new Error(t('imageNumberDownloadFailed', { number: versionIndex + 1 }));
        }
      }));
      saveBlob(createZip(entries), `Floris-images-${Date.now()}.zip`);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('batchDownloadFailed'));
    } finally {
      setDownloading(false);
    }
  };

  if (currentAction.status === 'executing') {
    return (
      <div className="image-studio-card image-studio-loading">
        <div className="image-studio-stage is-painting image-studio-stage-placeholder">
          <div className="image-painting-overlay"><span /><PaintingStatus /></div>
        </div>
      </div>
    );
  }
  if (!versions.length) {
    return <div className="image-studio-card image-studio-error">{t('imageGenerationFailed', { reason: currentAction.error || t('noImageReturned') })}</div>;
  }

  return (
    <div className="image-studio-card">
      <div className="image-studio-header">
        <div><strong>{t('imageStudio')}</strong><span>{index + 1} / {versions.length}</span></div>
        <div className="image-studio-downloads">
          <Button size="small" variant="text" icon={<DownloadIcon />} onClick={() => void downloadOne()}>{t('download')}</Button>
          <Button size="small" variant="outline" loading={downloading} onClick={() => void downloadAll()}>{t('batchDownload')}</Button>
        </div>
      </div>
      <div className={`image-studio-stage ${generating || !imageReady ? 'is-painting' : ''}`}>
        <Button className="image-studio-nav previous" shape="circle" disabled={versions.length < 2} aria-label={t('previousImage')} title={t('previousImage')} icon={<ChevronLeftIcon />} onClick={() => setIndex((index - 1 + versions.length) % versions.length)} />
        <img src={selectedSrc} alt={originalPrompt || t('generatedImage')} onLoad={() => {
          loadedUrlsRef.current.add(selected.image_url);
          setLoadedUrls((current) => new Set(current).add(selected.image_url));
          if (generating) MessagePlugin.success(t('imageLoaded'));
          setGenerating(false);
        }} onError={() => { setGenerating(false); MessagePlugin.error(t('imageLoadFailed')); }} />
        {(generating || !imageReady) && <div className="image-painting-overlay"><span /><PaintingStatus /></div>}
        <Button className="image-studio-nav next" shape="circle" disabled={versions.length < 2} aria-label={t('nextImage')} title={t('nextImage')} icon={<ChevronRightIcon />} onClick={() => setIndex((index + 1) % versions.length)} />
      </div>
      <div className="image-studio-prompt" title={originalPrompt}>{originalPrompt}</div>
      <div className="image-studio-editor">
        <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder={editHint} maxLength={2000} />
        <Button theme="primary" loading={generating} disabled={!instruction.trim()} onClick={() => void generateEdit()}>{t('editFromImage')}</Button>
      </div>
      {versions.length > 1 && (
        <div className="image-studio-thumbs">
          {versions.map((version, versionIndex) => (
            <button key={version.id} type="button" className={versionIndex === index ? 'selected' : ''} aria-label={t('imageVersion', { number: versionIndex + 1 })} title={t('imageVersion', { number: versionIndex + 1 })} onClick={() => setIndex(versionIndex)}>
              <img src={downloadCacheRef.current.get(version.image_url)?.objectUrl || withEdgeOneAuth(version.image_url)} alt={t('imageVersion', { number: versionIndex + 1 })} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

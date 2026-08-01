import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button, MessagePlugin } from 'tdesign-react';
import { AddIcon, DeleteIcon, DownloadIcon, EditIcon, FileIcon, FolderIcon, RefreshIcon } from 'tdesign-icons-react';
import { createZip } from '../../../services/zip';
import PaperFullReader from './PaperFullReader';
import { useLanguage } from '../../../i18n';
import { usePapersController } from '../controller/usePapersController';
import { currentAuthSession, ensureAuthSession, openAuthDialog } from '../../../shared/auth/session';
import { readingAccess, type ReadingAccess } from '../model/access';
import type {
  ReadingFolder,
  ReadingSettings,
  SavedPaper,
} from '../model/types';

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ReadingLibraryPanel() {
  const { t } = useLanguage();
  const { api } = usePapersController();
  const {
    createReadingFolder,
    deleteSavedPaper,
    fetchPaperFile,
    getReadingLibrary,
    moveReadingItem,
    preloadPaperFile,
    renameReadingFolder,
  } = api;
  const [items, setItems] = useState<SavedPaper[]>([]);
  const [folders, setFolders] = useState<ReadingFolder[]>([]);
  const [settings, setSettings] = useState<ReadingSettings>({ auto_organize: true });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [busyFolder, setBusyFolder] = useState('');
  const [reader, setReader] = useState<SavedPaper | null>(null);
  const [access, setAccess] = useState<ReadingAccess>(
    () => readingAccess(currentAuthSession()),
  );

  useEffect(() => {
    let disposed = false;
    const update = (session: Parameters<typeof readingAccess>[0]) => {
      if (!disposed) setAccess(readingAccess(session));
    };
    const handleAuthChanged = (event: Event) => {
      update((event as CustomEvent<Parameters<typeof readingAccess>[0]>).detail);
    };
    window.addEventListener('floris:auth-changed', handleAuthChanged);
    void ensureAuthSession().then(update).catch(() => {
      if (!disposed) setAccess('unavailable');
    });
    return () => {
      disposed = true;
      window.removeEventListener('floris:auth-changed', handleAuthChanged);
    };
  }, []);

  const load = useCallback(async () => {
    if (access !== 'available') {
      setLoading(access === 'loading');
      return;
    }
    setLoading(true);
    try {
      const data = await getReadingLibrary();
      setItems(data.papers); setFolders(data.folders); setSettings(data.settings);
      setExpanded((current) => data.folders.reduce((next, folder) => ({ ...next, [folder.id]: current[folder.id] ?? true }), current));
    } catch { MessagePlugin.error(t('readingLoadFailed')); }
    finally { setLoading(false); }
  }, [access, getReadingLibrary, t]);

  useEffect(() => {
    void load(); const refresh = () => { void load(); };
    window.addEventListener('yuanbao:library-changed', refresh);
    return () => window.removeEventListener('yuanbao:library-changed', refresh);
  }, [load]);

  const groups = useMemo(() => {
    const output = folders.map((folder) => ({ folder, items: items.filter((item) => item.folder_id === folder.id) }));
    const unfiled = items.filter((item) => !item.folder_id || !folders.some((folder) => folder.id === item.folder_id));
    if (unfiled.length) output.push({ folder: { id: '', name: t('unfiled'), automatic: false }, items: unfiled });
    return output.filter((group) => group.items.length || group.folder.id);
  }, [folders, items, t]);

  const remove = async (item: SavedPaper) => {
    if (!window.confirm(t('confirmRemoveReading', { name: item.title || item.filename }))) return;
    try {
      const result = await deleteSavedPaper(item.id);
      if (!result.ok) throw new Error(t('deleteNotConfirmed'));
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
      MessagePlugin.success(t('readingRemoved'));
    } catch {
      MessagePlugin.error(t('removeFailed'));
    }
  };
  const createFolder = async () => {
    const name = window.prompt(t('newFolderName')); if (!name?.trim()) return;
    await createReadingFolder(name.trim()); await load();
  };
  const rename = async (folder: ReadingFolder) => {
    const name = window.prompt(t('renameFolder'), folder.name); if (!name?.trim() || name.trim() === folder.name) return;
    await renameReadingFolder(folder.id, name.trim()); await load();
  };
  const downloadFolder = async (folder: ReadingFolder, folderItems: SavedPaper[]) => {
    if (!folderItems.length) return;
    setBusyFolder(folder.id || 'unfiled');
    try {
      const entries = await Promise.all(folderItems.map(async (item, index) => {
        const response = await fetchPaperFile(item.file_id);
        if (!response.ok) throw new Error(t('itemDownloadFailed', { name: item.title }));
        const safe = (item.title || item.filename || t('documentFileName', { number: index + 1 })).replace(/[\\/:*?"<>|]/g, '_');
        return { name: `${safe}.pdf`, data: new Uint8Array(await response.arrayBuffer()) };
      }));
      saveBlob(createZip(entries), `${folder.name}-${Date.now()}.zip`);
    } catch { MessagePlugin.error(t('folderDownloadFailed')); }
    finally { setBusyFolder(''); }
  };
  const warmReader = (item: SavedPaper) => preloadPaperFile(item.file_id, {
    size: item.file_size,
    partSize: item.part_size,
  });

  return <div className="my-panel-card reading-library-card" data-onboarding="reading">
    <div className="section-title">
      <FileIcon size="16px" /> {t('myReading')} <span className="reading-library-count">{items.length}</span>
      {access === 'available' && <>
        <Button shape="circle" variant="text" size="small" icon={<AddIcon />} aria-label={t('newFolder')} title={t('newFolder')} onClick={() => void createFolder()} />
        <Button shape="circle" variant="text" size="small" loading={loading} icon={<RefreshIcon />} aria-label={t('refresh')} title={t('refresh')} onClick={() => void load()} />
      </>}
    </div>
    {access === 'available' && <div className="reading-library-mode">{settings.auto_organize ? t('autoOrganizing') : t('manualOrganize')}</div>}
    {access === 'login_required' ? (
      <div className="reading-library-empty">
        <p>{t('readingLoginRequired')}</p>
        <Button size="small" variant="outline" onClick={openAuthDialog}>{t('readingLoginAction')}</Button>
      </div>
    ) : access === 'unavailable' ? (
      <div className="reading-library-empty">{t('readingLoadFailed')}</div>
    ) : loading && !items.length && !folders.length ? (
      <div className="skeleton-list" role="status" aria-label={t('loading')}>
        {[0, 1].map((row) => (
          <div className="skeleton-reading-item" key={row}>
            <span className="skeleton skeleton-line" style={{ width: '38%' }} aria-hidden="true" />
            <span className="skeleton skeleton-block" aria-hidden="true">
              <span className="skeleton skeleton-line" style={{ width: '82%' }} />
              <span className="skeleton skeleton-line" style={{ width: '58%' }} />
            </span>
          </div>
        ))}
      </div>
    ) : !items.length && !folders.length ? <div className="reading-library-empty">{t('libraryEmpty')}</div> : (
      <div className="reading-folder-list">{groups.map(({ folder, items: folderItems }) => (
        <section className="reading-folder" key={folder.id || 'unfiled'}>
          <div className="reading-folder-header">
            <button type="button" onClick={() => setExpanded((value) => ({ ...value, [folder.id]: !(value[folder.id] ?? true) }))}>
              <FolderIcon /><strong>{folder.name}</strong><span>{folderItems.length}</span>
            </button>
            {folder.id && <Button shape="circle" variant="text" size="small" icon={<EditIcon />} aria-label={t('rename')} title={t('rename')} onClick={() => void rename(folder)} />}
            <Button shape="circle" variant="text" size="small" loading={busyFolder === (folder.id || 'unfiled')} icon={<DownloadIcon />} aria-label={t('downloadFolder')} title={t('downloadFolder')} onClick={() => void downloadFolder(folder, folderItems)} />
          </div>
          {(expanded[folder.id] ?? true) && <div className="reading-library-list">{folderItems.map((item) => (
            <div className="reading-library-item" key={item.id}>
              <button
                type="button"
                className="reading-library-open"
                onPointerEnter={() => warmReader(item)}
                onFocus={() => warmReader(item)}
                onClick={() => setReader(item)}
              >
                <span>{item.is_paper || item.kind === 'paper' ? '📄' : '📑'}</span>
                <span><strong>{item.title || item.filename}</strong><small>{item.is_paper || item.kind === 'paper' ? t('paperAssistant') : t('pdfReading')}{item.page_count ? t('pageCount', { count: item.page_count }) : ''}</small></span>
              </button>
              <select aria-label={t('moveToFolder')} title={settings.auto_organize ? t('manualMoveHint') : t('moveToFolder')} value={item.folder_id || ''} onChange={(event) => void moveReadingItem(item.id, event.target.value).then(load).then(() => MessagePlugin.success(t('fileMoved'))).catch(() => MessagePlugin.error(t('moveFailed')))}>
                <option value="">{t('unfiled')}</option>{folders.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.name}</option>)}
              </select>
              <Button shape="circle" variant="text" size="small" icon={<DeleteIcon />} aria-label={t('remove')} title={t('remove')} onClick={() => void remove(item)} />
            </div>
          ))}</div>}
        </section>
      ))}</div>
    )}
    {reader && createPortal(
      <PaperFullReader
        fileId={reader.file_id}
        title={reader.title || reader.filename}
        arxivId={reader.arxiv_id}
        fileSize={reader.file_size}
        partSize={reader.part_size}
        assistantEnabled={Boolean(reader.is_paper || reader.kind === 'paper')}
        onClose={() => setReader(null)}
      />,
      document.body,
    )}
  </div>;
}

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button, MessagePlugin } from 'tdesign-react';
import { AddIcon, DeleteIcon, DownloadIcon, EditIcon, FileIcon, FolderIcon, RefreshIcon } from 'tdesign-icons-react';
import {
  createReadingFolder, deleteSavedPaper, getReadingLibrary, moveReadingItem,
  fetchPaperFile, renameReadingFolder, type ReadingFolder, type ReadingSettings, type SavedPaper,
} from '../../services/paperApi';
import { createZip } from '../../services/zip';
import PaperFullReader from '../paper/PaperFullReader';

function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function ReadingLibraryPanel() {
  const [items, setItems] = useState<SavedPaper[]>([]);
  const [folders, setFolders] = useState<ReadingFolder[]>([]);
  const [settings, setSettings] = useState<ReadingSettings>({ auto_organize: true });
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(false);
  const [busyFolder, setBusyFolder] = useState('');
  const [reader, setReader] = useState<SavedPaper | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getReadingLibrary();
      setItems(data.papers); setFolders(data.folders); setSettings(data.settings);
      setExpanded((current) => data.folders.reduce((next, folder) => ({ ...next, [folder.id]: current[folder.id] ?? true }), current));
    } catch (error) { MessagePlugin.error(error instanceof Error ? error.message : '读取我的阅读失败'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    void load(); const refresh = () => { void load(); };
    window.addEventListener('yuanbao:library-changed', refresh);
    return () => window.removeEventListener('yuanbao:library-changed', refresh);
  }, [load]);

  const groups = useMemo(() => {
    const output = folders.map((folder) => ({ folder, items: items.filter((item) => item.folder_id === folder.id) }));
    const unfiled = items.filter((item) => !item.folder_id || !folders.some((folder) => folder.id === item.folder_id));
    if (unfiled.length) output.push({ folder: { id: '', name: '未分类', automatic: false }, items: unfiled });
    return output.filter((group) => group.items.length || group.folder.id);
  }, [folders, items]);

  const remove = async (item: SavedPaper) => {
    if (!window.confirm(`确定从“我的阅读”移除“${item.title || item.filename}”吗？`)) return;
    try {
      const result = await deleteSavedPaper(item.id);
      if (!result.ok) throw new Error('服务端未确认删除');
      setItems((current) => current.filter((candidate) => candidate.id !== item.id));
      MessagePlugin.success('已从“我的阅读”移除');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '移除失败');
    }
  };
  const createFolder = async () => {
    const name = window.prompt('新文件夹名称'); if (!name?.trim()) return;
    await createReadingFolder(name.trim()); await load();
  };
  const rename = async (folder: ReadingFolder) => {
    const name = window.prompt('重命名文件夹', folder.name); if (!name?.trim() || name.trim() === folder.name) return;
    await renameReadingFolder(folder.id, name.trim()); await load();
  };
  const downloadFolder = async (folder: ReadingFolder, folderItems: SavedPaper[]) => {
    if (!folderItems.length) return;
    setBusyFolder(folder.id || 'unfiled');
    try {
      const entries = await Promise.all(folderItems.map(async (item, index) => {
        const response = await fetchPaperFile(item.file_id);
        if (!response.ok) throw new Error(`“${item.title}”下载失败`);
        const safe = (item.title || item.filename || `文档-${index + 1}`).replace(/[\\/:*?"<>|]/g, '_');
        return { name: `${safe}.pdf`, data: new Uint8Array(await response.arrayBuffer()) };
      }));
      saveBlob(createZip(entries), `${folder.name}-${Date.now()}.zip`);
    } catch (error) { MessagePlugin.error(error instanceof Error ? error.message : '下载文件夹失败'); }
    finally { setBusyFolder(''); }
  };

  return <div className="my-panel-card reading-library-card">
    <div className="section-title">
      <FileIcon size="16px" /> 我的阅读 <span className="reading-library-count">{items.length}</span>
      <Button shape="circle" variant="text" size="small" icon={<AddIcon />} aria-label="新建文件夹" onClick={() => void createFolder()} />
      <Button shape="circle" variant="text" size="small" loading={loading} icon={<RefreshIcon />} aria-label="刷新" onClick={() => void load()} />
    </div>
    <div className="reading-library-mode">{settings.auto_organize ? '自动整理中' : '手动整理'}</div>
    {!items.length && !folders.length ? <div className="reading-library-empty">上传 PDF 后会自动按类型整理；论文会启用助读。</div> : (
      <div className="reading-folder-list">{groups.map(({ folder, items: folderItems }) => (
        <section className="reading-folder" key={folder.id || 'unfiled'}>
          <div className="reading-folder-header">
            <button type="button" onClick={() => setExpanded((value) => ({ ...value, [folder.id]: !(value[folder.id] ?? true) }))}>
              <FolderIcon /><strong>{folder.name}</strong><span>{folderItems.length}</span>
            </button>
            {folder.id && <Button shape="circle" variant="text" size="small" icon={<EditIcon />} aria-label="重命名" onClick={() => void rename(folder)} />}
            <Button shape="circle" variant="text" size="small" loading={busyFolder === (folder.id || 'unfiled')} icon={<DownloadIcon />} aria-label="下载文件夹" onClick={() => void downloadFolder(folder, folderItems)} />
          </div>
          {(expanded[folder.id] ?? true) && <div className="reading-library-list">{folderItems.map((item) => (
            <div className="reading-library-item" key={item.id}>
              <button type="button" className="reading-library-open" onClick={() => setReader(item)}>
                <span>{item.is_paper || item.kind === 'paper' ? '📄' : '📑'}</span>
                <span><strong>{item.title || item.filename}</strong><small>{item.is_paper || item.kind === 'paper' ? '论文助读' : 'PDF 阅读'}{item.page_count ? ` · ${item.page_count} 页` : ''}</small></span>
              </button>
              <select aria-label="移动到文件夹" title={settings.auto_organize ? '手动移动后将保留你的选择' : '移动到文件夹'} value={item.folder_id || ''} onChange={(event) => void moveReadingItem(item.id, event.target.value).then(load).then(() => MessagePlugin.success('文件已移动')).catch((error) => MessagePlugin.error(error instanceof Error ? error.message : '移动失败'))}>
                <option value="">未分类</option>{folders.map((candidate) => <option value={candidate.id} key={candidate.id}>{candidate.name}</option>)}
              </select>
              <Button shape="circle" variant="text" size="small" icon={<DeleteIcon />} aria-label="移除" onClick={() => void remove(item)} />
            </div>
          ))}</div>}
        </section>
      ))}</div>
    )}
    {reader && createPortal(
      <PaperFullReader fileId={reader.file_id} title={reader.title || reader.filename} arxivId={reader.arxiv_id} assistantEnabled={Boolean(reader.is_paper || reader.kind === 'paper')} onClose={() => setReader(null)} />,
      document.body,
    )}
  </div>;
}

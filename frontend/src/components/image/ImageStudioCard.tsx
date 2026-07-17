import { useEffect, useMemo, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { DownloadIcon } from 'tdesign-icons-react';
import { streamImageEdit } from '../../services/api';
import { withEdgeOneAuth } from '../../services/auth';
import { createZip } from '../../services/zip';
import type { WorkspaceAction } from '../../types';

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

export default function ImageStudioCard({ action, conversationId, onUpdated }: Props) {
  const [currentAction, setCurrentAction] = useState(action);
  const [index, setIndex] = useState(0);
  const [instruction, setInstruction] = useState('');
  const [generating, setGenerating] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const versions = useMemo(() => versionsFrom(currentAction), [currentAction]);
  const selected = versions[Math.min(index, Math.max(0, versions.length - 1))];
  const editHint = selected?.prompt
    ? `继续修改“${selected.prompt.slice(0, 36)}${selected.prompt.length > 36 ? '…' : ''}”，例如保留主体并调整背景、动作或画风`
    : '描述希望保留和改变的部分';

  useEffect(() => {
    setCurrentAction(action);
    const next = versionsFrom(action);
    setIndex(Math.max(0, next.length - 1));
  }, [action]);

  const generateEdit = async () => {
    const prompt = instruction.trim();
    if (!prompt || !selected) return;
    setGenerating(true);
    try {
      const action = await streamImageEdit(conversationId, prompt, selected.id);
      setCurrentAction(action);
      onUpdated(action);
      const next = versionsFrom(action);
      setIndex(Math.max(0, next.length - 1));
      setInstruction('');
      if (action.status === 'failed') throw new Error(action.error || '修改图片失败');
      MessagePlugin.success('已生成新的图片版本');
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '修改图片失败');
    } finally {
      setGenerating(false);
    }
  };

  const downloadOne = async () => {
    if (!selected) return;
    try {
      const response = await fetch(withEdgeOneAuth(selected.image_url));
      if (!response.ok) throw new Error('下载图片失败');
      saveBlob(await response.blob(), `元宝图片-${index + 1}.png`);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '下载图片失败');
    }
  };

  const downloadAll = async () => {
    if (!versions.length) return;
    setDownloading(true);
    try {
      const entries = await Promise.all(versions.map(async (version, versionIndex) => {
        const response = await fetch(withEdgeOneAuth(version.image_url));
        if (!response.ok) throw new Error(`第 ${versionIndex + 1} 张图片下载失败`);
        return { name: `元宝图片-${versionIndex + 1}.png`, data: new Uint8Array(await response.arrayBuffer()) };
      }));
      saveBlob(createZip(entries), `元宝图片组-${Date.now()}.zip`);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '批量下载失败');
    } finally {
      setDownloading(false);
    }
  };

  if (currentAction.status === 'executing') {
    return <div className="image-studio-card image-studio-loading">正在生成图片…</div>;
  }
  if (!versions.length) {
    return <div className="image-studio-card image-studio-error">生成失败：{currentAction.error || '未返回图片'}</div>;
  }

  return (
    <div className="image-studio-card">
      <div className="image-studio-header">
        <div><strong>图片工坊</strong><span>{index + 1} / {versions.length}</span></div>
        <div className="image-studio-downloads">
          <Button size="small" variant="text" icon={<DownloadIcon />} onClick={() => void downloadOne()}>下载</Button>
          <Button size="small" variant="outline" loading={downloading} onClick={() => void downloadAll()}>批量下载</Button>
        </div>
      </div>
      <div className={`image-studio-stage ${generating ? 'is-painting' : ''}`}>
        <Button className="image-studio-nav previous" shape="circle" disabled={versions.length < 2} aria-label="上一张" onClick={() => setIndex((index - 1 + versions.length) % versions.length)}>{'<'}</Button>
        <img src={withEdgeOneAuth(selected.image_url)} alt={selected.prompt || '生成图片'} />
        {generating && <div className="image-painting-overlay"><span /><em>正在绘制新版本</em></div>}
        <Button className="image-studio-nav next" shape="circle" disabled={versions.length < 2} aria-label="下一张" onClick={() => setIndex((index + 1) % versions.length)}>{'>'}</Button>
      </div>
      <div className="image-studio-prompt" title={selected.prompt}>{selected.prompt}</div>
      <div className="image-studio-editor">
        <textarea value={instruction} onChange={(event) => setInstruction(event.target.value)} placeholder={editHint} maxLength={2000} />
        <Button theme="primary" loading={generating} disabled={!instruction.trim()} onClick={() => void generateEdit()}>基于此图修改</Button>
      </div>
      {versions.length > 1 && (
        <div className="image-studio-thumbs">
          {versions.map((version, versionIndex) => (
            <button key={version.id} type="button" className={versionIndex === index ? 'selected' : ''} onClick={() => setIndex(versionIndex)}>
              <img src={withEdgeOneAuth(version.image_url)} alt={`版本 ${versionIndex + 1}`} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

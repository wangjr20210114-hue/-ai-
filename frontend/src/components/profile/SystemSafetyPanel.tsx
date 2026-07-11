import { useEffect, useRef, useState } from 'react';
import { Button, MessagePlugin, Tag } from 'tdesign-react';
import {
  downloadSystemBackup,
  getSystemHealth,
  stageSystemRestore,
} from '../../services/api';
import type { SystemHealth } from '../../types';

function statusTheme(status?: string): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'ok' || status === 'ready' || status === 'enabled' || status === 'idle') return 'success';
  if (status === 'error' || status === 'unhealthy') return 'danger';
  if (status === 'degraded' || status === 'restart_required' || status === 'not_configured') return 'warning';
  return 'default';
}

/** Local-only diagnostics and restart-safe backup/restore controls. */
export default function SystemSafetyPanel() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [busy, setBusy] = useState<'backup' | 'restore' | ''>('');
  const inputRef = useRef<HTMLInputElement | null>(null);

  const refresh = async () => {
    try {
      setHealth(await getSystemHealth());
    } catch (error) {
      console.warn('system health refresh failed', error);
      setHealth(null);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const exportBackup = async () => {
    setBusy('backup');
    try {
      const filename = await downloadSystemBackup();
      MessagePlugin.success(`备份已生成：${filename}`);
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '生成备份失败');
    } finally {
      setBusy('');
    }
  };

  const restoreBackup = async (file?: File) => {
    if (!file) return;
    setBusy('restore');
    try {
      const result = await stageSystemRestore(file);
      MessagePlugin.warning(
        result.restart_required
          ? `备份校验通过，已暂存 ${result.file_count} 个文件；重启后恢复生效`
          : '备份已恢复',
      );
      await refresh();
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : '恢复备份失败');
    } finally {
      setBusy('');
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <div className="my-panel-card" data-testid="system-safety-panel">
      <div className="section-title" style={{ marginBottom: 8 }}>
        <span style={{ marginRight: 6 }}>🛡️</span>
        系统安全与恢复
        <Tag
          size="small"
          theme={statusTheme(health?.status)}
          variant="light"
          style={{ marginLeft: 'auto' }}
        >
          {health?.status || '未知'}
        </Tag>
      </div>

      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <Button size="small" variant="outline" loading={busy === 'backup'} onClick={() => { void exportBackup(); }}>
          导出完整备份
        </Button>
        <Button size="small" variant="outline" loading={busy === 'restore'} onClick={() => inputRef.current?.click()}>
          校验并恢复
        </Button>
        <Button size="small" variant="text" onClick={() => { void refresh(); }}>健康检查</Button>
        <input
          ref={inputRef}
          type="file"
          accept=".zip,application/zip"
          hidden
          onChange={(event) => { void restoreBackup(event.target.files?.[0]); }}
        />
      </div>

      <div style={{ marginTop: 7, fontSize: 10.5, color: 'var(--app-text-3)', lineHeight: 1.5 }}>
        <div>
          Supervisor：{health?.components.supervisor?.status || '-'}；数据库：{health?.components.database?.status || '-'}；模型：{health?.components.model?.status || '-'}
        </div>
        <div>恢复采用重启前原子替换，且自动保存恢复前安全副本。备份不包含 API Key、.env 或本地访问令牌。</div>
        {health?.components.restore?.status === 'restart_required' ? (
          <div style={{ color: 'var(--td-warning-color)', marginTop: 3 }}>已有恢复包等待应用，请关闭并重新启动后端。</div>
        ) : null}
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { Button, Dialog, MessagePlugin } from 'tdesign-react';
import { SettingIcon } from 'tdesign-icons-react';
import { getReadingLibrary, updateReadingSettings } from '../../services/paperApi';

export default function LibrarySettingsButton() {
  const [visible, setVisible] = useState(false);
  const [automatic, setAutomatic] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (visible) void getReadingLibrary().then((data) => setAutomatic(data.settings.auto_organize)).catch(() => undefined); }, [visible]);
  const save = async () => {
    setSaving(true);
    try {
      await updateReadingSettings(automatic);
      MessagePlugin.success(automatic ? '已开启自动整理' : '已切换为手动整理');
      setVisible(false);
    } catch (error) { MessagePlugin.error(error instanceof Error ? error.message : '保存设置失败'); }
    finally { setSaving(false); }
  };
  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<SettingIcon />} onClick={() => setVisible(true)}>设置</Button>
    <Dialog visible={visible} header="阅读整理设置" confirmBtn={{ content: '保存', loading: saving }} onConfirm={() => void save()} onCancel={() => setVisible(false)}>
      <div className="library-settings-options">
        <label><input type="radio" checked={automatic} onChange={() => setAutomatic(true)} /><span><strong>自动整理（默认）</strong><small>根据论文、报告、手册等文档类型自动创建文件夹。</small></span></label>
        <label><input type="radio" checked={!automatic} onChange={() => setAutomatic(false)} /><span><strong>手动添加</strong><small>新文档先进入“未分类”，由你选择文件夹。</small></span></label>
      </div>
    </Dialog>
  </>;
}

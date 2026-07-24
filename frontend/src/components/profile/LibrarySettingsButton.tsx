import { useEffect, useState } from 'react';
import { Button, Dialog, MessagePlugin } from 'tdesign-react';
import { SettingIcon } from 'tdesign-icons-react';
import { getReadingLibrary, updateReadingSettings } from '../../services/paperApi';
import { useLanguage } from '../../i18n';

export default function LibrarySettingsButton() {
  const { t } = useLanguage();
  const [visible, setVisible] = useState(false);
  const [automatic, setAutomatic] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (visible) void getReadingLibrary().then((data) => setAutomatic(data.settings.auto_organize)).catch(() => undefined); }, [visible]);
  const save = async () => {
    setSaving(true);
    try {
      await updateReadingSettings(automatic);
      MessagePlugin.success(automatic ? t('readingAutoEnabled') : t('readingManualEnabled'));
      setVisible(false);
    } catch (error) { MessagePlugin.error(error instanceof Error ? error.message : t('settingsSaveFailed')); }
    finally { setSaving(false); }
  };
  return <>
    <Button className="sidebar-settings-button" block variant="text" icon={<SettingIcon />} onClick={() => setVisible(true)}>{t('settings')}</Button>
    <Dialog visible={visible} header={t('readingOrganizationSettings')} confirmBtn={{ content: t('save'), loading: saving }} onConfirm={() => void save()} onCancel={() => setVisible(false)}>
      <div className="library-settings-options">
        <label><input type="radio" checked={automatic} onChange={() => setAutomatic(true)} /><span><strong>{t('autoOrganizeDefault')}</strong><small>{t('autoOrganizeDetail')}</small></span></label>
        <label><input type="radio" checked={!automatic} onChange={() => setAutomatic(false)} /><span><strong>{t('manualAdd')}</strong><small>{t('manualAddDetail')}</small></span></label>
      </div>
    </Dialog>
  </>;
}

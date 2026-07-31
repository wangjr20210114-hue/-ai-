import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MessagePlugin } from 'tdesign-react';

import { useLanguage } from '../../i18n';
import {
  configureSkillConnection,
  downloadSkillPackage,
  listSkillUploads,
  skillMarketplaceOperation,
  skillsOperation,
  uploadSkillPackage,
} from '../../services/api';
import { currentAuthSession, startWechatLogin } from '../../services/auth';
import { useAppState } from '../../store/appState';
import type {
  InstalledSkill,
  SkillConnectionState,
  SkillMarketplaceState,
  SkillUploadRecord,
} from '../../types';
import {
  filterMarketplaceSkills,
  localizedSkillText,
  type MarketplaceView,
  skillIsInstalled,
} from './model';


export function useSkillMarketplaceController() {
  const { conversationId } = useAppState();
  const { t, language } = useLanguage();
  const [visible, setVisible] = useState(false);
  const [view, setView] = useState<MarketplaceView>('catalog');
  const [marketplace, setMarketplace] = useState<SkillMarketplaceState | null>(null);
  const [preferences, setPreferences] = useState<Record<string, boolean>>({});
  const [connections, setConnections] = useState<Record<string, SkillConnectionState>>({});
  const [uploads, setUploads] = useState<SkillUploadRecord[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState('');
  const [tokenDrafts, setTokenDrafts] = useState<Record<string, string>>({});
  const uploadRef = useRef<HTMLInputElement>(null);
  const suppressOpenUntilRef = useRef(0);
  const wechatAvailable = currentAuthSession()?.login.wechat_available === true;

  const catalog = useMemo(
    () => marketplace?.skills || [],
    [marketplace?.skills],
  );
  const skillText = useCallback((
    values: Record<string, string> | undefined,
    fallback: string,
  ) => localizedSkillText(values, fallback, language), [language]);
  const skillName = useCallback((skillId: string) => {
    const skill = catalog.find((item) => item.id === skillId);
    return skill ? skillText(skill.name, skill.id) : skillId;
  }, [catalog, skillText]);
  const isInstalled = useCallback(
    (skill: InstalledSkill) => skillIsInstalled(skill, preferences),
    [preferences],
  );

  const refresh = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    try {
      const result = await skillMarketplaceOperation(conversationId);
      setMarketplace(result);
      setPreferences(result.preferences);
      setConnections(result.connections || {});
      setUploads(
        result.identity.auth_type !== 'guest'
          ? await listSkillUploads().catch(() => [])
          : [],
      );
      return true;
    } catch {
      MessagePlugin.error(t('skillsReadFailed'));
      return false;
    } finally {
      setLoading(false);
    }
  }, [conversationId, t]);

  const openMarketplace = useCallback(() => {
    if (Date.now() < suppressOpenUntilRef.current) return;
    setVisible(true);
    setView('catalog');
    void refresh();
  }, [refresh]);
  const closeMarketplace = useCallback(() => {
    // A full-screen layer can disappear while the browser is still
    // dispatching the originating pointer event. Ignore any click-through
    // reopen during that same interaction.
    suppressOpenUntilRef.current = Date.now() + 400;
    setVisible(false);
  }, []);

  useEffect(() => {
    const open = () => openMarketplace();
    window.addEventListener('yuanbao:open-skills', open);
    return () => window.removeEventListener('yuanbao:open-skills', open);
  }, [openMarketplace]);

  useEffect(() => {
    if (!visible) return undefined;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMarketplace();
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [closeMarketplace, visible]);

  const enabledCount = useMemo(
    () => catalog.filter(isInstalled).length,
    [catalog, isInstalled],
  );
  const visibleSkills = useMemo(
    () => filterMarketplaceSkills(catalog, {
      view,
      query,
      language,
      preferences,
    }),
    [catalog, language, preferences, query, view],
  );

  const save = async (skill: InstalledSkill, enabled: boolean) => {
    if (skill.locked) return;
    if (!skill.eligible) {
      if (skill.eligibility_reason === 'login_required' && wechatAvailable) {
        startWechatLogin('/chatBot');
      } else if (skill.eligibility_reason === 'login_required') {
        MessagePlugin.warning(t('wechatLoginUnavailable'));
      }
      else MessagePlugin.warning(t('membershipRequired'));
      return;
    }
    const next = { ...preferences, [skill.id]: enabled };
    const autoEnabled = enabled
      ? (skill.requires || []).filter((dependency) => next[dependency] === false)
      : [];
    autoEnabled.forEach((dependency) => { next[dependency] = true; });
    setSavingId(skill.id);
    try {
      const result = await skillsOperation(conversationId, next);
      setPreferences(result.preferences);
      setConnections(result.connections);
      window.dispatchEvent(new CustomEvent('yuanbao:skills-changed', {
        detail: result.preferences,
      }));
      await refresh();
      MessagePlugin.success(
        autoEnabled.length
          ? t('skillsDependenciesEnabled', {
            names: autoEnabled.map(skillName).join('、'),
          })
          : t(enabled ? 'skillInstalled' : 'skillUninstalled', {
            name: skillText(skill.name, skill.id),
          }),
      );
    } catch {
      MessagePlugin.error(t('skillsSaveFailed'));
    } finally {
      setSavingId('');
    }
  };

  const saveConnection = async (skillId: string) => {
    const token = String(tokenDrafts[skillId] || '').trim();
    if (!token) return;
    setSavingId(skillId);
    try {
      const state = await configureSkillConnection(conversationId, skillId, token);
      setConnections(state.skill_connections || {});
      setTokenDrafts((current) => ({ ...current, [skillId]: '' }));
      await refresh();
      MessagePlugin.success(t('skillTokenSaved'));
    } catch {
      MessagePlugin.error(t('skillTokenSaveFailed'));
    } finally {
      setSavingId('');
    }
  };

  const disconnect = async (skillId: string) => {
    setSavingId(skillId);
    try {
      const state = await configureSkillConnection(conversationId, skillId);
      setConnections(state.skill_connections || {});
      await refresh();
      MessagePlugin.success(t('skillDisconnected'));
    } catch {
      MessagePlugin.error(t('skillTokenSaveFailed'));
    } finally {
      setSavingId('');
    }
  };

  const upload = async (file?: File) => {
    if (!file) return;
    setSavingId('upload');
    try {
      const record = await uploadSkillPackage(file);
      setUploads((current) => [
        record,
        ...current.filter((item) => item.id !== record.id),
      ]);
      MessagePlugin.success(t('skillUploadSubmitted'));
    } catch (error) {
      MessagePlugin.error(String(
        (error as Error)?.message || t('skillUploadFailed'),
      ));
    } finally {
      setSavingId('');
      if (uploadRef.current) uploadRef.current.value = '';
    }
  };

  const download = async (skillId: string) => {
    try {
      await downloadSkillPackage(conversationId, skillId);
    } catch {
      MessagePlugin.error(t('skillDownloadFailed'));
    }
  };

  return {
    catalog,
    closeMarketplace,
    connections,
    disconnect,
    download,
    enabledCount,
    isInstalled,
    language,
    loading,
    login: () => {
      if (wechatAvailable) startWechatLogin('/chatBot');
      else MessagePlugin.warning(t('wechatLoginUnavailable'));
    },
    marketplace,
    openMarketplace,
    preferences,
    query,
    refresh,
    save,
    saveConnection,
    savingId,
    setQuery,
    setTokenDrafts,
    setView,
    skillName,
    skillText,
    t,
    tokenDrafts,
    upload,
    uploadRef,
    uploads,
    view,
    visible,
    visibleSkills,
    wechatAvailable,
  };
}

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { MessagePlugin } from 'tdesign-react';

import { useLanguage } from '../../../i18n';
import {
  downloadSkillPackage,
  listSkillUploads,
  skillMarketplaceOperation,
} from '../model/client';
import { marketplaceAccount, syncMarketplaceAuth } from '../model/authSync';
import { usePrivateSkillsController } from './usePrivateSkillsController';
import { intelligenceOperation } from '../../settings/model/client';
import {
  type AuthSession,
  currentAuthSession,
  openAuthDialog,
} from '../../../shared/auth/session';
import { useAppState } from '../../../store/appState';
import type {
  InstalledSkill,
  SkillConnectionState,
  SkillMarketplaceState,
} from '../../../shared/types';
import {
  filterMarketplaceSkills,
  localizedSkillText,
  type MarketplaceView,
  skillIsInstalled,
} from '../model';


async function skillsOperation(
  conversationId: string,
  preferences?: Record<string, boolean>,
) {
  const intelligence = await intelligenceOperation(
    conversationId,
    preferences ? 'update_skill_preferences' : 'get',
    preferences ? { preferences } : {},
  );
  return {
    preferences: intelligence.skill_preferences || {},
    providers: intelligence.providers || {},
    catalog: intelligence.skill_catalog || [],
    connections: intelligence.skill_connections || {},
  };
}

function configureSkillConnection(
  conversationId: string,
  skillId: string,
  token?: string,
) {
  return intelligenceOperation(
    conversationId,
    token ? 'configure_skill_connection' : 'disconnect_skill_connection',
    token ? { skill_id: skillId, token } : { skill_id: skillId },
  );
}


export function useSkillMarketplaceController() {
  const { conversationId } = useAppState();
  const { t, language } = useLanguage();
  const [visible, setVisible] = useState(false);
  const [view, setView] = useState<MarketplaceView>('catalog');
  const [marketplace, setMarketplace] = useState<SkillMarketplaceState | null>(null);
  const [authSession, setAuthSession] = useState<AuthSession | null>(
    () => currentAuthSession(),
  );
  const [preferences, setPreferences] = useState<Record<string, boolean>>({});
  const [connections, setConnections] = useState<Record<string, SkillConnectionState>>({});
  const privateSkills = usePrivateSkillsController(conversationId);
  const { setUploads, setUserSkills, uploads, userSkills } = privateSkills;
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState('');
  const [tokenDrafts, setTokenDrafts] = useState<Record<string, string>>({});
  const suppressOpenUntilRef = useRef(0);
  const refreshSequenceRef = useRef(0);

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
    const sequence = ++refreshSequenceRef.current;
    setLoading(true);
    try {
      const result = await skillMarketplaceOperation(conversationId);
      if (sequence !== refreshSequenceRef.current) return false;
      setMarketplace(result);
      setPreferences(result.preferences);
      setConnections(result.connections || {});
      setUserSkills(result.user_skills || []);
      const nextUploads = (
        result.identity.auth_type !== 'guest'
          ? await listSkillUploads().catch(() => [])
          : []
      );
      if (sequence !== refreshSequenceRef.current) return false;
      setUploads(nextUploads);
      return true;
    } catch {
      MessagePlugin.error(t('skillsReadFailed'));
      return false;
    } finally {
      if (sequence === refreshSequenceRef.current) setLoading(false);
    }
  }, [conversationId, setUploads, setUserSkills, t]);

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
    const changed = (event: Event) => {
      const session = (event as CustomEvent<AuthSession>).detail;
      setAuthSession(session);
      setMarketplace((current) => syncMarketplaceAuth(current, session));
      if (session.identity.auth_type === 'guest') {
        setUploads([]);
        setUserSkills([]);
      }
      if (visible) void refresh();
    };
    window.addEventListener('floris:auth-changed', changed);
    return () => window.removeEventListener('floris:auth-changed', changed);
  }, [refresh, setUploads, setUserSkills, visible]);

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
  const account = marketplaceAccount(marketplace, authSession);

  const save = async (skill: InstalledSkill, enabled: boolean) => {
    if (skill.locked) return;
    if (!skill.eligible) {
      if (skill.eligibility_reason === 'login_required') openAuthDialog();
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

  const download = async (skillId: string) => {
    try {
      await downloadSkillPackage(conversationId, skillId);
    } catch {
      MessagePlugin.error(t('skillDownloadFailed'));
    }
  };

  return {
    accountIdentity: account.identity,
    accountPlan: account.plan,
    catalog,
    closeMarketplace,
    connections,
    disconnect,
    download,
    enabledCount,
    isInstalled,
    language,
    loading,
    login: openAuthDialog,
    loginLabel: t('authSignIn'),
    marketplace,
    openMarketplace,
    preferences,
    query,
    refresh,
    save,
    saveConnection,
    savingId: savingId || privateSkills.savingId,
    setQuery,
    setTokenDrafts,
    setView,
    skillName,
    skillText,
    t,
    tokenDrafts,
    importFile: privateSkills.importFile,
    importFolder: privateSkills.importFolder,
    importText: privateSkills.importText,
    importUrl: privateSkills.importUrl,
    publishArchive: privateSkills.publishArchive,
    publishUserSkill: privateSkills.publishUserSkill,
    removeUserSkill: privateSkills.removeUserSkill,
    setUserSkillEnabled: privateSkills.setUserSkillEnabled,
    uploadArchive: privateSkills.uploadArchive,
    uploadRef: privateSkills.uploadRef,
    uploads,
    userSkills,
    view,
    visible,
    visibleSkills,
  };
}

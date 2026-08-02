import { useRef, useState } from 'react';
import { MessagePlugin } from 'tdesign-react';

import { useLanguage } from '../../../i18n';
import type { SkillUploadRecord, UserSkillRecord } from '../../../shared/types';
import { intelligenceOperation } from '../../settings/model/client';
import {
  requestMarketplaceReview,
  requestUserSkillMarketplaceReview,
  uploadPrivateSkillPackage,
} from '../model/client';
import {
  parseUserSkillText,
  readUserSkillFile,
  readUserSkillFolder,
  readUserSkillUrl,
  type UserSkillDraft,
} from '../model/userSkillImport';

export function usePrivateSkillsController(conversationId: string) {
  const { t } = useLanguage();
  const [uploads, setUploads] = useState<SkillUploadRecord[]>([]);
  const [userSkills, setUserSkills] = useState<UserSkillRecord[]>([]);
  const [savingId, setSavingId] = useState('');
  const uploadRef = useRef<HTMLInputElement>(null);

  const reportError = (error: unknown) => {
    MessagePlugin.error(String((error as Error)?.message || t('skillUploadFailed')));
  };

  const installDraft = async (draft: UserSkillDraft) => {
    setSavingId('private-skill');
    try {
      const state = await intelligenceOperation(
        conversationId,
        'install_user_skill',
        { skill: draft },
      );
      setUserSkills(state.user_skills || []);
      MessagePlugin.success(t('skillPrivateInstalled', { name: draft.name }));
      return true;
    } catch (error) {
      reportError(error);
      return false;
    } finally {
      setSavingId('');
    }
  };

  const importResolved = async (loader: () => Promise<UserSkillDraft>) => {
    try { return await installDraft(await loader()); }
    catch (error) {
      reportError(error);
      return false;
    }
  };

  const importFile = (file?: File) => (
    file ? importResolved(() => readUserSkillFile(file)) : Promise.resolve(false)
  );
  const importFolder = (files?: FileList | null) => (
    files?.length ? importResolved(() => readUserSkillFolder(files)) : Promise.resolve(false)
  );
  const importText = (value: string) => importResolved(
    () => Promise.resolve(parseUserSkillText(value)),
  );
  const importUrl = (value: string) => importResolved(() => readUserSkillUrl(value));

  const uploadArchive = async (file?: File) => {
    if (!file) return;
    setSavingId('archive');
    try {
      const record = await uploadPrivateSkillPackage(file);
      setUploads((current) => [
        record,
        ...current.filter((item) => item.id !== record.id),
      ]);
      MessagePlugin.success(t('skillPrivateArchiveStored'));
    } catch (error) {
      reportError(error);
    } finally {
      setSavingId('');
      if (uploadRef.current) uploadRef.current.value = '';
    }
  };

  const setUserSkillEnabled = async (skillId: string, enabled: boolean) => {
    setSavingId(skillId);
    try {
      const state = await intelligenceOperation(
        conversationId,
        'set_user_skill_enabled',
        { skill_id: skillId, enabled },
      );
      setUserSkills(state.user_skills || []);
      MessagePlugin.success(t(enabled ? 'skillEnabled' : 'skillDisabled'));
    } catch {
      MessagePlugin.error(t('skillsSaveFailed'));
    } finally {
      setSavingId('');
    }
  };

  const removeUserSkill = async (skillId: string) => {
    setSavingId(skillId);
    try {
      const state = await intelligenceOperation(
        conversationId,
        'remove_user_skill',
        { skill_id: skillId },
      );
      setUserSkills(state.user_skills || []);
      MessagePlugin.success(t('skillPrivateRemoved'));
    } catch {
      MessagePlugin.error(t('skillsSaveFailed'));
    } finally {
      setSavingId('');
    }
  };

  const publishArchive = async (uploadId: string) => {
    setSavingId(uploadId);
    try {
      const record = await requestMarketplaceReview(uploadId);
      setUploads((current) => current.map((item) => item.id === record.id ? record : item));
      MessagePlugin.success(t('skillMarketplaceReviewRequested'));
    } catch (error) {
      reportError(error);
    } finally {
      setSavingId('');
    }
  };

  const publishUserSkill = async (skill: UserSkillRecord) => {
    setSavingId(skill.id);
    try {
      const record = await requestUserSkillMarketplaceReview(skill);
      setUploads((current) => [
        record,
        ...current.filter((item) => item.id !== record.id),
      ]);
      MessagePlugin.success(t('skillMarketplaceReviewRequested'));
    } catch (error) {
      reportError(error);
    } finally {
      setSavingId('');
    }
  };

  return {
    importFile,
    importFolder,
    importText,
    importUrl,
    publishArchive,
    publishUserSkill,
    removeUserSkill,
    savingId,
    setUploads,
    setUserSkillEnabled,
    setUserSkills,
    uploadArchive,
    uploadRef,
    uploads,
    userSkills,
  };
}

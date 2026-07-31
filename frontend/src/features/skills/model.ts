import type { InstalledSkill } from '../../types';

export type MarketplaceView = 'catalog' | 'installed' | 'dependencies' | 'docs' | 'upload';

export function localizedSkillText(
  values: Record<string, string> | undefined,
  fallback: string,
  language: string,
): string {
  return values?.[language] || values?.['zh-CN'] || values?.en || fallback;
}

export function skillIsInstalled(
  skill: InstalledSkill,
  preferences: Record<string, boolean>,
): boolean {
  return skill.installed ?? (skill.locked || preferences[skill.id] !== false);
}

export function filterMarketplaceSkills(
  catalog: InstalledSkill[],
  options: {
    view: MarketplaceView;
    query: string;
    language: string;
    preferences: Record<string, boolean>;
  },
): InstalledSkill[] {
  const normalized = options.query.trim().toLocaleLowerCase(options.language);
  return catalog.filter((skill) => {
    if (
      options.view === 'installed'
      && !skillIsInstalled(skill, options.preferences)
    ) return false;
    if (!normalized) return true;
    return [
      skill.id,
      localizedSkillText(skill.name, '', options.language),
      localizedSkillText(skill.description, '', options.language),
      skill.publisher?.name || '',
    ].some((value) => value.toLocaleLowerCase(options.language).includes(normalized));
  });
}

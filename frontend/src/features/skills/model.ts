import type { InstalledSkill } from '../../shared/types';

export type MarketplaceView = 'catalog' | 'enabled' | 'docs' | 'upload';

export const SKILL_CATEGORY_ORDER = [
  'foundation',
  'knowledge',
  'creative',
  'productivity',
  'location',
  'other',
] as const;

export function groupMarketplaceSkills(catalog: InstalledSkill[]) {
  const groups = new Map<string, InstalledSkill[]>();
  for (const skill of catalog) {
    const category = String(skill.category || 'other');
    groups.set(category, [...(groups.get(category) || []), skill]);
  }
  return [...groups.entries()].sort(([left], [right]) => {
    const leftIndex = SKILL_CATEGORY_ORDER.indexOf(left as typeof SKILL_CATEGORY_ORDER[number]);
    const rightIndex = SKILL_CATEGORY_ORDER.indexOf(right as typeof SKILL_CATEGORY_ORDER[number]);
    return (leftIndex < 0 ? 999 : leftIndex) - (rightIndex < 0 ? 999 : rightIndex)
      || left.localeCompare(right);
  });
}

export function missingSkillRequirements(
  skill: InstalledSkill,
  enabledIds: ReadonlySet<string>,
): string[] {
  return (skill.requires || []).filter((id) => !enabledIds.has(id));
}

export function skillInstallOrder(
  catalog: InstalledSkill[],
  targetId: string,
): string[] {
  const skills = new Map(catalog.map((skill) => [skill.id, skill]));
  const order: string[] = [];
  const visiting = new Set<string>();
  const visited = new Set<string>();
  const visit = (id: string) => {
    if (visited.has(id)) return;
    if (visiting.has(id)) throw new Error(`Invalid Skill dependency cycle: ${id}`);
    const skill = skills.get(id);
    if (!skill) throw new Error(`Missing Skill dependency: ${id}`);
    visiting.add(id);
    for (const required of skill.requires || []) visit(required);
    visiting.delete(id);
    visited.add(id);
    order.push(id);
  };
  visit(targetId);
  return order;
}

export function localizedSkillText(
  values: Record<string, string> | undefined,
  fallback: string,
  language: string,
): string {
  return values?.[language] || values?.['zh-CN'] || values?.en || fallback;
}

export function skillIsEnabled(
  skill: InstalledSkill,
  preferences: Record<string, boolean>,
): boolean {
  return skill.enabled ?? (skill.locked || preferences[skill.id] !== false);
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
      options.view === 'enabled'
      && !skillIsEnabled(skill, options.preferences)
    ) return false;
    if (!normalized) return true;
    return [
      skill.id,
      localizedSkillText(skill.name, '', options.language),
      localizedSkillText(skill.description, '', options.language),
      skill.category || '',
      skill.publisher?.name || '',
    ].some((value) => value.toLocaleLowerCase(options.language).includes(normalized));
  });
}

import type { InstalledSkill } from '../types';

function effectiveSkillEnabled(
  catalog: InstalledSkill[],
  preferences: Record<string, boolean>,
  skillId: string,
  visiting = new Set<string>(),
): boolean {
  const skill = catalog.find((item) => item.id === skillId);
  if (!skill) return false;
  if (!skill.locked && preferences[skill.id] === false) return false;
  if (visiting.has(skill.id)) return false;
  const next = new Set(visiting);
  next.add(skill.id);
  return (skill.requires || []).every((requiredId) => {
    return effectiveSkillEnabled(catalog, preferences, requiredId, next);
  });
}

export function capabilityEnabled(
  catalog: InstalledSkill[],
  preferences: Record<string, boolean>,
  capability: string,
): boolean {
  // Keep the existing optimistic UI while the lightweight intelligence read
  // is still connecting. Backend capability gates remain authoritative.
  if (!catalog.length) return true;
  const owner = catalog.find((skill) => {
    return (skill.capabilities || []).includes(capability);
  });
  return Boolean(owner && effectiveSkillEnabled(
    catalog,
    preferences,
    owner.id,
  ));
}

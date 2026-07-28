export interface SkillCapabilityDefinition {
  id: string
  locked?: boolean
  requires?: string[]
  capabilities?: string[]
}

function effectiveSkillEnabled(
  catalog: SkillCapabilityDefinition[],
  preferences: Record<string, boolean>,
  skillId: string,
  visiting = new Set<string>(),
): boolean {
  const skill = catalog.find((item) => item.id === skillId)
  if (!skill) return false
  if (!skill.locked && preferences[skill.id] === false) return false
  if (visiting.has(skill.id)) return false
  const next = new Set(visiting)
  next.add(skill.id)
  return (skill.requires || []).every((requiredId) => (
    effectiveSkillEnabled(catalog, preferences, requiredId, next)
  ))
}

/**
 * Resolve a runtime capability through the shared Skill catalog. The Agent
 * remains authoritative; clients only use this helper to show or hide controls
 * consistently while the same backend capability gate protects execution.
 */
export function capabilityEnabled(
  catalog: SkillCapabilityDefinition[],
  preferences: Record<string, boolean>,
  capability: string,
): boolean {
  if (!catalog.length) return true
  const owner = catalog.find((skill) => (skill.capabilities || []).includes(capability))
  return Boolean(owner && effectiveSkillEnabled(catalog, preferences, owner.id))
}

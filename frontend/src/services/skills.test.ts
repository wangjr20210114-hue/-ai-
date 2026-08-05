import { describe, expect, it } from 'vitest';
import type { InstalledSkill } from '../features/skills/model';
import { capabilityEnabled } from './skills';

function skill(
  id: string,
  capabilities: string[],
  requires: string[] = [],
): InstalledSkill {
  return {
    id,
    order: 0,
    default_enabled: true,
    locked: false,
    capabilities,
    requires,
    recommends: [],
    external: false,
    configured: true,
    connect_url: '',
    icon: '◇',
    name: { 'zh-CN': id },
    description: { 'zh-CN': id },
  };
}

describe('capabilityEnabled', () => {
  it('resolves capability ownership without hard-coded Skill ids', () => {
    const catalog = [skill('renamed-map-package', ['places'])];
    expect(capabilityEnabled(catalog, {}, 'places')).toBe(true);
    expect(capabilityEnabled(
      catalog,
      { 'renamed-map-package': false },
      'places',
    )).toBe(false);
  });

  it('honors required Skill dependencies', () => {
    const catalog = [
      skill('calendar-package', ['calendar_action']),
      skill('meeting-package', ['meeting_action'], ['calendar-package']),
    ];
    expect(capabilityEnabled(
      catalog,
      { 'calendar-package': false },
      'meeting_action',
    )).toBe(false);
  });

  it('keeps panels optimistic until the catalog read completes', () => {
    expect(capabilityEnabled([], {}, 'places')).toBe(true);
  });
});

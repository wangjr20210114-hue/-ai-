import { describe, expect, it } from 'vitest';

import type { InstalledSkill } from '../../shared/types';
import {
  filterMarketplaceSkills,
  localizedSkillText,
  missingSkillRequirements,
  skillInstallOrder,
  skillIsInstalled,
} from './model';

function skill(changes: Partial<InstalledSkill>): InstalledSkill {
  return {
    id: 'test',
    order: 1,
    default_enabled: false,
    locked: false,
    capabilities: [],
    requires: [],
    recommends: [],
    external: false,
    configured: true,
    connect_url: '',
    icon: '◇',
    name: {},
    description: {},
    ...changes,
  };
}

const skills: InstalledSkill[] = [
  skill({
    id: 'core',
    locked: true,
    name: { 'zh-CN': '核心能力', en: 'Core' },
    description: { 'zh-CN': '基础组件', en: 'Base components' },
    publisher: { id: 'floris', name: 'Floris', verified: true },
  }),
  skill({
    id: 'maps',
    locked: false,
    installed: false,
    name: { 'zh-CN': '地图', en: 'Maps' },
    description: { 'zh-CN': '地点和路线', en: 'Places and routes' },
    publisher: { id: 'floris', name: 'Floris', verified: true },
  }),
];

describe('Skill marketplace Model', () => {
  it('localizes text without leaking transport concerns into the View', () => {
    expect(localizedSkillText(skills[0].name, 'fallback', 'zh-CN')).toBe('核心能力');
    expect(localizedSkillText(skills[0].name, 'fallback', 'fr')).toBe('核心能力');
  });

  it('keeps locked system Skills installed and filters installed View', () => {
    expect(skillIsInstalled(skills[0], {})).toBe(true);
    expect(filterMarketplaceSkills(skills, {
      view: 'installed',
      query: '',
      language: 'zh-CN',
      preferences: {},
    }).map((item) => item.id)).toEqual(['core']);
  });

  it('searches localized Model fields and publisher metadata', () => {
    expect(filterMarketplaceSkills(skills, {
      view: 'catalog',
      query: 'route',
      language: 'en',
      preferences: {},
    }).map((item) => item.id)).toEqual(['maps']);
  });

  it('orders prerequisites and rejects missing or cyclic dependency data', () => {
    const graph = [
      skill({ id: 'core', requires: [] }),
      skill({ id: 'maps', requires: ['core'] }),
      skill({ id: 'calendar', requires: ['maps'] }),
    ];
    expect(skillInstallOrder(graph, 'calendar')).toEqual(['core', 'maps', 'calendar']);
    expect(missingSkillRequirements(graph[2], new Set(['core']))).toEqual(['maps']);
    expect(() => skillInstallOrder([
      skill({ id: 'a', requires: ['b'] }),
      skill({ id: 'b', requires: ['a'] }),
    ], 'a')).toThrow(/cycle/i);
    expect(() => skillInstallOrder([
      skill({ id: 'calendar', requires: ['missing'] }),
    ], 'calendar')).toThrow(/Missing Skill dependency/);
  });
});

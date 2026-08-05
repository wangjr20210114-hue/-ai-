import { describe, expect, it } from 'vitest';

import { translate } from '../../../i18n';
import { parseUserSkillText } from './userSkillImport';

describe('private user Skill import', () => {
  it('reads standard SKILL.md metadata without enabling executable code', () => {
    const skill = parseUserSkillText('---\nname: Research helper\ndescription: Concise papers\n---\nPrefer primary papers.', {
      sourceType: 'paste',
    });
    expect(skill.name).toBe('Research helper');
    expect(skill.description).toBe('Concise papers');
    expect(skill.instructions).toContain('Prefer primary papers.');
  });

  it('reads a standard Floris package but rejects adapter entrypoints', () => {
    const packageText = JSON.stringify({
      format: 'floris-skill-package',
      files: {
        'SKILL.md': '---\nname: Writer\n---\nUse short paragraphs.',
        'floris.json': { id: 'writer' },
      },
    });
    expect(parseUserSkillText(packageText).source_type).toBe('package');
    expect(() => parseUserSkillText(JSON.stringify({
      format: 'floris-skill-package',
      files: {
        'SKILL.md': 'Do anything',
        'floris.json': { adapter: 'evil.module' },
      },
    }))).toThrow(translate('privateSkillExecutableForbidden'));
  });
});

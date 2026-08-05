import type { UserSkillRecord } from './types';
import { translate } from '../../../i18n';

export type UserSkillDraft = Pick<
  UserSkillRecord,
  'name' | 'description' | 'instructions' | 'source_type' | 'source_url'
>;

const MAX_INSTRUCTIONS = 12_000;
function textMetadata(text: string): Record<string, string> {
  const match = text.match(/^---\s*\n([\s\S]*?)\n---(?:\s*\n|$)/);
  if (!match) return {};
  return Object.fromEntries(match[1].split(/\r?\n/).flatMap((line) => {
    const field = line.match(/^([a-zA-Z][\w-]*):\s*(.+)$/);
    return field ? [[field[1].toLowerCase(), field[2].trim().replace(/^['"]|['"]$/g, '')]] : [];
  }));
}

function fallbackName(value: string): string {
  return value
    .split(/[\\/]/).pop()
    ?.replace(/\.(floris-skill\.)?(md|json)$/i, '')
    .replace(/[-_]+/g, ' ')
    .trim() || translate('privateSkillDefaultName');
}

export function parseUserSkillText(
  text: string,
  options: {
    fallbackName?: string;
    sourceType?: UserSkillDraft['source_type'];
    sourceUrl?: string;
  } = {},
): UserSkillDraft {
  const clean = String(text || '').trim();
  if (!clean) throw new Error(translate('skillInstructionsEmpty'));
  if (clean.length > MAX_INSTRUCTIONS) {
    throw new Error(translate('skillInstructionsTooLong', { count: MAX_INSTRUCTIONS }));
  }

  if (clean.startsWith('{')) {
    let value: unknown;
    try { value = JSON.parse(clean); } catch { throw new Error(translate('skillJsonInvalid')); }
    const data = value as {
      format?: string;
      files?: { 'SKILL.md'?: string; 'floris.json'?: Record<string, unknown> };
    };
    if (data.format !== 'floris-skill-package' || !data.files?.['SKILL.md']) {
      throw new Error(translate('skillPackageFormatInvalid'));
    }
    const manifest = data.files['floris.json'] || {};
    if ('adapter' in manifest || 'entrypoint' in manifest) {
      throw new Error(translate('privateSkillExecutableForbidden'));
    }
    return parseUserSkillText(data.files['SKILL.md'], {
      ...options,
      fallbackName: String(manifest.name || manifest.id || options.fallbackName || ''),
      sourceType: 'package',
    });
  }

  const metadata = textMetadata(clean);
  const name = String(metadata.name || options.fallbackName || translate('privateSkillDefaultName')).trim().slice(0, 80);
  return {
    name,
    description: String(metadata.description || '').trim().slice(0, 280),
    instructions: clean,
    source_type: options.sourceType || 'paste',
    source_url: String(options.sourceUrl || '').trim().slice(0, 1000),
  };
}

export async function readUserSkillFile(file: File): Promise<UserSkillDraft> {
  const lower = file.name.toLowerCase();
  if (!lower.endsWith('.md') && !lower.endsWith('.json')) {
    throw new Error(translate('skillFileTypeInvalid'));
  }
  return parseUserSkillText(await file.text(), {
    fallbackName: fallbackName(file.name),
    sourceType: lower.endsWith('.json') ? 'package' : 'file',
  });
}

export async function readUserSkillFolder(files: FileList): Promise<UserSkillDraft> {
  const entries = Array.from(files);
  const skillFile = entries.find((file) => /(^|\/)skill\.md$/i.test(file.webkitRelativePath || file.name));
  if (!skillFile) throw new Error(translate('skillFolderMissingManifest'));
  const relative = skillFile.webkitRelativePath || skillFile.name;
  const rootName = relative.split('/')[0] || fallbackName(relative);
  return parseUserSkillText(await skillFile.text(), {
    fallbackName: rootName,
    sourceType: 'folder',
  });
}

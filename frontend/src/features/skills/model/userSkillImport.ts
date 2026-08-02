import type { UserSkillRecord } from '../../../shared/types';
import { requestRaw } from '../../../shared/transport/httpClient';

export type UserSkillDraft = Pick<
  UserSkillRecord,
  'name' | 'description' | 'instructions' | 'source_type' | 'source_url'
>;

const MAX_INSTRUCTIONS = 12_000;
const PUBLIC_SKILL_HOSTS = new Set([
  'github.com',
  'gitlab.com',
  'raw.githubusercontent.com',
]);

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
    .trim() || 'Private Skill';
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
  if (!clean) throw new Error('Skill instructions cannot be empty');
  if (clean.length > MAX_INSTRUCTIONS) {
    throw new Error(`Skill instructions must be at most ${MAX_INSTRUCTIONS} characters`);
  }

  if (clean.startsWith('{')) {
    let value: unknown;
    try { value = JSON.parse(clean); } catch { throw new Error('Invalid Floris Skill JSON'); }
    const data = value as {
      format?: string;
      files?: { 'SKILL.md'?: string; 'floris.json'?: Record<string, unknown> };
    };
    if (data.format !== 'floris-skill-package' || !data.files?.['SKILL.md']) {
      throw new Error('JSON must be a standard floris-skill-package');
    }
    const manifest = data.files['floris.json'] || {};
    if ('adapter' in manifest || 'entrypoint' in manifest) {
      throw new Error('Private Skills cannot contain executable adapters');
    }
    return parseUserSkillText(data.files['SKILL.md'], {
      ...options,
      fallbackName: String(manifest.name || manifest.id || options.fallbackName || ''),
      sourceType: 'package',
    });
  }

  const metadata = textMetadata(clean);
  const name = String(metadata.name || options.fallbackName || 'Private Skill').trim().slice(0, 80);
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
    throw new Error('Choose SKILL.md or a .floris-skill.json package');
  }
  return parseUserSkillText(await file.text(), {
    fallbackName: fallbackName(file.name),
    sourceType: lower.endsWith('.json') ? 'package' : 'file',
  });
}

export async function readUserSkillFolder(files: FileList): Promise<UserSkillDraft> {
  const entries = Array.from(files);
  const skillFile = entries.find((file) => /(^|\/)skill\.md$/i.test(file.webkitRelativePath || file.name));
  if (!skillFile) throw new Error('The folder must contain SKILL.md');
  const relative = skillFile.webkitRelativePath || skillFile.name;
  const rootName = relative.split('/')[0] || fallbackName(relative);
  return parseUserSkillText(await skillFile.text(), {
    fallbackName: rootName,
    sourceType: 'folder',
  });
}

export function publicSkillMarkdownUrl(value: string): string {
  const url = new URL(String(value || '').trim());
  if (url.protocol !== 'https:' || !PUBLIC_SKILL_HOSTS.has(url.hostname)) {
    throw new Error('Use a public GitHub, GitLab, or raw GitHub HTTPS URL');
  }
  if (url.hostname === 'raw.githubusercontent.com') return url.toString();
  const parts = url.pathname.split('/').filter(Boolean);
  if (url.hostname === 'github.com') {
    if (parts.length < 2) throw new Error('Invalid GitHub repository URL');
    const [owner, repo] = parts;
    if (parts[2] === 'blob' && parts.length >= 5) {
      return `https://raw.githubusercontent.com/${owner}/${repo}/${parts[3]}/${parts.slice(4).join('/')}`;
    }
    if (parts[2] === 'tree' && parts.length >= 4) {
      return `https://raw.githubusercontent.com/${owner}/${repo}/${parts[3]}/${parts.slice(4).concat('SKILL.md').join('/')}`;
    }
    return `https://raw.githubusercontent.com/${owner}/${repo}/HEAD/SKILL.md`;
  }
  const marker = parts.indexOf('-');
  if (marker >= 2 && parts[marker + 1] === 'raw') return url.toString();
  if (parts.length < 2) throw new Error('Invalid GitLab repository URL');
  return `https://gitlab.com/${parts[0]}/${parts[1]}/-/raw/HEAD/SKILL.md`;
}

export async function readUserSkillUrl(value: string): Promise<UserSkillDraft> {
  const markdownUrl = publicSkillMarkdownUrl(value);
  const response = await requestRaw(markdownUrl, {
    credentials: 'omit',
    headers: { Accept: 'text/markdown,text/plain;q=0.9' },
    redirect: 'follow',
  }, false);
  if (!response.ok) throw new Error(`Could not read SKILL.md: HTTP ${response.status}`);
  const text = await response.text();
  return parseUserSkillText(text, {
    fallbackName: fallbackName(new URL(value).pathname),
    sourceType: 'url',
    sourceUrl: value,
  });
}

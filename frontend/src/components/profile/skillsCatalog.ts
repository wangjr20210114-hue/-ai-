import type { TranslationKey } from '../../i18n';

export interface SkillCatalogEntry {
  id: string;
  nameKey: TranslationKey;
  icon: string;
  descriptionKey: TranslationKey;
  locked?: boolean;
  requires?: string[];
  recommends?: string[];
  external?: boolean;
}

export const SKILLS_CATALOG: SkillCatalogEntry[] = [
  { id: 'core', nameKey: 'skillCoreName', icon: '✦', descriptionKey: 'skillCoreDescription', locked: true },
  { id: 'web-search', nameKey: 'skillSearchName', icon: '⌕', descriptionKey: 'skillSearchDescription' },
  { id: 'vision', nameKey: 'skillVisionName', icon: '◉', descriptionKey: 'skillVisionDescription' },
  { id: 'image-studio', nameKey: 'skillImageName', icon: '◇', descriptionKey: 'skillImageDescription', recommends: ['vision', 'web-search'] },
  { id: 'maps', nameKey: 'skillMapsName', icon: '⌖', descriptionKey: 'skillMapsDescription' },
  { id: 'calendar', nameKey: 'skillCalendarName', icon: '▦', descriptionKey: 'skillCalendarDescription', recommends: ['maps'] },
  { id: 'proactive-agent', nameKey: 'skillProactiveName', icon: '✧', descriptionKey: 'skillProactiveDescription', recommends: ['calendar', 'maps'] },
  { id: 'paper-reading', nameKey: 'skillPaperName', icon: '▤', descriptionKey: 'skillPaperDescription', recommends: ['web-search'] },
  { id: 'tencent-meeting', nameKey: 'skillMeetingName', icon: '会', descriptionKey: 'skillMeetingDescription', requires: ['calendar'], external: true },
];

import { describe, expect, it } from 'vitest';
import { translate, translationKeys, type Language } from './i18n';

const languages: Language[] = ['zh-CN', 'zh-TW', 'en', 'cat-cute', 'cat-cold'];

describe('fixed UI translations', () => {
  it('provides a non-empty value for every catalog entry in every product language', () => {
    for (const key of translationKeys) {
      for (const language of languages) {
        expect(translate(key, {}, language).trim(), `${key} (${language})`).not.toBe('');
      }
    }
  });

  it('provides every product language for critical failure and action labels', () => {
    for (const language of languages) {
      expect(translate('generationFailedRetry', {}, language)).not.toBe('generationFailedRetry');
      expect(translate('retryGeneration', {}, language)).not.toBe('retryGeneration');
      expect(translate('imageGenerationFailed', { reason: 'x' }, language)).toContain('x');
    }
  });

  it('localizes follow-up and source labels in every product language', () => {
    expect(translate('followUpLabel', {}, 'en')).toBe('You may also want to ask');
    expect(translate('viewSource', {}, 'en')).toBe('View source');
    expect(translate('followUpLabel', {}, 'zh-TW')).toBe('猜你想繼續問');
    expect(translate('viewSource', {}, 'zh-TW')).toBe('查看來源');
    expect(translate('followUpLabel', {}, 'cat-cute')).toContain('喵');
  });

  it('interpolates named values without leaking placeholders', () => {
    for (const language of languages) {
      const value = translate('messageCount', { count: 3 }, language);
      expect(value).toContain('3');
      expect(value).not.toContain('{count}');
    }
  });
});

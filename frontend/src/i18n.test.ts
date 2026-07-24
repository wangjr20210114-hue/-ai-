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

  it('interpolates named values without leaking placeholders', () => {
    for (const language of languages) {
      const value = translate('messageCount', { count: 3 }, language);
      expect(value).toContain('3');
      expect(value).not.toContain('{count}');
    }
  });
});

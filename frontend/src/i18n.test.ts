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

  it('renders numeric settings and route values without braces', () => {
    const cases = [
      translate('numericValue', { value: 8 }, 'zh-CN'),
      translate('secondsValue', { value: 30 }, 'zh-CN'),
      translate('routeToleranceMinutes', { value: 10 }, 'zh-CN'),
      translate('transitFareEstimate', { amount: 6 }, 'zh-CN'),
      translate('transitLines', { lines: '1号线' }, 'zh-CN'),
      translate('transitWalkingDistance', { count: 500 }, 'zh-CN'),
    ];

    for (const value of cases) {
      expect(value).not.toMatch(/[{}]/);
    }
    expect(cases).toEqual([
      '8',
      '30 秒',
      '10 分钟',
      '公交票价约 ¥6',
      '线路：1号线',
      '步行接驳 500 米',
    ]);
  });
});

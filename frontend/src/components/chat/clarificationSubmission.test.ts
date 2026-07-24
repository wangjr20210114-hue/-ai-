import { describe, expect, it } from 'vitest';
import type { ClarificationPrompt } from '../../types';
import {
  clarificationRequestPayload,
  clarificationResponse,
  clarificationSubmissionText,
} from './clarificationSubmission';

describe('clarification submission', () => {
  it('turns selected fields into a direct continuation message', () => {
    const text = clarificationSubmissionText({
      id: 'clarify-1',
      title: '补充必要信息',
      prompt: '请选择',
      fields: [
        { id: 'date', label: '日期', type: 'date', required: true },
        { id: 'style', label: '风格', type: 'multi', options: ['简洁', '正式'] },
      ],
    }, {
      date: '2026-07-26',
      style: ['简洁', '正式'],
    }, '补充必要信息（请直接继续完成上一项任务）：');
    expect(text).toContain('直接继续完成上一项任务');
    expect(text).toContain('日期：2026-07-26');
    expect(text).toContain('风格：简洁、正式');
    expect(text).not.toContain('输入框');
  });

  it('omits optional blank fields', () => {
    expect(clarificationSubmissionText({
      id: 'clarify-2',
      title: '补充必要信息',
      prompt: '请选择',
      fields: [
        { id: 'required', label: '必选项', type: 'single', required: true },
        { id: 'optional', label: '可选项', type: 'text' },
      ],
    }, { required: '方案 A', optional: '' }, '补充必要信息：')).not.toContain('可选项：');
  });

  it('builds a structured silent response tied to the original card', () => {
    const clarification: ClarificationPrompt = {
      id: 'clarify-3',
      title: '补充必要信息',
      prompt: '请选择',
      fields: [
        { id: 'route', label: '路线', type: 'single', required: true },
        { id: 'notes', label: '备注', type: 'text' },
      ],
    };
    const values = {
      route: '地铁',
      notes: '',
    };
    const response = clarificationResponse(clarification, values, 'ai-card-1');
    expect(response).toEqual({
      id: 'clarify-3',
      source_message_id: 'ai-card-1',
      answers: [{ id: 'route', label: '路线', value: '地铁' }],
    });
    const payload = clarificationRequestPayload(
      clarification,
      values,
      'ai-card-1',
      'response-1',
      '补充必要信息：路线：地铁',
      'zh-CN',
    );
    expect(payload.interaction_mode).toBe('clarification');
    expect(payload.clarification_response).toEqual(response);
    expect(payload).not.toHaveProperty('client_message');
  });
});

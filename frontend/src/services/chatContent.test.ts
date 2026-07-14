import { describe, expect, it } from 'vitest';
import { stripInlineFollowUpSection } from './chatContent';

describe('chat content formatting', () => {
  it('removes leaked UI follow-up text from the answer body', () => {
    expect(stripInlineFollowUpSection('正文结论。\n\n### 猜你想继续问\n- 问题一\n- 问题二'))
      .toBe('正文结论。');
  });

  it('removes the travel answer heading emitted by the model', () => {
    expect(stripInlineFollowUpSection(
      '如果只有一天，可以优先选择市区景点。\n\n后续问题：\n1. 需要帮你串成行程吗？\n2. 想看门票信息吗？',
    )).toBe('如果只有一天，可以优先选择市区景点。');
  });

  it('recognizes markdown and alternate question-only headings', () => {
    expect(stripInlineFollowUpSection('正文。\n\n## 后续追问\n- 问题一')).toBe('正文。');
    expect(stripInlineFollowUpSection('正文。\n\n延伸问题\n- 问题一')).toBe('正文。');
  });

  it('does not remove a legitimate project follow-up plan', () => {
    const content = '实施完成。\n\n## 后续建议\n1. 继续观察指标';
    expect(stripInlineFollowUpSection(content)).toBe(content);
  });
});

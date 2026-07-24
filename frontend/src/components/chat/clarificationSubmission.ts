import type { ClarificationPrompt } from '../../types';

export function clarificationSubmissionText(
  clarification: ClarificationPrompt,
  values: Record<string, string | string[]>,
  intro: string,
): string {
  const answers = clarification.fields.flatMap((field) => {
    const value = values[field.id];
    const text = Array.isArray(value) ? value.map(String).filter(Boolean).join('、') : String(value || '').trim();
    return text ? [`${field.label}：${text}`] : [];
  });
  return [
    intro,
    ...answers,
  ].join('\n');
}

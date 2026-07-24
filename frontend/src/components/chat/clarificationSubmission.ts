import type { ClarificationPrompt } from '../../types';

export interface ClarificationResponse {
  id: string;
  source_message_id: string;
  answers: Array<{ id: string; label: string; value: string | string[] }>;
}

export function clarificationResponse(
  clarification: ClarificationPrompt,
  values: Record<string, string | string[]>,
  sourceMessageId: string,
): ClarificationResponse {
  const answers: ClarificationResponse['answers'] = [];
  clarification.fields.forEach((field) => {
    const value = values[field.id];
    if (Array.isArray(value)) {
      if (value.length) answers.push({ id: field.id, label: field.label, value });
      return;
    }
    const text = String(value || '').trim();
    if (text) answers.push({ id: field.id, label: field.label, value: text });
  });
  return {
    id: clarification.id,
    source_message_id: sourceMessageId,
    answers,
  };
}

export function clarificationRequestPayload(
  clarification: ClarificationPrompt,
  values: Record<string, string | string[]>,
  sourceMessageId: string,
  responseId: string,
  content: string,
  responseLanguage: string,
): Record<string, unknown> {
  return {
    activity: 'clarification_answered',
    text: content,
    message_id: responseId,
    client_message_id: responseId,
    interaction_mode: 'clarification',
    clarification_response: clarificationResponse(clarification, values, sourceMessageId),
    reference_images: [],
    response_language: responseLanguage,
  };
}

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

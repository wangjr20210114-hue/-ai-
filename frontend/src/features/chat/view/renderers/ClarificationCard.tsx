import { useEffect, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';

import {
  clarificationOptionValue,
  clarificationRequestPayload,
  clarificationSubmissionText,
} from '../../../../components/chat/clarificationSubmission';
import { getStoredLanguage, useLanguage } from '../../../../i18n';
import type { ChatClient } from '../../../../services/chatClient';
import type { ClarificationPrompt } from '../../model';

interface Props {
  clarification: ClarificationPrompt;
  messageId: string;
  client: React.RefObject<ChatClient | null>;
  answered: boolean;
  generationActive: boolean;
}

export function ClarificationCard({
  clarification,
  messageId,
  client,
  answered,
  generationActive,
}: Props) {
  const { t } = useLanguage();
  const [values, setValues] = useState<Record<string, string | string[]>>({});
  const [activeIndex, setActiveIndex] = useState(0);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isSubmitted = submitted || answered;
  const fields = clarification.fields;
  const activeField = fields[Math.min(activeIndex, Math.max(0, fields.length - 1))];
  const setValue = (id: string, value: string | string[]) => {
    setValues((current) => ({ ...current, [id]: value }));
  };
  const fieldComplete = (field: ClarificationPrompt['fields'][number]) => {
    if (!field.required) return true;
    const value = values[field.id];
    return Array.isArray(value) ? value.length > 0 : Boolean(String(value || '').trim());
  };
  const complete = fields.every(fieldComplete);
  const currentComplete = activeField ? fieldComplete(activeField) : false;
  const lastStep = activeIndex >= fields.length - 1;

  useEffect(() => {
    setActiveIndex((current) => Math.min(current, Math.max(0, fields.length - 1)));
  }, [fields.length]);

  const advance = () => {
    if (!currentComplete || lastStep) return;
    setActiveIndex((current) => Math.min(fields.length - 1, current + 1));
  };
  const chooseAndAdvance = (id: string, value: string) => {
    setValue(id, value);
    if (!lastStep) setActiveIndex((current) => Math.min(fields.length - 1, current + 1));
  };
  const submit = async () => {
    if (!client.current || !complete || isSubmitted || submitting || generationActive) {
      if (!client.current) MessagePlugin.warning(t('connectionNotReady'));
      return;
    }
    const content = clarificationSubmissionText(
      clarification,
      values,
      t('clarificationAnswerIntro'),
    );
    const responseId = `clarification-${clarification.id}-${Date.now()}`;
    setSubmitted(true);
    setSubmitting(true);
    MessagePlugin.success(t('askContinue'));
    try {
      await Promise.resolve(client.current.send({
        type: 'user_activity',
        payload: clarificationRequestPayload(
          clarification,
          values,
          messageId,
          responseId,
          content,
          getStoredLanguage(),
        ),
      }));
    } catch {
      setSubmitted(false);
      MessagePlugin.error(t('serviceError'));
    } finally {
      setSubmitting(false);
    }
  };

  const fieldInput = () => {
    if (!activeField) return null;
    const field = activeField;
    const value = values[field.id];
    if (field.type === 'single' || field.type === 'boolean') {
      const options = field.type === 'boolean' ? [t('yes'), t('no')] : (field.options || []);
      return <fieldset className="clarification-field">
        <legend>{field.label}{field.required ? t('requiredSingle') : ''}</legend>
        <div className="clarification-option-list">{options.map((option) => {
          const optionValue = clarificationOptionValue(field, option);
          return <label key={option} className="clarification-option">
            <input
              type="radio"
              name={`${clarification.id}-${field.id}`}
              checked={value === optionValue}
              onChange={() => chooseAndAdvance(field.id, optionValue)}
            />
            {option}
          </label>;
        })}</div>
      </fieldset>;
    }
    if (field.type === 'multi') {
      return <fieldset className="clarification-field">
        <legend>{field.label}{field.required ? t('requiredMulti') : ''}</legend>
        <div className="clarification-option-list">{(field.options || []).map((option) => {
          const optionValue = clarificationOptionValue(field, option);
          const selected = Array.isArray(value) && value.includes(optionValue);
          return <label key={option} className="clarification-option">
            <input
              type="checkbox"
              checked={selected}
              onChange={(event) => {
                const current = Array.isArray(value) ? value : [];
                setValue(field.id, event.target.checked
                  ? [...current, optionValue]
                  : current.filter((item) => item !== optionValue));
              }}
            />
            {option}
          </label>;
        })}</div>
      </fieldset>;
    }
    const inputType = field.type === 'date'
      ? 'date'
      : field.type === 'time'
        ? 'time'
        : field.type === 'datetime'
          ? 'datetime-local'
          : 'text';
    return <label className={`clarification-field clarification-field-${field.type}`}>
      <span>{field.label}{field.required ? t('requiredField') : ''}</span>
      <input
        type={inputType}
        value={typeof value === 'string' ? value : ''}
        placeholder={field.placeholder}
        step={field.type === 'time' ? 300 : undefined}
        onChange={(event) => setValue(field.id, event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' || !currentComplete) return;
          event.preventDefault();
          if (lastStep && complete) void submit();
          else advance();
        }}
      />
    </label>;
  };

  return <div className="clarification-card">
    <div className="clarification-heading">
      <strong>{clarification.title}</strong>
      {fields.length > 1 && <span>{activeIndex + 1} / {fields.length}</span>}
    </div>
    <p>{clarification.prompt}</p>
    {isSubmitted
      ? <div className="clarification-complete">{t('filledInput')}</div>
      : fieldInput()}
    {!isSubmitted && <div className="clarification-actions">
      {fields.length > 1 && <Button
        size="small"
        variant="outline"
        disabled={activeIndex === 0 || submitting || generationActive}
        onClick={() => setActiveIndex((current) => Math.max(0, current - 1))}
      >{t('previousStep')}</Button>}
      {!lastStep
        ? <Button
          size="small"
          theme="primary"
          disabled={!currentComplete || submitting || generationActive}
          onClick={advance}
        >{t('nextStep')}</Button>
        : <Button
          size="small"
          theme="primary"
          loading={submitting}
          disabled={!complete || generationActive}
          onClick={() => { void submit(); }}
        >{t('completeAndContinue')}</Button>}
    </div>}
  </div>;
}

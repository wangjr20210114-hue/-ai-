import { useMemo, useState } from 'react'
import {
  Button,
  Checkbox,
  CheckboxGroup,
  Input,
  Label,
  Picker,
  Radio,
  RadioGroup,
  Text,
  View,
} from '@tarojs/components'
import type { ClarificationField, ClarificationPrompt } from '@floris/contracts'
import { translate } from '@/i18n'

interface Props {
  prompt: ClarificationPrompt
  disabled?: boolean
  answered?: boolean
  onSubmit: (values: Record<string, string | string[]>) => void
}

function ChoiceField({
  field,
  value,
  disabled,
  onChange,
}: {
  field: ClarificationField
  value: string | string[]
  disabled: boolean
  onChange: (value: string | string[]) => void
}) {
  if (field.type === 'multi') {
    return <CheckboxGroup onChange={(event) => onChange(event.detail.value)} name={field.id}>
      {(field.options || []).map((option) => {
        const checked = Array.isArray(value) && value.includes(option)
        return <Label className={`choice-option ${checked ? 'is-selected' : ''}`} key={option}>
        <Checkbox value={option} checked={checked} disabled={disabled} />
        <Text>{option}</Text>
      </Label>
      })}
    </CheckboxGroup>
  }
  return <RadioGroup onChange={(event) => onChange(event.detail.value)} name={field.id}>
    {(field.type === 'boolean' && !(field.options || []).length
      ? [translate('yes'), translate('no')]
      : field.options || []).map((option) => {
      const checked = value === option
      return <Label className={`choice-option ${checked ? 'is-selected' : ''}`} key={option}>
        <Radio value={option} checked={checked} disabled={disabled} />
        <Text>{option}</Text>
      </Label>
      })}
  </RadioGroup>
}

function NativeInput({
  field,
  value,
  disabled,
  onChange,
}: {
  field: ClarificationField
  value: string
  disabled: boolean
  onChange: (value: string) => void
}) {
  if (field.type === 'date' || field.type === 'time') {
    return <Picker
      disabled={disabled}
      mode={field.type}
      value={value || (field.type === 'date' ? new Date().toISOString().slice(0, 10) : '09:00')}
      onChange={(event) => onChange(String(event.detail.value))}
    >
      <View className='native-picker'>{value || field.placeholder || translate(field.type === 'date' ? 'chooseDate' : 'chooseTime')}</View>
    </Picker>
  }
  if (field.type === 'datetime') {
    const [date = '', time = ''] = value.split('T')
    const update = (nextDate: string, nextTime: string) => onChange(`${nextDate}T${nextTime}`)
    return <View className='datetime-row'>
      <Picker disabled={disabled} mode='date' value={date || new Date().toISOString().slice(0, 10)}
        onChange={(event) => update(String(event.detail.value), time || '09:00')}>
        <View className='native-picker'>{date || translate('chooseDate')}</View>
      </Picker>
      <Picker disabled={disabled} mode='time' value={time || '09:00'}
        onChange={(event) => update(date || new Date().toISOString().slice(0, 10), String(event.detail.value))}>
        <View className='native-picker'>{time || translate('chooseTime')}</View>
      </Picker>
    </View>
  }
  return <Input
    className='clarification-input'
    disabled={disabled}
    placeholder={field.placeholder || translate('inputPlaceholder')}
    value={value}
    onInput={(event) => onChange(event.detail.value)}
  />
}

export default function ClarificationCard({ prompt, disabled = false, answered = false, onSubmit }: Props) {
  const initial = useMemo(() => Object.fromEntries(
    prompt.fields.map((field) => [field.id, field.type === 'multi' ? [] : '']),
  ), [prompt])
  const [values, setValues] = useState<Record<string, string | string[]>>(initial)
  const complete = prompt.fields.every((field) => {
    if (!field.required) return true
    const value = values[field.id]
    return Array.isArray(value) ? value.length > 0 : Boolean(String(value || '').trim())
  })
  const locked = disabled || answered

  return <View className='structured-card'>
    <Text className='card-title'>{prompt.title}</Text>
    <Text className='card-copy'>{prompt.prompt}</Text>
    {prompt.fields.map((field) => {
      const value = values[field.id]
      const choice = ['single', 'multi', 'boolean'].includes(field.type)
      return <View className='clarification-field' key={field.id}>
        <Text className='field-label'>{field.label}{field.required ? ' *' : ''}</Text>
        {choice
          ? <ChoiceField field={field} value={value} disabled={locked}
            onChange={(next) => setValues((current) => ({ ...current, [field.id]: next }))} />
          : <NativeInput field={field} value={String(value || '')} disabled={locked}
            onChange={(next) => setValues((current) => ({ ...current, [field.id]: next }))} />}
      </View>
    })}
    <Button className='primary-button' disabled={!complete || locked} onClick={() => onSubmit(values)}>
      {translate(answered ? 'submitted' : 'confirmContinue')}
    </Button>
  </View>
}

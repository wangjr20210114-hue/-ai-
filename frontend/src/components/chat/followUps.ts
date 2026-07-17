import type { Action } from '../../store/appState';

/** A suggestion is an editable draft. Sending always remains an explicit user action. */
export function followUpDraftAction(question: string): Action {
  return { type: 'SET_DRAFT', payload: question };
}

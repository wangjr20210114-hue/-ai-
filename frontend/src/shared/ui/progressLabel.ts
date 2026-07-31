import type {
  StructuredProgressActivity,
  StructuredProgressStage,
  StructuredProgressStep,
} from '../../shared/types';
import type { TranslationKey } from '../../i18n';


export function progressTranslationKey(
  step: StructuredProgressStep,
): TranslationKey {
  const activityKeys: Partial<Record<
    StructuredProgressActivity,
    TranslationKey
  >> = {
    web_search: 'progressWebSearch',
    paper_search: 'progressPaperSearch',
    place_search: 'progressPlaceSearch',
    route_planning: 'progressRoutePlanning',
    calendar_preparation: 'progressCalendarPreparation',
    meeting_preparation: 'progressMeetingPreparation',
    image_generation: 'progressImageGeneration',
    image_review: 'progressImageReview',
    component_action: 'progressComponentAction',
  };
  if (step.activity !== 'general' && activityKeys[step.activity]) {
    return activityKeys[step.activity] as TranslationKey;
  }
  const stageKeys: Record<StructuredProgressStage, TranslationKey> = {
    planning: 'progressPlanning',
    retrieval: 'progressRetrieval',
    verification: 'progressVerification',
    synthesis: 'progressSynthesis',
    finalizing: 'progressFinalizing',
    complete: 'progressComplete',
  };
  return stageKeys[step.stage];
}

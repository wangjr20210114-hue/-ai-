import type {
  StructuredProgressActivity,
  StructuredProgressStage,
  StructuredProgressStep,
} from '../../../types';
export { progressTranslationKey } from '../../../shared/ui/progressLabel';

const STAGES = new Set<StructuredProgressStage>([
  'planning',
  'retrieval',
  'verification',
  'synthesis',
  'finalizing',
  'complete',
]);
const STATUSES = new Set<StructuredProgressStep['status']>([
  'active',
  'completed',
  'skipped',
]);
const ACTIVITIES = new Set<StructuredProgressActivity>([
  'general',
  'web_search',
  'paper_search',
  'place_search',
  'route_planning',
  'calendar_preparation',
  'meeting_preparation',
  'image_generation',
  'image_review',
  'component_action',
]);

export function initialPlanningProgress(now = Date.now()): StructuredProgressStep {
  return {
    schema_version: 1,
    stage: 'planning',
    status: 'active',
    activity: 'general',
    source: 'client',
    updated_at: now,
  };
}

export function normalizeProgressEvent(
  value: unknown,
  now = Date.now(),
): StructuredProgressStep | null {
  if (!value || typeof value !== 'object') return null;
  const raw = value as Record<string, unknown>;
  const stage = String(raw.stage || '') as StructuredProgressStage;
  const status = String(raw.status || '') as StructuredProgressStep['status'];
  const activity = String(raw.activity || '') as StructuredProgressActivity;
  if (
    Number(raw.schema_version) !== 1
    || raw.source !== 'controller'
    || !STAGES.has(stage)
    || !STATUSES.has(status)
    || !ACTIVITIES.has(activity)
  ) return null;
  return {
    schema_version: 1,
    stage,
    status,
    activity,
    source: 'controller',
    updated_at: now,
  };
}

export function mergeProgressStep(
  current: StructuredProgressStep[] | undefined,
  incoming: StructuredProgressStep,
): StructuredProgressStep[] {
  const steps = [...(current || [])];
  const key = `${incoming.stage}:${incoming.activity}`;
  const index = steps.findIndex(
    (item) => `${item.stage}:${item.activity}` === key,
  );
  if (index >= 0) steps[index] = incoming;
  else steps.push(incoming);
  if (incoming.stage === 'complete' && incoming.status === 'completed') {
    return steps.map((item) => (
      item.status === 'active'
        ? {
          ...item,
          status: 'completed' as const,
          updated_at: incoming.updated_at,
        }
        : item
    )).slice(-8);
  }
  return steps.slice(-8);
}


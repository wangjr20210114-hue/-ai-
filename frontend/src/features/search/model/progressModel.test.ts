import { describe, expect, it } from 'vitest';

import {
  initialPlanningProgress,
  mergeProgressStep,
  normalizeProgressEvent,
} from './progressModel';

describe('trusted structured progress Model', () => {
  it('starts immediately on the client while server planning is pending', () => {
    expect(initialPlanningProgress(100)).toEqual({
      schema_version: 1,
      stage: 'planning',
      status: 'active',
      activity: 'general',
      source: 'client',
      updated_at: 100,
    });
  });

  it('accepts only controller-owned enum events', () => {
    expect(normalizeProgressEvent({
      schema_version: 1,
      stage: 'retrieval',
      status: 'active',
      activity: 'web_search',
      source: 'controller',
      reasoning: 'hidden text must be ignored',
    }, 200)?.activity).toBe('web_search');
    expect(normalizeProgressEvent({
      schema_version: 1,
      stage: 'reasoning',
      status: 'active',
      activity: 'general',
      source: 'model',
    })).toBeNull();
  });

  it('preserves the controller timestamp across a browser restore', () => {
    expect(normalizeProgressEvent({
      schema_version: 1,
      stage: 'retrieval',
      status: 'active',
      activity: 'web_search',
      source: 'controller',
      updated_at: 1786000000123,
    }, 200)?.updated_at).toBe(1786000000123);
  });

  it('updates stable steps and closes active work on completion', () => {
    const planning = initialPlanningProgress(100);
    const planned = normalizeProgressEvent({
      schema_version: 1,
      stage: 'planning',
      status: 'completed',
      activity: 'general',
      source: 'controller',
    }, 200)!;
    const complete = normalizeProgressEvent({
      schema_version: 1,
      stage: 'complete',
      status: 'completed',
      activity: 'general',
      source: 'controller',
    }, 300)!;
    expect(
      mergeProgressStep(mergeProgressStep([planning], planned), complete)
        .every((item) => item.status !== 'active'),
    ).toBe(true);
  });
});

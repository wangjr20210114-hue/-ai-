import { describe, expect, it } from 'vitest';
import type { WorkspaceAction } from '../../types';
import { generatedImageOpportunitySignal, nextWholeHourRange, usableMapPlaces } from './workspaceUi';

function mapAction(places: WorkspaceAction['payload']['places']): WorkspaceAction {
  return {
    schema_version: 1,
    id: 'map-test',
    kind: 'map_recommendation',
    status: 'ready',
    version: 1,
    payload: { places },
  };
}

describe('meeting confirmation helpers', () => {
  it('offers a next-whole-hour range with a one-hour duration', () => {
    const range = nextWholeHourRange(new Date(2026, 6, 21, 10, 24, 35));
    const start = new Date(range.start);
    const end = new Date(range.end);

    expect(start.getMinutes()).toBe(0);
    expect(start.getSeconds()).toBe(0);
    expect(end.getTime() - start.getTime()).toBe(60 * 60_000);
  });
});

describe('map Action snapshot', () => {
  it('reveals only places with valid frozen IDs and coordinates', () => {
    const action = mapAction([
      { place_id: 'verified', provider: 'tencent', name: '已核实地点', address: '北京', latitude: 39.9, longitude: 116.4 },
      { place_id: '', provider: 'tencent', name: '缺少 ID', address: '', latitude: 39.9, longitude: 116.4 },
      { place_id: 'bad-coordinate', provider: 'tencent', name: '错误坐标', address: '', latitude: 999, longitude: 116.4 },
    ]);

    expect(usableMapPlaces(action).map((place) => place.place_id)).toEqual(['verified']);
  });
});

describe('generated image opportunity signal', () => {
  it('contains only prompt metadata and deduplicates by Action id', () => {
    const action = {
      schema_version: 1,
      id: 'image-action-1',
      kind: 'image_generate',
      status: 'succeeded',
      version: 2,
      payload: { prompt: '活动页首屏，主体靠左', parent_action_id: 'image-v1' },
      result: { image_url: '/files?key=secret-image-key', storage_key: 'secret-image-key' },
    } as WorkspaceAction;

    expect(generatedImageOpportunitySignal(action)).toEqual({
      signal_type: 'image_generated',
      dedup_key: 'image-action-1',
      payload: {
        action_id: 'image-action-1',
        prompt: '活动页首屏，主体靠左',
        has_reference_image: true,
        has_previous_version: true,
      },
    });
  });

  it('does not emit before the image succeeds', () => {
    const action = {
      schema_version: 1,
      id: 'image-action-2',
      kind: 'image_generate',
      status: 'awaiting_confirmation',
      version: 1,
      payload: { prompt: '一只橘猫' },
    } as WorkspaceAction;
    expect(generatedImageOpportunitySignal(action)).toBeNull();
  });
});

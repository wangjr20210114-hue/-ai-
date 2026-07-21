import { describe, expect, it } from 'vitest';
import type { WorkspaceAction } from '../../types';
import { nextWholeHourRange, usableMapPlaces } from './workspaceUi';

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

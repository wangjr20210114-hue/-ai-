import { describe, expect, it } from 'vitest';

import { routes as calendarRoutes } from './calendar/model/client';
import { routes as chatRoutes } from './chat/model/client';
import { routes as mapsRoutes } from './maps/model/client';
import { routes as paperRoutes } from './papers/model/client';
import { routes as searchRoutes } from './search/model/client';
import { routes as settingsRoutes } from './settings/model/client';
import { routes as skillRoutes } from './skills/model/client';


describe('feature route ownership', () => {
  it('assigns each endpoint to exactly one model client', () => {
    expect(chatRoutes).toEqual(['/chat', '/conversation', '/messages', '/stop']);
    expect(paperRoutes.every(
      (route) => ['/papers', '/reader', '/library'].includes(route),
    )).toBe(true);
    const owned = [
      ...chatRoutes,
      ...searchRoutes,
      ...calendarRoutes,
      ...mapsRoutes,
      ...paperRoutes,
      ...settingsRoutes,
      ...skillRoutes,
    ];
    expect(owned).toHaveLength(new Set(owned).size);
  });
});

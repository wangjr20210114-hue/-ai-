import assert from 'node:assert/strict';
import test from 'node:test';

import { assertImportAllowed } from './check-feature-boundaries.mjs';


test('feature boundary policy allows public view APIs but rejects deep cross-feature views', () => {
  assert.equal(
    assertImportAllowed('features/chat/model/x.ts', 'features/maps/view/Map.tsx'),
    false,
  );
  assert.equal(
    assertImportAllowed(
      'features/chat/controller/x.ts',
      'features/search/model/events.ts',
    ),
    true,
  );
  assert.equal(
    assertImportAllowed('shared/ui/Button.tsx', 'features/chat/model/x.ts'),
    false,
  );
  assert.equal(
    assertImportAllowed('features/chat/view/x.tsx', 'features/maps/view'),
    true,
  );
  assert.equal(
    assertImportAllowed(
      'features/chat/view/x.tsx',
      'features/maps/view/TravelPlanCard.tsx',
    ),
    false,
  );
});

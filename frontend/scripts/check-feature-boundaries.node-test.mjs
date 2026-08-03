import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertImportAllowed,
  assertNetworkAllowed,
} from './check-feature-boundaries.mjs';


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
      'features/maps/view/MakersMap.tsx',
    ),
    false,
  );
});

test('backend calls are owned only by shared transport/auth or feature models', () => {
  assert.equal(assertNetworkAllowed('shared/transport/httpClient.ts'), true);
  assert.equal(assertNetworkAllowed('shared/auth/session.ts'), true);
  assert.equal(assertNetworkAllowed('features/chat/model/client.ts'), true);
  assert.equal(assertNetworkAllowed('features/papers/model/api.ts'), true);
  assert.equal(assertNetworkAllowed('features/chat/controller/chatTransport.ts'), false);
  assert.equal(assertNetworkAllowed('features/papers/view/Reader.tsx'), false);
  assert.equal(assertNetworkAllowed('services/paperApi.ts'), false);
});

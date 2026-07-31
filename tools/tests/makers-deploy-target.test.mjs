import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertMakerDeployTarget,
  EXPECTED_PROJECT,
} from '../assert-makers-deploy-target.mjs';


test('accepts only the isolated dev Maker project', () => {
  assert.doesNotThrow(() => assertMakerDeployTarget({ ...EXPECTED_PROJECT }));
});

test('rejects another Maker project even when its shape is valid', () => {
  assert.throws(
    () => assertMakerDeployTarget({ Name: 'another-project', ProjectId: 'makers-other' }),
    /Refusing deployment/,
  );
});

test('rejects an ambiguous binding with extra fields', () => {
  assert.throws(
    () => assertMakerDeployTarget({ ...EXPECTED_PROJECT, environment: 'production' }),
    /unexpected fields/,
  );
});

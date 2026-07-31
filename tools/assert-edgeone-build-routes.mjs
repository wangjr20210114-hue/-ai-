import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const configPath = resolve(root, '.edgeone/agent-python/config.json');
const config = JSON.parse(await readFile(configPath, 'utf8'));
const routes = new Set((config.routes || []).map((route) => route.path));

assert.ok(
  routes.has('/skill_marketplace'),
  'EdgeOne build is missing the /skill_marketplace Agent route',
);
assert.ok(
  !routes.has('/skills'),
  'EdgeOne reserved /skills must not be used as a product route',
);
for (const route of routes) {
  assert.ok(
    !route.startsWith('/skill_adapters')
      && !route.startsWith('/_skill_adapters'),
    `trusted Skill adapter was exposed as an HTTP route: ${route}`,
  );
}

console.log('EdgeOne Agent route contract verified.');

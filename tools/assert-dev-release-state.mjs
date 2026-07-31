import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';


const EXPECTED_MAIN = '72be68b2615e7dc23abfbeadca9ce204e3a3c84c';
const root = resolve(import.meta.dirname, '..');

function git(...args) {
  return execFileSync('git', args, {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

assert.equal(git('branch', '--show-current'), 'dev', 'Release is allowed only from dev.');
assert.equal(git('rev-parse', 'main'), EXPECTED_MAIN, 'Local main baseline changed.');
assert.equal(git('rev-parse', 'origin/main'), EXPECTED_MAIN, 'origin/main baseline changed.');
assert.equal(git('status', '--porcelain'), '', 'Release requires a clean worktree.');

console.log(`Dev release state verified; main remains ${EXPECTED_MAIN}.`);

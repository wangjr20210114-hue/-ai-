import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';


// The protected local main ref remains pinned to the task's immutable baseline.
// origin/main was independently fast-forwarded before this dev release; pin it
// separately so a dev deployment never rewrites or silently follows either ref.
const EXPECTED_LOCAL_MAIN = '72be68b2615e7dc23abfbeadca9ce204e3a3c84c';
const EXPECTED_ORIGIN_MAIN = '712fe07a1b41dc1ce2ba316838bba0e2d111d32a';
const root = resolve(import.meta.dirname, '..');

function git(...args) {
  return execFileSync('git', args, {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  }).trim();
}

assert.equal(git('branch', '--show-current'), 'dev', 'Release is allowed only from dev.');
assert.equal(
  git('rev-parse', 'main'), EXPECTED_LOCAL_MAIN, 'Local main baseline changed.',
);
assert.equal(
  git('rev-parse', 'origin/main'), EXPECTED_ORIGIN_MAIN, 'origin/main baseline changed.',
);
const releaseStatus = git('status', '--porcelain', '--untracked-files=all')
  .split('\n')
  .filter(Boolean)
  // The Android client is a separate user-owned branch checkout in this
  // shared workspace. A Web dev release must neither stage nor delete it.
  .filter((line) => !/^\?\? "?android\//.test(line))
  .join('\n');
assert.equal(releaseStatus, '', 'Release requires a clean Web dev worktree.');

console.log(
  `Dev release state verified; local main remains ${EXPECTED_LOCAL_MAIN}; `
  + `observed origin/main remains ${EXPECTED_ORIGIN_MAIN}.`,
);

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';


export const EXPECTED_PROJECT = Object.freeze({
  Name: 'floris-dev',
  ProjectId: 'makers-0kgcojx0gjiy',
});

export function assertMakerDeployTarget(project) {
  assert.deepEqual(
    { Name: project.Name, ProjectId: project.ProjectId },
    EXPECTED_PROJECT,
    'Refusing deployment: local EdgeOne binding is not the isolated dev Maker project.',
  );
  assert.equal(
    Object.keys(project).length,
    Object.keys(EXPECTED_PROJECT).length,
    'Refusing deployment: project binding contains unexpected fields.',
  );
}

async function main() {
  const root = resolve(import.meta.dirname, '..');
  const projectPath = resolve(root, '.edgeone', 'project.json');
  const project = JSON.parse(await readFile(projectPath, 'utf8'));
  assertMakerDeployTarget(project);
  console.log(
    `Maker deployment target verified: ${EXPECTED_PROJECT.Name} (${EXPECTED_PROJECT.ProjectId}).`,
  );
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}

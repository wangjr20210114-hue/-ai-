import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sourceRoot = resolve(frontendRoot, 'src');
const entryPath = resolve(sourceRoot, 'styles/index.css');
const failures = [];

function filesUnder(directory) {
  if (!existsSync(directory)) return [];
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    return entry.isDirectory() ? filesUnder(path) : [path];
  });
}

const cssFiles = [
  ...filesUnder(resolve(sourceRoot, 'styles')),
  ...filesUnder(resolve(sourceRoot, 'features')),
  ...filesUnder(resolve(sourceRoot, 'shared/ui')),
].filter((file) => file.endsWith('.css'));

if (existsSync(resolve(sourceRoot, 'index.css'))) {
  failures.push('legacy src/index.css must not exist');
}

const mainSource = readFileSync(resolve(sourceRoot, 'main.tsx'), 'utf8');
if (!mainSource.includes("import './styles/index.css'")) {
  failures.push('main.tsx must import the owned styles entry');
}

const entry = readFileSync(entryPath, 'utf8');
const imports = [...entry.matchAll(/@import\s+["']([^"']+)["'];/g)]
  .map((match) => resolve(dirname(entryPath), match[1]));
const importCounts = new Map();
for (const file of imports) {
  importCounts.set(file, (importCounts.get(file) || 0) + 1);
}

for (const file of cssFiles) {
  const label = relative(frontendRoot, file).split(sep).join('/');
  const source = readFileSync(file, 'utf8');
  const lineCount = source.split(/\r?\n/).length - 1;
  if (file !== entryPath && lineCount > 400) {
    failures.push(`${label} has ${lineCount} lines (maximum 400)`);
  }
  if (/媒体槽|YUANBAO_MEDIA|model.+media slot/i.test(source)) {
    failures.push(`${label} contains a legacy model-directed media-slot marker`);
  }
  if (file !== entryPath && importCounts.get(file) !== 1) {
    failures.push(`${label} must be imported exactly once by styles/index.css`);
  }
}

for (const [file, count] of importCounts) {
  if (count !== 1) {
    failures.push(`${relative(frontendRoot, file)} is imported ${count} times`);
  }
  if (!existsSync(file)) {
    failures.push(`styles/index.css imports missing file ${relative(frontendRoot, file)}`);
  }
}

function selectors(source) {
  const cleaned = source.replace(/\/\*[\s\S]*?\*\//g, '');
  const found = new Set();
  const stack = [];
  let statementStart = 0;
  let quote = '';
  let escaped = false;
  for (let index = 0; index < cleaned.length; index += 1) {
    const character = cleaned[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === quote) quote = '';
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      continue;
    }
    if (character === ';') {
      statementStart = index + 1;
      continue;
    }
    if (character === '{') {
      const header = cleaned.slice(statementStart, index).trim();
      const inKeyframes = stack.some((item) => item.startsWith('@keyframes'));
      if (
        header
        && !header.startsWith('@')
        && !inKeyframes
        && !/^(?:from|to|\d+(?:\.\d+)?%)$/.test(header)
      ) {
        for (const selector of header.split(',')) {
          found.add(selector.replace(/\s+/g, ' ').trim());
        }
      }
      stack.push(header);
      statementStart = index + 1;
      continue;
    }
    if (character === '}') {
      stack.pop();
      statementStart = index + 1;
    }
  }
  return found;
}

const featureOwners = new Map();
for (const file of cssFiles) {
  const normalized = relative(sourceRoot, file).split(sep).join('/');
  const match = normalized.match(/^features\/([^/]+)\//);
  if (!match) continue;
  const feature = match[1];
  for (const selector of selectors(readFileSync(file, 'utf8'))) {
    const owners = featureOwners.get(selector) || new Set();
    owners.add(feature);
    featureOwners.set(selector, owners);
  }
}

for (const [selector, owners] of featureOwners) {
  if (owners.size > 1) {
    failures.push(`selector "${selector}" is owned by multiple features: ${[...owners].sort().join(', ')}`);
  }
}

if (failures.length) {
  console.error(failures.map((failure) => `- ${failure}`).join('\n'));
  process.exit(1);
}

console.log(`CSS ownership passed for ${cssFiles.length - 1} files.`);

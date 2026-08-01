import { readFile, readdir } from 'node:fs/promises';
import { dirname, extname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';


const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'src');
const SOURCE_EXTENSIONS = new Set(['.ts', '.tsx']);

function normalized(value) {
  return value.replaceAll('\\', '/').replace(/^.*?src\//, '');
}

export function assertImportAllowed(sourcePath, targetPath) {
  const source = normalized(sourcePath);
  const target = normalized(targetPath);
  if (source.startsWith('shared/')) {
    return !target.startsWith('features/');
  }
  const match = source.match(/^features\/([^/]+)\/(model|controller|view)\//);
  if (!match) return true;
  const [, feature, layer] = match;
  const targetFeature = target.match(/^features\/([^/]+)\/(model|controller|view)\//);
  if (!targetFeature) return true;
  const [, otherFeature, targetLayer] = targetFeature;
  if (otherFeature === feature) {
    if (layer === 'model') return targetLayer === 'model';
    if (layer === 'controller') return targetLayer !== 'view';
    return true;
  }
  if (layer === 'view' && targetLayer === 'view') {
    return new RegExp(`^features/${otherFeature}/view(?:/index)?$`).test(target);
  }
  return layer === 'controller' && targetLayer === 'model';
}

async function sourceFiles(directory) {
  const values = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) values.push(...await sourceFiles(path));
    else if (SOURCE_EXTENSIONS.has(extname(entry.name))) values.push(path);
  }
  return values;
}

async function main() {
  const failures = [];
  for (const path of await sourceFiles(ROOT)) {
    const source = await readFile(path, 'utf8');
    const imports = source.matchAll(/(?:from\s+|import\s*\()(['"])([^'"]+)\1/g);
    for (const match of imports) {
      const specifier = match[2];
      if (!specifier.startsWith('.')) continue;
      const target = resolve(dirname(path), specifier);
      if (!assertImportAllowed(relative(ROOT, path), relative(ROOT, target))) {
        failures.push(`${relative(ROOT, path)} -> ${specifier}`);
      }
    }
  }
  if (failures.length) {
    throw new Error(`Feature boundary violations:\n${failures.join('\n')}`);
  }
  process.stdout.write('Frontend feature boundaries passed.\n');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}

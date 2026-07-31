import { readFile, readdir, stat } from 'node:fs/promises';
import { extname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';


const ROOT = resolve(fileURLToPath(new URL('../src', import.meta.url)));
const removed = [
  resolve(ROOT, 'services/api.ts'),
  resolve(ROOT, 'types/index.ts'),
  resolve(ROOT, 'hooks/useSSEChat.ts'),
];
const requiredChatRenderers = [
  'PaperRenderer.tsx',
  'ProgressRenderer.tsx',
  'TextRenderer.tsx',
  'WorkspaceActionRenderer.tsx',
].map((name) => resolve(ROOT, 'features/chat/view/renderers', name));

async function files(directory) {
  const result = [];
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) result.push(...await files(path));
    else if (['.ts', '.tsx'].includes(extname(entry.name))) result.push(path);
  }
  return result;
}

const failures = [];
for (const path of removed) {
  try {
    if ((await stat(path)).isFile()) failures.push(`removed path exists: ${relative(ROOT, path)}`);
  } catch {
    // Expected.
  }
}
for (const path of requiredChatRenderers) {
  try {
    if (!(await stat(path)).isFile()) failures.push(`chat renderer is not a file: ${relative(ROOT, path)}`);
  } catch {
    failures.push(`chat renderer is missing: ${relative(ROOT, path)}`);
  }
}
for (const path of await files(ROOT)) {
  const source = await readFile(path, 'utf8');
  if (/services\/api|types\/index|hooks\/useSSEChat/.test(source)) {
    failures.push(`legacy import in ${relative(ROOT, path)}`);
  }
  if (!relative(ROOT, path).replaceAll('\\', '/').startsWith('shared/')) {
    if (/\bfetch\s*\(/.test(source)) {
      failures.push(`direct fetch outside shared transport: ${relative(ROOT, path)}`);
    }
  }
}
const messageBubblePath = resolve(ROOT, 'features/chat/view/MessageBubble.tsx');
const messageBubble = await readFile(messageBubblePath, 'utf8');
const messageBubbleLines = messageBubble.split(/\r?\n/).length;
if (messageBubbleLines > 1_100) {
  failures.push(`MessageBubble.tsx has ${messageBubbleLines} lines (maximum 1100)`);
}
for (const movedView of ['MarkdownRenderer', 'PaperListCard', 'PaperInlineReader', 'ImageStudioCard']) {
  if (messageBubble.includes(`import ${movedView}`)) {
    failures.push(`MessageBubble still owns moved ${movedView} rendering`);
  }
}
if (failures.length) {
  throw new Error(`Legacy frontend check failed:\n${failures.join('\n')}`);
}
process.stdout.write('Legacy frontend paths and direct feature fetches are absent.\n');

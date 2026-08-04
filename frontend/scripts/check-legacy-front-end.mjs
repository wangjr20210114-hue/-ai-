import { readFile, readdir, stat } from 'node:fs/promises';
import { extname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';


const ROOT = resolve(fileURLToPath(new URL('../src', import.meta.url)));
const removed = [
  resolve(ROOT, 'app/apiComposition.ts'),
  resolve(ROOT, 'App.tsx'),
  resolve(ROOT, 'components/chat/MessageBubble.tsx'),
  resolve(ROOT, 'features/skills/useSkillMarketplaceController.ts'),
  resolve(ROOT, 'services/sse.ts'),
  resolve(ROOT, 'services/sse.test.ts'),
  resolve(ROOT, 'shared/types/index.ts'),
  resolve(ROOT, 'shared/ui/progressLabel.ts'),
  resolve(ROOT, 'services/api.ts'),
  resolve(ROOT, 'types/index.ts'),
  resolve(ROOT, 'hooks/useSSEChat.ts'),
  resolve(ROOT, 'features/maps/view/MapRenderer.tsx'),
  resolve(ROOT, 'features/maps/view/RouteMap.tsx'),
  resolve(ROOT, 'features/maps/view/TravelPlanCard.tsx'),
  resolve(ROOT, 'features/calendar/view/CalendarRenderer.tsx'),
  resolve(ROOT, 'features/calendar/controller/useCalendarController.ts'),
  resolve(ROOT, 'features/chat/controller/useChatTransport.ts'),
  resolve(ROOT, 'features/chat/controller/useConversationLifecycle.ts'),
  resolve(ROOT, 'features/chat/model/events.ts'),
  resolve(ROOT, 'features/chat/model/state.ts'),
  resolve(ROOT, 'features/search/controller/useSearchProgress.ts'),
  resolve(ROOT, 'features/search/model/client.ts'),
  resolve(ROOT, 'features/search/model/progress.ts'),
  resolve(ROOT, 'features/search/view/SearchEvidenceRenderer.tsx'),
];
const removedDirectories = [
  resolve(ROOT, 'components/paper'),
  resolve(ROOT, 'components/profile'),
];
const requiredChatRenderers = [
  'ClarificationCard.tsx',
  'MeetingConfirmationCard.tsx',
  'MessageBubbleView.tsx',
  'MessageExtrasRenderer.tsx',
  'MessagePrimaryRenderer.tsx',
  'PaperRenderer.tsx',
  'ProgressRenderer.tsx',
  'ProactiveRenderer.tsx',
  'TextRenderer.tsx',
  'WorkspaceActionRenderer.tsx',
].map((name) => resolve(ROOT, 'features/chat/view/renderers', name));
const requiredFeatureModels = [
  'features/chat/model/types.ts',
  'features/search/model/types.ts',
  'features/maps/model/types.ts',
  'features/calendar/model/types.ts',
  'features/papers/model/types.ts',
  'features/settings/model/types.ts',
  'features/skills/model/types.ts',
  'features/workspace/model/types.ts',
].map((name) => resolve(ROOT, name));

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
for (const path of removedDirectories) {
  try {
    if ((await stat(path)).isDirectory()) {
      failures.push(`removed directory exists: ${relative(ROOT, path)}`);
    }
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
for (const path of requiredFeatureModels) {
  try {
    if (!(await stat(path)).isFile()) failures.push(`feature model is not a file: ${relative(ROOT, path)}`);
  } catch {
    failures.push(`feature model is missing: ${relative(ROOT, path)}`);
  }
}
for (const path of await files(ROOT)) {
  const source = await readFile(path, 'utf8');
  const sourceName = relative(ROOT, path).replaceAll('\\', '/');
  if (/services\/api|shared\/types|types\/index|hooks\/useSSEChat/.test(source)) {
    failures.push(`legacy import in ${relative(ROOT, path)}`);
  }
  if (!relative(ROOT, path).replaceAll('\\', '/').startsWith('shared/')) {
    if (/\bfetch\s*\(/.test(source)) {
      failures.push(`direct fetch outside shared transport: ${relative(ROOT, path)}`);
    }
  }
  if (
    /^features\/[^/]+\//.test(sourceName)
    && /app\/apiComposition/.test(source)
  ) {
    failures.push(`feature imports app composition: ${sourceName}`);
  }
  if (
    /^features\/[^/]+\/view\//.test(sourceName)
    && /services\/paperApi/.test(source)
  ) {
    failures.push(`feature view bypasses its controller: ${sourceName}`);
  }
}
const messageBubblePath = resolve(ROOT, 'features/chat/view/MessageBubble.tsx');
const messageBubble = await readFile(messageBubblePath, 'utf8');
const messageBubbleLines = messageBubble.split(/\r?\n/).length;
if (messageBubbleLines > 80) {
  failures.push(`MessageBubble.tsx has ${messageBubbleLines} lines (maximum 80)`);
}
for (const movedView of ['MarkdownRenderer', 'PaperListCard', 'PaperInlineReader', 'ImageStudioCard']) {
  if (messageBubble.includes(`import ${movedView}`)) {
    failures.push(`MessageBubble still owns moved ${movedView} rendering`);
  }
}
for (const rendererPath of requiredChatRenderers) {
  const renderer = await readFile(rendererPath, 'utf8');
  const rendererLines = renderer.split(/\r?\n/).length;
  if (rendererLines > 300) {
    failures.push(
      `${relative(ROOT, rendererPath)} has ${rendererLines} lines (maximum 300)`,
    );
  }
  if (/app\/apiComposition|workspaceOperation|proactiveOperation/.test(renderer)) {
    failures.push(
      `${relative(ROOT, rendererPath)} bypasses the chat controller`,
    );
  }
}
if (failures.length) {
  throw new Error(`Legacy frontend check failed:\n${failures.join('\n')}`);
}
process.stdout.write('Legacy frontend paths and direct feature fetches are absent.\n');

import { resolve } from 'node:path';
import { createServer } from 'vite';

export default async function globalSetup() {
  const server = await createServer({
    configFile: resolve(process.cwd(), 'vite.config.ts'),
    server: {
      host: '127.0.0.1',
      port: 41738,
      strictPort: true,
    },
  });
  await server.listen();
  // Prime the same module graph the first page consumes. A clean Vite cache
  // otherwise spends the first test timeout optimizing dependencies while
  // page.goto() is still waiting for the load event.
  await server.transformRequest('/src/main.tsx');
  return async () => {
    await server.close();
  };
}

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
  return async () => {
    await server.close();
  };
}

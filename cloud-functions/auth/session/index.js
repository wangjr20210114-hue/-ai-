import { getStore } from '@edgeone/pages-blob';
import { handleSession } from '../../../auth/controllers/session-controller.js';

export async function onRequest(context) {
  return handleSession({
    ...context,
    profileStore: context.__profileStore
      || getStore({ name: 'yuanbao-files', consistency: 'strong' }),
  });
}

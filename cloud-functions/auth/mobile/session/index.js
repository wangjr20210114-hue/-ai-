import { getStore } from '@edgeone/pages-blob';
import { handleMobileSession } from '../../../../auth/controllers/cloudbase-controller.js';

export async function onRequest(context) {
  return handleMobileSession({
    ...context,
    profileStore: context.__profileStore
      || getStore({ name: 'yuanbao-files', consistency: 'strong' }),
  });
}

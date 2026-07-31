import { handleSession } from '../../../auth/controllers/session-controller.js';

export async function onRequest(context) {
  return handleSession(context);
}

import { handleLogout } from '../../../auth/controllers/session-controller.js';

export async function onRequest(context) {
  return handleLogout(context);
}

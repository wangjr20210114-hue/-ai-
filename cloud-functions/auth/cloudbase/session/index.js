import { handleCloudBaseSession } from '../../../../auth/controllers/cloudbase-controller.js';

export async function onRequest(context) {
  return handleCloudBaseSession(context);
}

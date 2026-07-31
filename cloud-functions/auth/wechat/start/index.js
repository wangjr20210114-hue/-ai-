import { handleWechatStart } from '../../../../auth/controllers/wechat-controller.js';

export async function onRequest(context) {
  return handleWechatStart(context);
}

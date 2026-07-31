import { handleWechatCallback } from '../../../../auth/controllers/wechat-controller.js';

export async function onRequest(context) {
  return handleWechatCallback(context);
}

const TECHNICAL_ERROR = /(?:^|\b)(?:role|keyerror|traceback|stack|internal server error|agent_run_error|invalid_request|provider|model id|api[_ -]?key|gateway)(?:\b|$)/i;
const NETWORK_ERROR = /(?:failed to fetch|load failed|networkerror|network request failed|fetch failed)/i;
const PUBLIC_BUSY_ERROR = /模型服务当前繁忙或配额不足|模型服務目前繁忙或配額不足/i;
const PUBLIC_REQUEST_ERROR = /模型服务暂时未能处理本轮上下文|模型服務暫時無法處理本輪內容/i;
const PUBLIC_SERVICE_ERROR = /(?:模型服务配置异常|消息服务暂时异常|模型服務設定異常|訊息服務暫時異常)/i;

export function presentableChatError(value: unknown): string {
  const message = String(value || '').trim();
  if (NETWORK_ERROR.test(message)) {
    return translate('networkRequestFailed');
  }
  if (PUBLIC_BUSY_ERROR.test(message)) {
    return translate('modelServiceBusy');
  }
  if (PUBLIC_REQUEST_ERROR.test(message)) {
    return translate('modelRequestRejected');
  }
  if (PUBLIC_SERVICE_ERROR.test(message)) {
    return translate('messageServiceFailed');
  }
  if (!message || TECHNICAL_ERROR.test(message)) {
    return translate('messageServiceFailed');
  }
  return message.length > 180 ? `${message.slice(0, 180)}…` : message;
}
import { translate } from '../i18n';

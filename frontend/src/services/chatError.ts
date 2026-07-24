const TECHNICAL_ERROR = /(?:^|\b)(?:role|keyerror|traceback|stack|internal server error|agent_run_error|invalid_request|provider|model id|api[_ -]?key|gateway)(?:\b|$)/i;
const NETWORK_ERROR = /(?:failed to fetch|load failed|networkerror|network request failed|fetch failed)/i;

export function presentableChatError(value: unknown): string {
  const message = String(value || '').trim();
  if (NETWORK_ERROR.test(message)) {
    return translate('networkRequestFailed');
  }
  if (!message || TECHNICAL_ERROR.test(message)) {
    return translate('messageServiceFailed');
  }
  return message.length > 180 ? `${message.slice(0, 180)}…` : message;
}
import { translate } from '../i18n';

const TECHNICAL_ERROR = /(?:^|\b)(?:role|keyerror|traceback|stack|internal server error|agent_run_error|invalid_request|provider|model id|api[_ -]?key|gateway)(?:\b|$)/i;
const NETWORK_ERROR = /(?:failed to fetch|load failed|networkerror|network request failed|fetch failed)/i;

export function presentableChatError(value: unknown): string {
  const message = String(value || '').trim();
  if (NETWORK_ERROR.test(message)) {
    return '网络请求未能送达，请检查连接后重试。原问题不会自动重复发送。';
  }
  if (!message || TECHNICAL_ERROR.test(message)) {
    return '消息服务暂时异常，请重试。本次失败不会保存为 AI 回答；如持续失败，请检查 Preview 的模型配置。';
  }
  return message.length > 180 ? `${message.slice(0, 180)}…` : message;
}

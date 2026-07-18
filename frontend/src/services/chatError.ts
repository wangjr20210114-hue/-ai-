const TECHNICAL_ERROR = /(?:^|\b)(?:role|keyerror|traceback|stack|internal server error|agent_run_error|invalid_request|provider|model id|api[_ -]?key|gateway)(?:\b|$)/i;

export function presentableChatError(value: unknown): string {
  const message = String(value || '').trim();
  if (!message || TECHNICAL_ERROR.test(message)) {
    return '消息服务暂时异常，请重试。本次失败不会保存为 AI 回答；如持续失败，请检查 Preview 的模型配置。';
  }
  return message.length > 180 ? `${message.slice(0, 180)}…` : message;
}

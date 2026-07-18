const TECHNICAL_ERROR = /(?:^|\b)(?:role|keyerror|traceback|stack|internal server error|agent_run_error)(?:\b|$)/i;

export function presentableChatError(value: unknown): string {
  const message = String(value || '').trim();
  if (!message || TECHNICAL_ERROR.test(message)) {
    return '消息服务暂时异常，请稍后重试；本次失败不会被当作 AI 回答保存。';
  }
  return message.length > 180 ? `${message.slice(0, 180)}…` : message;
}

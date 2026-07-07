import type { WSMessage } from '../types';

type Listener = (msg: WSMessage) => void;

/** WebSocket 连接管理：心跳保活 + 断线重连。 */
export class WSClient {
  private ws: WebSocket | null = null;
  private url: string;
  private listeners = new Set<Listener>();
  private heartbeat?: number;
  private reconnectTimer?: number;
  private manualClose = false;

  constructor(sessionId: string) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    this.url = `${proto}://${location.host}/ws/${sessionId}`;
  }

  connect(onOpen?: () => void, onClose?: () => void) {
    this.manualClose = false;
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      onOpen?.();
      this.heartbeat = window.setInterval(() => this.send({ type: 'ping', payload: {} }), 20000);
    };

    this.ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data) as WSMessage;
        this.listeners.forEach((l) => l(msg));
      } catch {
        // ignore malformed
      }
    };

    this.ws.onclose = () => {
      window.clearInterval(this.heartbeat);
      onClose?.();
      if (!this.manualClose) {
        this.reconnectTimer = window.setTimeout(() => this.connect(onOpen, onClose), 2000);
      }
    };
  }

  send(msg: WSMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  on(listener: Listener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  close() {
    this.manualClose = true;
    window.clearInterval(this.heartbeat);
    window.clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}

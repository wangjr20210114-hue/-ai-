import type { WSMessage } from '../types';
import { getLocalAccessToken } from './auth';

type Listener = (msg: WSMessage) => void;

/** WebSocket 连接管理：本地令牌 + 心跳保活 + 断线重连。 */
export class WSClient {
  private ws: WebSocket | null = null;
  private baseUrl: string;
  private listeners = new Set<Listener>();
  private heartbeat?: number;
  private reconnectTimer?: number;
  private manualClose = false;
  private generation = 0;

  constructor(sessionId: string) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const host = location.host.includes('edgeone') ? '94.16.110.28:8000' : location.host;
    this.baseUrl = `${proto}://${host}/ws/${encodeURIComponent(sessionId)}`;
  }

  connect(onOpen?: () => void, onClose?: () => void) {
    this.manualClose = false;
    const generation = ++this.generation;
    void getLocalAccessToken()
      .then((token) => {
        if (this.manualClose || generation !== this.generation) return;
        this.ws = new WebSocket(this.baseUrl, [`agent-token.${token}`]);

        this.ws.onopen = () => {
          onOpen?.();
          this.heartbeat = window.setInterval(() => this.send({ type: 'ping', payload: {} }), 20000);
        };

        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data) as WSMessage;
            this.listeners.forEach((listener) => listener(message));
          } catch {
            // Ignore malformed transport frames; backend validation handles client frames.
          }
        };

        this.ws.onclose = () => {
          window.clearInterval(this.heartbeat);
          onClose?.();
          if (!this.manualClose && generation === this.generation) {
            this.reconnectTimer = window.setTimeout(() => this.connect(onOpen, onClose), 2000);
          }
        };
      })
      .catch(() => {
        onClose?.();
        if (!this.manualClose && generation === this.generation) {
          this.reconnectTimer = window.setTimeout(() => this.connect(onOpen, onClose), 2000);
        }
      });
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
    this.generation += 1;
    window.clearInterval(this.heartbeat);
    window.clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
  }
}

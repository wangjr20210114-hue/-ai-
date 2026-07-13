import type { WSMessage } from '../types';
import { getLocalAccessToken } from './auth';
import type { ChatClient } from './chatClient';

type Listener = (message: WSMessage) => void;
type PageLocation = Pick<Location, 'protocol' | 'host'>;

export function buildWebSocketUrl(sessionId: string, page: PageLocation): string {
  const protocol = page.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${page.host}/ws/${encodeURIComponent(sessionId)}`;
}

/** Local FastAPI transport: token subprotocol, heartbeat and reconnect. */
export class WSClient implements ChatClient {
  private ws: WebSocket | null = null;
  private readonly baseUrl: string;
  private readonly listeners = new Set<Listener>();
  private heartbeat?: number;
  private reconnectTimer?: number;
  private manualClose = false;
  private generation = 0;

  constructor(sessionId: string) {
    this.baseUrl = buildWebSocketUrl(sessionId, window.location);
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
          this.heartbeat = window.setInterval(
            () => this.send({ type: 'ping', payload: {} }),
            20_000,
          );
        };
        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(String(event.data)) as WSMessage;
            for (const listener of this.listeners) listener(message);
          } catch {
            // Ignore malformed server frames; valid frames are JSON WSMessage objects.
          }
        };
        this.ws.onclose = () => {
          window.clearInterval(this.heartbeat);
          onClose?.();
          if (!this.manualClose && generation === this.generation) {
            this.reconnectTimer = window.setTimeout(
              () => this.connect(onOpen, onClose),
              2_000,
            );
          }
        };
      })
      .catch(() => {
        onClose?.();
        if (!this.manualClose && generation === this.generation) {
          this.reconnectTimer = window.setTimeout(
            () => this.connect(onOpen, onClose),
            2_000,
          );
        }
      });
  }

  send(rawMessage: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(rawMessage as WSMessage));
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

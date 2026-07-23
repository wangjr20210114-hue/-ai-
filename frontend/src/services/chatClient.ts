/** Minimal client interface shared by the local and Makers transports. */
export interface ChatClient {
  send(message: unknown): Promise<void> | void;
  stop?(): Promise<'confirmed' | 'local'>;
  close(): void;
}

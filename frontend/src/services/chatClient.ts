/** Minimal client interface shared by WSClient and SSEChatClient. */
export interface ChatClient {
  send(msg: any): Promise<void> | void;
  close(): void;
}

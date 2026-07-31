import { useChatRuntime } from './chatRuntime';


export function useChatController() {
  return useChatRuntime();
}

export * from './chatRuntime';

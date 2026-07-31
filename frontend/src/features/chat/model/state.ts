import type { RichMediaAsset } from '../../../types';


export interface ChatControllerState {
  progress: {
    stage: string;
  };
  streamingText: string;
  search: {
    media: RichMediaAsset[];
  };
  terminal: 'active' | 'done' | 'error';
  error: string;
}

export const initialChatControllerState: ChatControllerState = {
  progress: { stage: 'planning' },
  streamingText: '',
  search: { media: [] },
  terminal: 'active',
  error: '',
};

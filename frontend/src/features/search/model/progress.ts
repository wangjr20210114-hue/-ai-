import type { RichMediaAsset } from './types';


export interface SearchProgressState {
  stage: string;
  media: RichMediaAsset[];
}

export const initialSearchProgress: SearchProgressState = {
  stage: 'planning',
  media: [],
};

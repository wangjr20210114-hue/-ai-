import type { ChatMessage } from '../../../shared/types';
import TravelPlanCard from './TravelPlanCard';


export function MapRenderer({ message }: { message: ChatMessage }) {
  if (!message.travelPlanData) return null;
  return <TravelPlanCard plan={message.travelPlanData} />;
}

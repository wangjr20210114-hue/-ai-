import TravelPlanCard from '../../../components/travel/TravelPlanCard';
import type { ChatMessage } from '../../../types';


export function MapRenderer({ message }: { message: ChatMessage }) {
  if (!message.travelPlanData) return null;
  return <TravelPlanCard plan={message.travelPlanData} />;
}

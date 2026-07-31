import type { ChatMessage } from '../../../shared/types';


export function CalendarRenderer({ message }: { message: ChatMessage }) {
  if (!message.parsedSchedules?.length) return null;
  return (
    <div className="schedule-summary" data-schedule-count={message.parsedSchedules.length}>
      {message.parsedSchedules.map((schedule) => schedule.title || '').filter(Boolean).join(' · ')}
    </div>
  );
}

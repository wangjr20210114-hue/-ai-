import { useEffect, useMemo, useState } from 'react';

import { calendarDateKey, calendarMonthCells, groupSchedulesByDate, type ScheduleItem } from '../model';

interface CalendarPulse { date: string; count: number; token: number }

export function useCalendarWorkspaceController(
  schedules: ScheduleItem[], pulse: CalendarPulse | null, onPulseConsumed: () => void,
) {
  const [currentMonth, setCurrentMonth] = useState(() => { const now = new Date(); return new Date(now.getFullYear(), now.getMonth(), 1); });
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [dayViewOpen, setDayViewOpen] = useState(false);
  useEffect(() => {
    if (!pulse) return;
    const target = new Date(`${pulse.date}T00:00:00`);
    if (Number.isNaN(target.getTime())) return;
    setCurrentMonth(new Date(target.getFullYear(), target.getMonth(), 1));
    setSelectedDate(target);
    setDayViewOpen(true);
    const timer = window.setTimeout(onPulseConsumed, 2600);
    return () => window.clearTimeout(timer);
  }, [onPulseConsumed, pulse]);
  const calendarDays = useMemo(() => calendarMonthCells(currentMonth), [currentMonth]);
  const schedulesByDate = useMemo(() => groupSchedulesByDate(schedules), [schedules]);
  const selectedItems = schedulesByDate.get(calendarDateKey(selectedDate)) || [];
  return { calendarDays, currentMonth, dayViewOpen, schedulesByDate, selectedDate, selectedItems, setCurrentMonth, setDayViewOpen, setSelectedDate };
}

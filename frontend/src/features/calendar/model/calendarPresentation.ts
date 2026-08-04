import type { ScheduleItem } from './types';

export function calendarDateKey(date: Date): string {
  return [date.getFullYear(), String(date.getMonth() + 1).padStart(2, '0'), String(date.getDate()).padStart(2, '0')].join('-');
}

export function isPastCalendarDate(date: Date, now = new Date()): boolean {
  return calendarDateKey(date) < calendarDateKey(now);
}

export function calendarMonthCells(month: Date): Array<Date | null> {
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const offset = new Date(year, monthIndex, 1).getDay();
  const count = new Date(year, monthIndex + 1, 0).getDate();
  const cells: Array<Date | null> = Array.from({ length: offset }, () => null);
  for (let day = 1; day <= count; day += 1) cells.push(new Date(year, monthIndex, day));
  while (cells.length < 42) cells.push(null);
  return cells;
}

export function groupSchedulesByDate(schedules: ScheduleItem[]) {
  const result = new Map<string, ScheduleItem[]>();
  schedules.forEach((item) => {
    const key = calendarDateKey(new Date(item.start_time * 1000));
    result.set(key, [...(result.get(key) || []), item]);
  });
  result.forEach((items) => items.sort((left, right) => left.start_time - right.start_time));
  return result;
}

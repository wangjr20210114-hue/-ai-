export interface CalendarSchedule {
  id?: string
  title?: string
  start_time?: number
  duration_minutes?: number
  location?: string
  description?: string
  category?: string
  extra?: {
    place?: Record<string, unknown>
    [key: string]: unknown
  }
}

export function localDateValue(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function localTimeValue(date: Date): string {
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

export function localTimestamp(date: string, time: string): number {
  const [year, month, day] = date.split('-').map(Number)
  const [hour, minute] = time.split(':').map(Number)
  return Math.floor(new Date(year, month - 1, day, hour, minute, 0, 0).getTime() / 1000)
}

export function todayValue(now = new Date()): string {
  return localDateValue(now)
}

export function isPastCalendarDay(date: string, now = new Date()): boolean {
  return date < todayValue(now)
}

export function schedulesForDay(schedules: CalendarSchedule[], date: string): CalendarSchedule[] {
  return schedules
    .filter((schedule) => localDateValue(new Date(Number(schedule.start_time || 0) * 1000)) === date)
    .sort((left, right) => Number(left.start_time || 0) - Number(right.start_time || 0))
}

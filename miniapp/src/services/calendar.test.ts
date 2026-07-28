import { describe, expect, it } from 'vitest'
import {
  isPastCalendarDay,
  localDateValue,
  localTimeValue,
  localTimestamp,
  schedulesForDay,
} from './calendar'

describe('calendar helpers', () => {
  it('round trips local date and time values', () => {
    const value = new Date(2026, 6, 28, 8, 35)
    expect(localDateValue(value)).toBe('2026-07-28')
    expect(localTimeValue(value)).toBe('08:35')
    expect(localTimestamp('2026-07-28', '08:35')).toBe(Math.floor(value.getTime() / 1000))
  })

  it('keeps the selected day in chronological order', () => {
    const morning = localTimestamp('2026-07-28', '08:00')
    const evening = localTimestamp('2026-07-28', '18:00')
    expect(schedulesForDay([
      { id: 'late', start_time: evening },
      { id: 'other', start_time: localTimestamp('2026-07-29', '08:00') },
      { id: 'early', start_time: morning },
    ], '2026-07-28').map((item) => item.id)).toEqual(['early', 'late'])
  })

  it('protects dates before today without blocking today', () => {
    const now = new Date(2026, 6, 28, 12)
    expect(isPastCalendarDay('2026-07-27', now)).toBe(true)
    expect(isPastCalendarDay('2026-07-28', now)).toBe(false)
  })
})

import { Button } from 'tdesign-react';
import { ChevronLeftIcon, ChevronRightIcon } from 'tdesign-icons-react';
import { calendarDateKey, type ScheduleItem } from '../model';
import { useLanguage } from '../../../i18n';

interface Props {
  calendarDays: Array<Date | null>; currentMonth: Date; hidden: boolean; locale: string;
  pulseDate?: string; schedulesByDate: Map<string, ScheduleItem[]>; selectedDate: Date;
  onMonthChange: (month: Date) => void; onSelectDate: (date: Date) => void;
}

export function CalendarMonthView({ calendarDays, currentMonth, hidden, locale, pulseDate, schedulesByDate, selectedDate, onMonthChange, onSelectDate }: Props) {
  const { t } = useLanguage();
  const monthLabel = currentMonth.toLocaleDateString(locale, { year: 'numeric', month: 'long' });
  const weekdays = Array.from({ length: 7 }, (_, index) => new Intl.DateTimeFormat(locale, { weekday: 'narrow' }).format(new Date(2023, 0, 1 + index)));
  const today = calendarDateKey(new Date());
  const selected = calendarDateKey(selectedDate);
  return <section className="calendar-workspace-pane calendar-month-pane" aria-hidden={hidden}>
    <div className="calendar-header">
      <Button variant="text" size="small" icon={<ChevronLeftIcon />} aria-label={t('previousMonth')} title={t('previousMonth')} onClick={() => onMonthChange(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))} />
      <span className="calendar-month-label">{monthLabel}</span>
      <Button variant="text" size="small" icon={<ChevronRightIcon />} aria-label={t('nextMonth')} title={t('nextMonth')} onClick={() => onMonthChange(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))} />
    </div>
    <div className="calendar-weekdays">{weekdays.map((weekday, index) => <div key={`${weekday}-${index}`} className="calendar-weekday">{weekday}</div>)}</div>
    <div className="calendar-grid">{calendarDays.map((date, index) => {
      if (!date) return <div key={`empty-${index}`} className="calendar-day empty" />;
      const key = calendarDateKey(date); const count = schedulesByDate.get(key)?.length || 0;
      return <button key={key} tabIndex={hidden ? -1 : 0} className={`calendar-day ${count ? 'has-events' : ''} ${today === key ? 'today' : ''} ${selected === key ? 'selected' : ''} ${pulseDate === key ? 'calendar-day-pulse' : ''}`} onClick={() => onSelectDate(date)} title={count ? t('scheduleItems', { count }) : t('noSchedule')}>
        <span className="calendar-day-num">{date.getDate()}</span>{count > 0 && <span className="calendar-day-dot" />}
      </button>;
    })}</div>
  </section>;
}

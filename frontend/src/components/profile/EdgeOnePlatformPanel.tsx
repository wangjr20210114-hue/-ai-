import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { ArrowLeftIcon, ChevronLeftIcon, ChevronRightIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import { intelligenceOperation, searchMakersPlaces, workspaceOperation } from '../../services/api';
import type { MakersMapPlace, ScheduleItem } from '../../types';
import MakersMap from './MakersMap';
import ReadingLibraryPanel from './ReadingLibraryPanel';
import { useLanguage } from '../../i18n';
const EMPTY_SCHEDULES: ScheduleItem[] = [];

function dateKey(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

function isPastCalendarDate(date: Date, now = new Date()): boolean {
  return dateKey(date) < dateKey(now);
}

export default function EdgeOnePlatformPanel() {
  const { language, t } = useLanguage();
  const locale = language === 'zh-TW' ? 'zh-TW' : language === 'en' ? 'en' : 'zh-CN';
  const dispatch = useAppDispatch();
  const { conversationId, schedules, mapPlaces, mapTitle, mapRevision, calendarPulse } = useAppState();
  const [currentMonth, setCurrentMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [selectedDate, setSelectedDate] = useState(() => new Date());
  const [showRecommendation, setShowRecommendation] = useState(true);
  const [editingId, setEditingId] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [formTitle, setFormTitle] = useState('');
  const [formStart, setFormStart] = useState('');
  const [formEnd, setFormEnd] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [placeQuery, setPlaceQuery] = useState('');
  const [placeOptions, setPlaceOptions] = useState<MakersMapPlace[]>([]);
  const [placeOptionsOpen, setPlaceOptionsOpen] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<MakersMapPlace | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [placeSearchBusy, setPlaceSearchBusy] = useState(false);
  const [dayViewOpen, setDayViewOpen] = useState(false);
  const [deleteConfirmId, setDeleteConfirmId] = useState('');
  const [skillPreferences, setSkillPreferences] = useState<Record<string, boolean>>({});
  const placePickerRef = useRef<HTMLDivElement>(null);
  const autoDescriptionRef = useRef('');

  useEffect(() => {
    if (mapPlaces.length) setShowRecommendation(true);
  }, [mapRevision, mapPlaces.length]);

  useEffect(() => {
    let disposed = false;
    void intelligenceOperation(conversationId).then((state) => {
      if (!disposed) setSkillPreferences(state.skill_preferences || {});
    }).catch(() => { /* The panel keeps defaults while the store reconnects. */ });
    const changed = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, boolean>>).detail;
      if (detail) setSkillPreferences(detail);
    };
    window.addEventListener('yuanbao:skills-changed', changed);
    return () => { disposed = true; window.removeEventListener('yuanbao:skills-changed', changed); };
  }, [conversationId]);

  useEffect(() => {
    if (!calendarPulse) return;
    const target = new Date(`${calendarPulse.date}T00:00:00`);
    if (Number.isNaN(target.getTime())) return;
    setCurrentMonth(new Date(target.getFullYear(), target.getMonth(), 1));
    setSelectedDate(target);
    setDayViewOpen(true);
    const timer = window.setTimeout(() => dispatch({ type: 'CLEAR_CALENDAR_PULSE', payload: {} }), 2600);
    return () => window.clearTimeout(timer);
  }, [calendarPulse, dispatch]);

  const calendarDays = useMemo(() => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const offset = new Date(year, month, 1).getDay();
    const count = new Date(year, month + 1, 0).getDate();
    const cells: Array<Date | null> = Array.from({ length: offset }, () => null);
    for (let day = 1; day <= count; day += 1) cells.push(new Date(year, month, day));
    while (cells.length < 42) cells.push(null);
    return cells;
  }, [currentMonth]);

  const schedulesByDate = useMemo(() => {
    const result = new Map<string, typeof schedules>();
    schedules.forEach((item) => {
      const key = dateKey(new Date(item.start_time * 1000));
      result.set(key, [...(result.get(key) || []), item]);
    });
    result.forEach((items) => items.sort((a, b) => a.start_time - b.start_time));
    return result;
  }, [schedules]);

  const selectedItems = schedulesByDate.get(dateKey(selectedDate)) || EMPTY_SCHEDULES;
  const schedulePlaces = useMemo(
    () => selectedItems
      .map((item) => item.extra?.place)
      .filter((place): place is NonNullable<typeof place> => Boolean(place)),
    [selectedItems],
  );
  const effectivePlaces = useMemo(
    () => showRecommendation && mapPlaces.length ? mapPlaces : schedulePlaces,
    [showRecommendation, mapPlaces, schedulePlaces],
  );
  const effectiveTitle = showRecommendation && mapPlaces.length
    ? mapTitle
    : t('daySchedule', { date: selectedDate.toLocaleDateString(locale, { month: 'long', day: 'numeric' }) });
  const showingRecommendation = showRecommendation && mapPlaces.length > 0;
  const showingScheduleRoute = !showingRecommendation && schedulePlaces.length >= 2;
  const monthLabel = currentMonth.toLocaleDateString(locale, { year: 'numeric', month: 'long' });
  const weekdays = useMemo(() => Array.from({ length: 7 }, (_, index) => {
    const date = new Date(2023, 0, 1 + index);
    return new Intl.DateTimeFormat(locale, { weekday: 'narrow' }).format(date);
  }), [locale]);
  const selectedDateIsPast = isPastCalendarDate(selectedDate);
  const todayKey = dateKey(new Date());
  const mapsEnabled = skillPreferences.maps !== false;
  const calendarEnabled = skillPreferences.calendar !== false;

  const openScheduleForm = (item?: ScheduleItem) => {
    if (!calendarEnabled) {
      MessagePlugin.info(t('enableCalendarFirst'));
      window.dispatchEvent(new CustomEvent('yuanbao:open-skills'));
      return;
    }
    if (isPastCalendarDate(item ? new Date(item.start_time * 1000) : selectedDate)) {
      MessagePlugin.warning(t('pastScheduleReadOnly'));
      return;
    }
    const start = item ? new Date(item.start_time * 1000) : new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate(), 9, 0);
    const local = new Date(start.getTime() - start.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
    const end = new Date(start.getTime() + (item?.duration_minutes || 60) * 60_000);
    const localEnd = new Date(end.getTime() - end.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
    setEditingId(item?.id || '');
    setDeleteConfirmId('');
    setFormTitle(item?.title || '');
    setFormStart(local);
    setFormEnd(localEnd);
    setFormDescription(item?.description || '');
    autoDescriptionRef.current = '';
    setSelectedPlace(item?.extra?.place || null);
    setPlaceQuery(item?.extra?.place?.name || item?.location || '');
    setPlaceOptions([]);
    setPlaceOptionsOpen(false);
    setFormOpen(true);
  };

  useEffect(() => {
    if (!formOpen || !mapsEnabled) return;
    const closeOnOutside = (event: PointerEvent) => {
      if (!placePickerRef.current?.contains(event.target as Node)) setPlaceOptionsOpen(false);
    };
    document.addEventListener('pointerdown', closeOnOutside);
    return () => document.removeEventListener('pointerdown', closeOnOutside);
  }, [formOpen, mapsEnabled]);

  useEffect(() => {
    if (!formOpen || !mapsEnabled) {
      setPlaceOptions([]);
      setPlaceOptionsOpen(false);
      setPlaceSearchBusy(false);
      return;
    }
    const query = placeQuery.trim();
    if (selectedPlace && query === selectedPlace.name) {
      setPlaceOptions([]);
      setPlaceOptionsOpen(false);
      setPlaceSearchBusy(false);
      return;
    }
    if (query.length < 2) {
      setPlaceOptions([]);
      setPlaceOptionsOpen(false);
      setPlaceSearchBusy(false);
      return;
    }
    let disposed = false;
    const timer = window.setTimeout(() => {
      setPlaceSearchBusy(true);
      void searchMakersPlaces(conversationId, query)
        .then((places) => {
          if (!disposed) {
            setPlaceOptions(places);
            setPlaceOptionsOpen(places.length > 0);
          }
        })
        .catch((error) => {
          if (!disposed) MessagePlugin.error(error instanceof Error ? error.message : t('placeSearchFailed'));
        })
        .finally(() => { if (!disposed) setPlaceSearchBusy(false); });
    }, 350);
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [conversationId, formOpen, mapsEnabled, placeQuery, selectedPlace, t]);

  const selectPlace = (place: MakersMapPlace) => {
    setSelectedPlace(place);
    setPlaceQuery(place.name);
    setPlaceOptions([]);
    setPlaceOptionsOpen(false);
    setFormDescription((current) => {
      const nextAuto = t('goToPlaceDescription', {
        name: place.name,
        address: place.address ? t('parenthesizedAddress', { address: place.address }) : '',
      });
      if (!current.trim() || current === autoDescriptionRef.current) {
        autoDescriptionRef.current = nextAuto;
        return nextAuto;
      }
      return current;
    });
  };

  const saveSchedule = async () => {
    if (!formTitle.trim() || !formStart || !formEnd) {
      MessagePlugin.warning(t('scheduleRequiredFields'));
      return;
    }
    if (mapsEnabled && placeQuery.trim() && !selectedPlace) {
      MessagePlugin.warning(t('selectVerifiedPlace'));
      return;
    }
    const startTime = Math.floor(new Date(formStart).getTime() / 1000);
    const endTime = Math.floor(new Date(formEnd).getTime() / 1000);
    if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime <= startTime) {
      MessagePlugin.warning(t('endAfterStart'));
      return;
    }
    if (isPastCalendarDate(new Date(startTime * 1000))) {
      MessagePlugin.warning(t('cannotSchedulePast'));
      return;
    }
    setFormBusy(true);
    try {
      const durationMinutes = Math.max(1, Math.round((endTime - startTime) / 60));
      const response = await workspaceOperation(conversationId, 'direct_calendar_changes', {
        changes: [{
          operation: editingId ? 'update' : 'create',
          ...(editingId ? { schedule_id: editingId } : {}),
          event: {
            title: formTitle.trim(), start_time: startTime, duration_minutes: durationMinutes,
            description: formDescription.trim(),
            category: 'travel',
            ...(selectedPlace ? { place: selectedPlace, location: selectedPlace.address || selectedPlace.name } : {}),
          },
        }],
      });
      dispatch({ type: 'SET_SCHEDULES', payload: response.schedules });
      const savedDate = new Date(startTime * 1000);
      setSelectedDate(savedDate);
      setCurrentMonth(new Date(savedDate.getFullYear(), savedDate.getMonth(), 1));
      setFormOpen(false);
      setEditingId('');
      setPlaceOptionsOpen(false);
      setShowRecommendation(false);
      MessagePlugin.success(editingId ? t('scheduleUpdated') : t('scheduleAdded'));
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('saveFailed'));
    } finally {
      setFormBusy(false);
    }
  };

  const deleteSchedule = async (item: ScheduleItem) => {
    if (isPastCalendarDate(new Date(item.start_time * 1000))) {
      MessagePlugin.warning(t('pastScheduleCannotDelete'));
      return;
    }
    try {
      const response = await workspaceOperation(conversationId, 'direct_calendar_changes', {
        changes: [{ operation: 'delete', schedule_id: item.id }],
      });
      dispatch({ type: 'SET_SCHEDULES', payload: response.schedules });
      dispatch({ type: 'CLEAR_CALENDAR_PULSE', payload: {} });
      if (editingId === item.id) { setFormOpen(false); setEditingId(''); }
      setDeleteConfirmId('');
      setShowRecommendation(false);
      MessagePlugin.success(t('scheduleDeleted'));
    } catch (error) {
      MessagePlugin.error(error instanceof Error ? error.message : t('deleteFailed'));
    }
  };

  const closeScheduleForm = () => {
    setFormOpen(false);
    setEditingId('');
    setDeleteConfirmId('');
    setPlaceOptionsOpen(false);
  };

  const scheduleForm = (
    <div className={`makers-schedule-form schedule-inline-editor ${editingId ? 'is-editing' : 'is-creating'}`} aria-label={editingId ? t('editSchedule') : t('addSchedule')}>
      <div className="schedule-inline-heading">
        <strong>{editingId ? t('editThisSchedule') : t('addNewSchedule')}</strong>
        <button type="button" aria-label={t('closeScheduleEditor')} title={t('closeScheduleEditor')} onClick={closeScheduleForm}>×</button>
      </div>
      <input value={formTitle} onInput={(event) => setFormTitle(event.currentTarget.value)} placeholder={t('scheduleTitle')} maxLength={120} />
      <div className="makers-schedule-datetime">
        <label>{t('date')}<input aria-label={t('scheduleDate')} type="date" min={todayKey} value={formStart.slice(0, 10)} onInput={(event) => {
          const date = event.currentTarget.value;
          setFormStart(`${date}T${formStart.slice(11, 16) || '09:00'}`);
          setFormEnd(`${date}T${formEnd.slice(11, 16) || '10:00'}`);
        }} /></label>
        <label>{t('startTime')}<input aria-label={t('scheduleStartTime')} type="time" value={formStart.slice(11, 16)} onInput={(event) => setFormStart(`${formStart.slice(0, 10) || dateKey(selectedDate)}T${event.currentTarget.value}`)} /></label>
        <label>{t('endTime')}<input aria-label={t('scheduleEndTime')} type="time" value={formEnd.slice(11, 16)} onInput={(event) => setFormEnd(`${formEnd.slice(0, 10) || formStart.slice(0, 10) || dateKey(selectedDate)}T${event.currentTarget.value}`)} /></label>
      </div>
      <textarea value={formDescription} onChange={(event) => { setFormDescription(event.target.value); autoDescriptionRef.current = ''; }} placeholder={t('scheduleDescriptionPlaceholder')} maxLength={1000} rows={3} />
      {mapsEnabled ? <>
        <div className="makers-place-picker" ref={placePickerRef}>
          <div className="makers-place-search-row makers-place-autocomplete">
            <input
              value={placeQuery}
              onFocus={() => { if (placeOptions.length) setPlaceOptionsOpen(true); }}
              onKeyDown={(event) => { if (event.key === 'Escape') setPlaceOptionsOpen(false); }}
              onChange={(event) => { setPlaceQuery(event.target.value); setSelectedPlace(null); setPlaceOptionsOpen(true); }}
              placeholder={t('placeSearchPlaceholder')}
            />
            {placeSearchBusy && <span className="makers-place-searching">{t('searching')}</span>}
            {placeOptionsOpen && <button type="button" className="makers-place-close" aria-label={t('closePlaceSuggestions')} title={t('closePlaceSuggestions')} onClick={() => setPlaceOptionsOpen(false)}>×</button>}
          </div>
          {placeOptionsOpen && placeOptions.length > 0 && (
            <div className="makers-place-options">
              {placeOptions.map((place) => (
                <button key={place.place_id} type="button" onMouseDown={(event) => event.preventDefault()} onClick={() => selectPlace(place)}>
                  <b>{place.name}</b><span>{place.address}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        {selectedPlace && <div className="makers-selected-place">{t('selectedPlace', { name: selectedPlace.name })}</div>}
      </> : <div className="schedule-map-dependency">
        <span>{t('scheduleWithoutMap')}</span>
        <button type="button" onClick={() => window.dispatchEvent(new CustomEvent('yuanbao:open-skills'))}>{t('enableNow')}</button>
      </div>}
      <div className="makers-form-actions">
        <Button size="small" theme="primary" loading={formBusy} onClick={() => void saveSchedule()}>{editingId ? t('confirmUpdate') : t('confirmAdd')}</Button>
        <Button size="small" variant="outline" onClick={closeScheduleForm}>{t('cancel')}</Button>
      </div>
    </div>
  );

  return (
    <aside className="my-panel makers-workspace">
      <div className="my-panel-card makers-map-card">
        {mapsEnabled
          ? <MakersMap
            conversationId={conversationId}
            title={effectiveTitle}
            places={effectivePlaces}
            revision={mapRevision}
            showRoute={showingScheduleRoute}
            optimize={showingScheduleRoute}
          />
          : <div className="workspace-skill-disabled"><span>⌖</span><strong>{t('mapSkillDisabled')}</strong><small>{t('mapSkillDisabledDetail')}</small><button type="button" onClick={() => window.dispatchEvent(new CustomEvent('yuanbao:open-skills'))}>{t('enableInSkills')}</button></div>}
      </div>

      <div className={`my-panel-card calendar-panel calendar-workspace-card ${dayViewOpen ? 'is-day-view' : ''}`}>
        {calendarPulse && (
          <div key={calendarPulse.token} className="calendar-write-notice">
            {t('schedulesWritten', { count: calendarPulse.count })}
          </div>
        )}
        <div className="calendar-workspace-viewport">
          <section className="calendar-workspace-pane calendar-month-pane" aria-hidden={dayViewOpen}>
            <div className="calendar-header">
              <Button variant="text" size="small" icon={<ChevronLeftIcon />} aria-label={t('previousMonth')} title={t('previousMonth')} onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))} />
              <span className="calendar-month-label">{monthLabel}</span>
              <Button variant="text" size="small" icon={<ChevronRightIcon />} aria-label={t('nextMonth')} title={t('nextMonth')} onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))} />
            </div>
            <div className="calendar-weekdays">
              {weekdays.map((weekday, index) => <div key={`${weekday}-${index}`} className="calendar-weekday">{weekday}</div>)}
            </div>
            <div className="calendar-grid">
              {calendarDays.map((date, index) => {
                if (!date) return <div key={`empty-${index}`} className="calendar-day empty" />;
                const key = dateKey(date);
                const count = schedulesByDate.get(key)?.length || 0;
                const isPulse = calendarPulse?.date === key;
                const isToday = dateKey(new Date()) === key;
                const isSelected = dateKey(selectedDate) === key;
                return (
                  <button
                    key={key}
                    tabIndex={dayViewOpen ? -1 : 0}
                    className={`calendar-day ${count ? 'has-events' : ''} ${isToday ? 'today' : ''} ${isSelected ? 'selected' : ''} ${isPulse ? 'calendar-day-pulse' : ''}`}
                    onClick={() => { setSelectedDate(date); setShowRecommendation(false); setDayViewOpen(true); }}
                    title={count ? t('scheduleItems', { count }) : t('noSchedule')}
                  >
                    <span className="calendar-day-num">{date.getDate()}</span>
                    {count > 0 && <span className="calendar-day-dot" />}
                  </button>
                );
              })}
            </div>
          </section>

          <section className="calendar-workspace-pane calendar-day-pane" aria-hidden={!dayViewOpen}>
            <div className="calendar-day-toolbar">
              <Button shape="circle" variant="text" size="small" icon={<ArrowLeftIcon />} aria-label={t('backToCalendar')} title={t('backToCalendar')} onClick={() => { setDayViewOpen(false); closeScheduleForm(); }} />
              <div className="calendar-day-heading">
                <strong>{t('daySchedule', { date: selectedDate.toLocaleDateString(locale, { month: 'long', day: 'numeric' }) })}</strong>
                <span>{t('itemCount', { count: selectedItems.length })}</span>
              </div>
              <Button size="small" variant="text" disabled={selectedDateIsPast || !calendarEnabled} title={!calendarEnabled ? t('enableCalendarFirst') : undefined} onClick={() => openScheduleForm()}>＋ {t('add')}</Button>
            </div>
            <div className="calendar-day-scroll">
              {formOpen && !editingId && scheduleForm}
              {selectedItems.length === 0 ? (
                <div className="makers-day-empty">{t('dayEmpty')}</div>
              ) : (
                <div className="makers-day-list">
                  {selectedItems.map((item) => {
                    const start = new Date(item.start_time * 1000);
                    const end = new Date((item.start_time + item.duration_minutes * 60) * 1000);
                    return (
                      <div key={item.id} className={`makers-day-item-shell ${formOpen && editingId === item.id ? 'is-editing' : ''}`}>
                        <div className="makers-day-item">
                          <div className="makers-day-time">
                            {start.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false })}
                            <span>{end.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12: false })}</span>
                          </div>
                          <div className="makers-day-content">
                            <div className="makers-day-title">{item.title}</div>
                            {item.location && <div className="makers-day-location">📍 {item.location}</div>}
                            {item.description && <div className="makers-day-description">{item.description}</div>}
                            {!selectedDateIsPast && calendarEnabled && (
                              <div className="makers-day-actions">
                                <button type="button" aria-expanded={formOpen && editingId === item.id} onClick={() => openScheduleForm(item)}>{t('edit')}</button>
                                <button type="button" aria-expanded={deleteConfirmId === item.id} onClick={() => { closeScheduleForm(); setDeleteConfirmId(item.id); }}>{t('delete')}</button>
                              </div>
                            )}
                          </div>
                        </div>
                        {formOpen && editingId === item.id && scheduleForm}
                        {deleteConfirmId === item.id && <div className="schedule-inline-delete" role="alert">
                          <span>{t('confirmDeleteSchedule', { title: item.title })}</span>
                          <div><button type="button" onClick={() => void deleteSchedule(item)}>{t('confirmDelete')}</button><button type="button" onClick={() => setDeleteConfirmId('')}>{t('cancel')}</button></div>
                        </div>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>

      <ReadingLibraryPanel />
    </aside>
  );
}

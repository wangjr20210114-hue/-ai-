import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, MessagePlugin } from 'tdesign-react';
import { ArrowLeftIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../../store/appState';
import { capabilityEnabled } from '../../../services/skills';
import { calendarDateKey as dateKey, isPastCalendarDate, type ScheduleItem } from '../../calendar/model';
import { useCalendarWorkspaceController } from '../../calendar/controller';
import { CalendarMonthView } from '../../calendar/view';
import type { MakersMapPlace } from '../../maps/model';
import type { InstalledSkill } from '../../skills/model';
import { MakersMap, chronologicalSchedulePlaces, scheduleRoutePreferences } from '../../maps/view';
import { ReadingLibraryPanel } from '../../papers/view';
import { useLanguage } from '../../../i18n';
import { useWorkspaceController } from '../controller/useWorkspaceController';

export default function WorkspacePanel() {
  const { language, t } = useLanguage();
  const locale = language === 'zh-TW' ? 'zh-TW' : language === 'en' ? 'en' : 'zh-CN';
  const dispatch = useAppDispatch();
  const {
    conversationId, schedules, mapPlaces, mapTitle, mapRouteMode, mapRouteStrategy, mapRoute,
    mapShowRoute, mapRevision, calendarPulse,
  } = useAppState();
  const { intelligence, searchPlaces, workspace } = useWorkspaceController(
    conversationId,
  );
  const consumeCalendarPulse = useCallback(
    () => dispatch({ type: 'CLEAR_CALENDAR_PULSE', payload: {} }),
    [dispatch],
  );
  const {
    calendarDays, currentMonth, dayViewOpen, schedulesByDate, selectedDate,
    selectedItems, setCurrentMonth, setDayViewOpen, setSelectedDate,
  } = useCalendarWorkspaceController(schedules, calendarPulse, consumeCalendarPulse);
  const [showRecommendation, setShowRecommendation] = useState(true);
  const [activeWorkspace, setActiveWorkspace] = useState<'map' | 'calendar' | 'reading'>('map');
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
  const [deleteConfirmId, setDeleteConfirmId] = useState('');
  const [skillPreferences, setSkillPreferences] = useState<Record<string, boolean>>({});
  const [skillCatalog, setSkillCatalog] = useState<InstalledSkill[]>([]);
  const placePickerRef = useRef<HTMLDivElement>(null);
  const autoDescriptionRef = useRef('');

  useEffect(() => {
    if (mapPlaces.length) {
      setShowRecommendation(true);
      setActiveWorkspace('map');
    }
  }, [mapRevision, mapPlaces.length]);

  useEffect(() => {
    if (calendarPulse) setActiveWorkspace('calendar');
  }, [calendarPulse]);

  useEffect(() => {
    let disposed = false;
    void intelligence().then((state) => {
      if (!disposed) {
        setSkillPreferences(state.skill_preferences || {});
        setSkillCatalog(state.skill_catalog || []);
      }
    }).catch(() => { /* The panel keeps defaults while the store reconnects. */ });
    const changed = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, boolean>>).detail;
      if (detail) setSkillPreferences(detail);
    };
    window.addEventListener('yuanbao:skills-changed', changed);
    return () => { disposed = true; window.removeEventListener('yuanbao:skills-changed', changed); };
  }, [intelligence]);

  const schedulePlaces = useMemo(
    () => chronologicalSchedulePlaces(selectedItems),
    [selectedItems],
  );
  const scheduleRoutePreference = useMemo(
    () => scheduleRoutePreferences(selectedItems),
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
  const selectedDateIsPast = isPastCalendarDate(selectedDate);
  const todayKey = dateKey(new Date());
  const mapsEnabled = capabilityEnabled(
    skillCatalog,
    skillPreferences,
    'places',
  );
  const calendarEnabled = capabilityEnabled(
    skillCatalog,
    skillPreferences,
    'calendar_action',
  );

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
      void searchPlaces(query)
        .then((places) => {
          if (!disposed) {
            setPlaceOptions(places);
            setPlaceOptionsOpen(places.length > 0);
          }
        })
        .catch(() => {
          if (!disposed) MessagePlugin.error(t('placeSearchFailed'));
        })
        .finally(() => { if (!disposed) setPlaceSearchBusy(false); });
    }, 350);
    return () => { disposed = true; window.clearTimeout(timer); };
  }, [formOpen, mapsEnabled, placeQuery, searchPlaces, selectedPlace, t]);

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
      const response = await workspace('direct_calendar_changes', {
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
    } catch {
      MessagePlugin.error(t('saveFailed'));
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
      const response = await workspace('direct_calendar_changes', {
        changes: [{ operation: 'delete', schedule_id: item.id }],
      });
      dispatch({ type: 'SET_SCHEDULES', payload: response.schedules });
      dispatch({ type: 'CLEAR_CALENDAR_PULSE', payload: {} });
      if (editingId === item.id) { setFormOpen(false); setEditingId(''); }
      setDeleteConfirmId('');
      setShowRecommendation(false);
      MessagePlugin.success(t('scheduleDeleted'));
    } catch {
      MessagePlugin.error(t('deleteFailed'));
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
      <nav className="workspace-section-tabs" aria-label={t('workspaceSections')}>
        {(['map', 'calendar', 'reading'] as const).map((section) => (
          <button
            type="button"
            key={section}
            className={activeWorkspace === section ? 'is-active' : ''}
            aria-current={activeWorkspace === section ? 'page' : undefined}
            onClick={() => setActiveWorkspace(section)}
          >{t(
            section === 'map' ? 'workspaceMapTab'
              : section === 'calendar' ? 'workspaceCalendarTab'
                : 'workspaceReadingTab',
          )}</button>
        ))}
      </nav>

      {activeWorkspace === 'map' && <div className="my-panel-card makers-map-card workspace-section-pane" data-onboarding="map">
        {mapsEnabled
          ? <MakersMap
            conversationId={conversationId}
            title={effectiveTitle}
            places={effectivePlaces}
            revision={mapRevision}
            showRoute={showingScheduleRoute || (showingRecommendation && mapShowRoute)}
            routeMode={showingRecommendation ? mapRouteMode : scheduleRoutePreference.mode}
            routeStrategy={showingRecommendation ? mapRouteStrategy : scheduleRoutePreference.strategy}
            routeSnapshot={showingRecommendation ? mapRoute : undefined}
          />
          : <div className="workspace-skill-disabled"><span>⌖</span><strong>{t('mapSkillDisabled')}</strong><small>{t('mapSkillDisabledDetail')}</small><button type="button" onClick={() => window.dispatchEvent(new CustomEvent('yuanbao:open-skills'))}>{t('enableInSkills')}</button></div>}
      </div>}

      {activeWorkspace === 'calendar' && <div className={`my-panel-card calendar-panel calendar-workspace-card workspace-section-pane ${dayViewOpen ? 'is-day-view' : ''}`} data-onboarding="calendar">
        {calendarPulse && (
          <div key={calendarPulse.token} className="calendar-write-notice">
            {t('schedulesWritten', { count: calendarPulse.count })}
          </div>
        )}
        <div className="calendar-workspace-viewport">
          <CalendarMonthView
            calendarDays={calendarDays}
            currentMonth={currentMonth}
            hidden={dayViewOpen}
            locale={locale}
            pulseDate={calendarPulse?.date}
            schedulesByDate={schedulesByDate}
            selectedDate={selectedDate}
            onMonthChange={setCurrentMonth}
            onSelectDate={(date) => { setSelectedDate(date); setShowRecommendation(false); setDayViewOpen(true); }}
          />

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
      </div>}

      {activeWorkspace === 'reading' && <ReadingLibraryPanel />}
    </aside>
  );
}

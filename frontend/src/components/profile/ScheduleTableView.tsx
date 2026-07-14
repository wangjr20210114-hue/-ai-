import { useState, useMemo, useEffect } from 'react';
import { Button, Dialog, Input, MessagePlugin, Tag } from 'tdesign-react';
import { ChevronLeftIcon, ChevronRightIcon, ArrowLeftIcon } from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ScheduleCategory, ScheduleItem } from '../../types';
import { SCHEDULE_CATEGORY_COLORS } from '../../types';
import type { DailyRouteLocation } from '../../services/api';
import { updateSchedule } from '../../services/api';

/** 课程表风格色彩调色板 */
const COURSE_COLORS = [
  { bg: 'rgba(78,124,255,0.10)', border: '#4e7cff', dot: '#4e7cff', time: '#4e7cff' },
  { bg: 'rgba(0,168,112,0.10)', border: '#00a870', dot: '#00a870', time: '#00a870' },
  { bg: 'rgba(227,115,24,0.10)', border: '#e37318', dot: '#e37318', time: '#e37318' },
  { bg: 'rgba(124,92,255,0.10)', border: '#7c5cff', dot: '#7c5cff', time: '#7c5cff' },
  { bg: 'rgba(237,123,132,0.10)', border: '#ed7b84', dot: '#ed7b84', time: '#ed7b84' },
  { bg: 'rgba(34,184,214,0.10)', border: '#22b8d6', dot: '#22b8d6', time: '#22b8d6' },
  { bg: 'rgba(245,166,35,0.10)', border: '#f5a623', dot: '#f5a623', time: '#f5a623' },
  { bg: 'rgba(80,200,120,0.10)', border: '#50c878', dot: '#50c878', time: '#50c878' },
  { bg: 'rgba(160,120,255,0.10)', border: '#a078ff', dot: '#a078ff', time: '#a078ff' },
  { bg: 'rgba(255,130,100,0.10)', border: '#ff8264', dot: '#ff8264', time: '#ff8264' },
];

const PLACE_TYPE_ICONS: Record<string, string> = {
  scenic: '🏛',
  restaurant: '🍜',
  hotel: '🏨',
  transport: '🚗',
  other: '📍',
};

interface Props {
  selectedDate: Date;
  onClose: () => void;
  onDateChange?: (date: Date) => void;
  routeLocations?: DailyRouteLocation[];
  selectedAlts: Record<string, number>;
  onAltChange?: (scheduleId: string, altIdx: number) => void;
}

/** 自适应时间线课程表：基于内容自动调整卡片高度。 */
export default function ScheduleTableView({ selectedDate, onClose, onDateChange, routeLocations, selectedAlts, onAltChange }: Props) {
  const { schedules, sessionId } = useAppState();
  const dispatch = useAppDispatch();
  const [expandedAlt, setExpandedAlt] = useState<string | null>(null);
  const [editing, setEditing] = useState<ScheduleItem | null>(null);
  const [saving, setSaving] = useState(false);

  const [currentDate, setCurrentDate] = useState(selectedDate);
  useEffect(() => { setCurrentDate(selectedDate); }, [selectedDate]);

  const changeDay = (delta: number) => {
    const d = new Date(currentDate);
    d.setDate(d.getDate() + delta);
    setCurrentDate(d);
    onDateChange?.(d);
  };

  const formatDateFull = (d: Date) => {
    const weekdays = ['日', '一', '二', '三', '四', '五', '六'];
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
    let prefix = '';
    if (diff === 0) prefix = '今天 · ';
    else if (diff === 1) prefix = '明天 · ';
    else if (diff === -1) prefix = '昨天 · ';
    return `${prefix}${d.getMonth() + 1}月${d.getDate()}日 周${weekdays[d.getDay()]}`;
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  };

  const currentDaySchedules = useMemo(() => {
    const dayStart = new Date(currentDate);
    dayStart.setHours(0, 0, 0, 0);
    const startTs = dayStart.getTime() / 1000;
    const dayEnd = startTs + 86400;
    return schedules
      .filter((s) => {
        if (s.start_time <= 0) return false;
        if (s.duration_days > 0) {
          const sEnd = s.start_time + s.duration_days * 86400;
          return s.start_time < dayEnd && sEnd > startTs;
        }
        return s.start_time >= startTs && s.start_time < dayEnd;
      })
      .sort((a, b) => a.start_time - b.start_time);
  }, [schedules, currentDate]);

  const md = currentDaySchedules.filter((s) => s.duration_days > 0);
  const timed = currentDaySchedules.filter((s) => s.duration_days === 0);

  const findRouteLocation = (scheduleId: string) =>
    routeLocations?.find((l) => l.id === scheduleId);

  // 从路线数据获取真实地名和备选方案
  const getResolved = (event: ScheduleItem) => {
    const rl = findRouteLocation(event.id);
    if (!rl) return { name: event.location, alts: [] };
    return { name: rl.name || event.location, alts: rl.alternatives || [] };
  };

  return (
    <div className="schedule-timeline-wrap">
      {/* 顶部栏 */}
      <div className="schedule-timeline-topbar">
        <Button shape="circle" variant="text" size="small" icon={<ArrowLeftIcon />} onClick={onClose} title="返回日历" />
        <span className="schedule-timeline-date">{formatDateFull(currentDate)}</span>
        <div style={{ display: 'flex', gap: 4 }}>
          <Button variant="text" size="small" icon={<ChevronLeftIcon />} onClick={() => changeDay(-1)} />
          <Button variant="text" size="small" icon={<ChevronRightIcon />} onClick={() => changeDay(1)} />
        </div>
      </div>

      {/* 多天日程 */}
      {md.length > 0 && (
        <div className="schedule-timeline-multiday">
          {md.map((item) => {
            const cat = item.category as ScheduleCategory;
            const color = SCHEDULE_CATEGORY_COLORS[cat] || '#909399';
            return (
              <div key={item.id} className="schedule-timeline-multiday-item" style={{ borderLeftColor: color }}>
                <span className="multiday-title">{item.title}</span>
                <Tag size="small" variant="light">{item.duration_days}天</Tag>
                {item.location && <span className="multiday-loc">📍 {item.location}</span>}
              </div>
            );
          })}
        </div>
      )}

      {/* 时间线 */}
      <div className="schedule-timeline-list">
        {timed.map((event, ei) => {
          const colorIdx = ei % COURSE_COLORS.length;
          const { border, bg, dot, time: timeColor } = COURSE_COLORS[colorIdx];
          const desc = event.description || event.extra?.description || '';
          const cost = event.extra?.cost_estimate || 0;
          const placeType = event.extra?.place_type || 'other';
          const { name: resolvedName, alts } = getResolved(event);
          const hasAlts = alts.length > 0;
          const isAltExpanded = expandedAlt === event.id;
          const selIdx = selectedAlts[event.id];
          const isAltSelected = selIdx != null && selIdx >= 0 && selIdx < alts.length;
          const displayLocation = isAltSelected && alts[selIdx]
            ? alts[selIdx].title
            : resolvedName;
          const endTs = event.start_time + (event.duration_minutes || 30) * 60;
          const prevEnd = ei > 0 ? timed[ei - 1].start_time + (timed[ei - 1].duration_minutes || 30) * 60 : 0;
          // 计算时间间隔
          const gapMin = ei > 0 ? Math.round((event.start_time - prevEnd) / 60) : 0;

          return (
            <div key={event.id} className="schedule-timeline-row">
              {/* 时间标签 */}
              <div className="schedule-timeline-time" style={{ color: timeColor }}>
                <span className="time-start">{formatTime(event.start_time)}</span>
                <span className="time-arrow">→</span>
                <span className="time-end">{formatTime(endTs)}</span>
              </div>

              {/* 事件卡片 */}
              <div className="schedule-timeline-card" style={{ borderLeftColor: border, background: bg }}>
                <div className="timeline-card-dot" style={{ background: dot }} />
                <div className="timeline-card-body">
                  <div className="timeline-card-header">
                    <span className="timeline-card-title">{event.title}</span>
                    {cost > 0 && <span className="timeline-card-cost">¥{cost}</span>}
                    <Button size="small" variant="text" onClick={() => setEditing({ ...event })}>编辑</Button>
                  </div>
                  {displayLocation && (
                    <div className="timeline-card-loc">{PLACE_TYPE_ICONS[placeType]} {displayLocation}</div>
                  )}
                  {desc && <div className="timeline-card-desc">{desc}</div>}
                  {hasAlts && (
                    <>
                      <div className="timeline-card-alts-toggle" onClick={() => setExpandedAlt(isAltExpanded ? null : event.id)}>
                        {isAltExpanded ? '收起方案 ▲' : `${alts.length}个备选方案 ▼`}
                      </div>
                      {isAltExpanded && (
                        <div className="timeline-card-alt-list">
                          {/* 默认（API 解析的地名） */}
                          {resolvedName && (
                            <div
                              className={`timeline-alt-item ${!isAltSelected ? 'selected' : ''}`}
                              onClick={() => { onAltChange?.(event.id, -1); setExpandedAlt(null); }}
                            >
                              <span className="alt-radio">{!isAltSelected ? '◉' : '○'}</span>
                              <div className="alt-body">
                                <div className="alt-name">⭐ {resolvedName} (推荐)</div>
                              </div>
                            </div>
                          )}
                          {alts.map((alt, ai) => (
                            <div
                              key={ai}
                              className={`timeline-alt-item ${selIdx === ai ? 'selected' : ''}`}
                              onClick={() => { onAltChange?.(event.id, ai); setExpandedAlt(null); }}
                            >
                              <span className="alt-radio">{selIdx === ai ? '◉' : '○'}</span>
                              <div className="alt-body">
                                <div className="alt-name">{alt.title}</div>
                                {alt.address && <div className="alt-addr">{alt.address}</div>}
                                {alt.tel && <div className="alt-tel">📞 {alt.tel}</div>}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>

              {/* 时间间隔指示 */}
              {ei < timed.length - 1 && gapMin > 0 && (
                <div className="schedule-timeline-gap">
                  <div className="gap-line" />
                  <span className="gap-text">{gapMin >= 60 ? `${Math.round(gapMin / 60)}h${gapMin % 60 > 0 ? gapMin % 60 + 'm' : ''}` : `${gapMin}m`}</span>
                </div>
              )}
            </div>
          );
        })}

        {timed.length === 0 && md.length === 0 && (
          <div className="schedule-timeline-empty">这天没有定时日程</div>
        )}
      </div>
      <Dialog
        visible={!!editing}
        header="编辑日程"
        confirmBtn={{ content: '保存', loading: saving }}
        cancelBtn="取消"
        onCancel={() => setEditing(null)}
        onClose={() => setEditing(null)}
        onConfirm={async () => {
          if (!editing) return;
          setSaving(true);
          try {
            await updateSchedule(sessionId, editing.id, editing);
            dispatch({ type: 'UPDATE_SCHEDULE', payload: editing });
            setEditing(null);
            MessagePlugin.success('日程已更新，路线将自动重算');
          } catch (error) {
            MessagePlugin.error(error instanceof Error ? error.message : '保存失败');
          } finally {
            setSaving(false);
          }
        }}
      >
        {editing && (
          <div style={{ display: 'grid', gap: 12 }}>
            <label>
              <div style={{ marginBottom: 5 }}>标题</div>
              <Input value={editing.title} onChange={(value) => setEditing({ ...editing, title: String(value) })} />
            </label>
            <label>
              <div style={{ marginBottom: 5 }}>地点</div>
              <Input value={editing.location} onChange={(value) => setEditing({ ...editing, location: String(value) })} />
            </label>
            <label>
              <div style={{ marginBottom: 5 }}>开始时间</div>
              <input
                type="datetime-local"
                value={new Date(editing.start_time * 1000 - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)}
                onChange={(event) => setEditing({ ...editing, start_time: new Date(event.target.value).getTime() / 1000 })}
                style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--app-border)', borderRadius: 6 }}
              />
            </label>
            <label>
              <div style={{ marginBottom: 5 }}>时长（分钟）</div>
              <input
                type="number"
                min="0"
                value={editing.duration_minutes}
                onChange={(event) => setEditing({ ...editing, duration_minutes: Number(event.target.value) })}
                style={{ width: '100%', padding: '8px 10px', border: '1px solid var(--app-border)', borderRadius: 6 }}
              />
            </label>
          </div>
        )}
      </Dialog>
    </div>
  );
}

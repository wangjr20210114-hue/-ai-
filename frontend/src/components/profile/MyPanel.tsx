import { useEffect, useState, useMemo } from 'react';
import { Button, Tag, MessagePlugin, Dialog, Checkbox } from 'tdesign-react';
import {
  UserIcon,
  DeleteIcon,
  RefreshIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from 'tdesign-icons-react';
import { useAppDispatch, useAppState } from '../../store/appState';
import { listSchedules, deleteSchedule, toggleScheduleDone } from '../../services/api';
import MarkdownRenderer from '../common/MarkdownRenderer';
import ScheduleTableView from './ScheduleTableView';
import DailyRouteMap from '../travel/DailyRouteMap';
import type { DailyRouteData } from '../../services/api';
import {
  SCHEDULE_CATEGORY_LABELS,
  SCHEDULE_CATEGORY_COLORS,
  type ScheduleCategory,
  type ScheduleItem,
} from '../../types';

const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];

function dateKey(date: Date): string {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
}

/** 右侧「我的」面板：日历视图 + 当日日程列表。 */
export default function MyPanel() {
  const {
    sessionId,
    schedules,
    scheduleViewDate,
    calendarFocusDate,
    calendarPulse,
  } = useAppState();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [currentMonth, setCurrentMonth] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [selectedDate, setSelectedDate] = useState(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d;
  });
  const [selectedAlts, setSelectedAlts] = useState<Record<string, number>>({});
  const [routeData, setRouteData] = useState<DailyRouteData | null>(null);
  const [pulsingDate, setPulsingDate] = useState<string | null>(null);
  const [writeNoticeCount, setWriteNoticeCount] = useState<number | null>(null);

  useEffect(() => {
    if (!calendarFocusDate) return;
    const target = new Date(`${calendarFocusDate}T00:00:00`);
    if (Number.isNaN(target.getTime())) return;
    setCurrentMonth(new Date(target.getFullYear(), target.getMonth(), 1));
    setSelectedDate(target);
    dispatch({ type: 'SHOW_SCHEDULE_VIEW', payload: null });
  }, [calendarFocusDate, calendarPulse?.token, dispatch]);

  useEffect(() => {
    if (!calendarPulse) return;
    setPulsingDate(calendarPulse.date);
    setWriteNoticeCount(calendarPulse.count);
    const pulseTimer = window.setTimeout(() => setPulsingDate(null), 1300);
    const noticeTimer = window.setTimeout(() => setWriteNoticeCount(null), 2200);
    return () => {
      window.clearTimeout(pulseTimer);
      window.clearTimeout(noticeTimer);
    };
  }, [calendarPulse]);

  // 当前生效日期：课程表模式用 scheduleViewDate，否则用日历选中日期
  const effectiveDate = scheduleViewDate || selectedDate;

  // 当切换查看日期时重置方案选择
  const viewTs = effectiveDate?.getTime();
  useEffect(() => {
    setSelectedAlts({});
    setRouteData(null);
  }, [viewTs]);

  const refresh = async (merge = false) => {
    setLoading(true);
    try {
      const items = await listSchedules(sessionId);
      dispatch({ type: merge ? 'MERGE_SCHEDULES' : 'SET_SCHEDULES', payload: items });
    } catch {
      // 静默
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const handleDelete = async () => {
    if (!deleteId) return;
    try {
      await deleteSchedule(sessionId, deleteId);
      dispatch({ type: 'DELETE_SCHEDULE', payload: deleteId });
      MessagePlugin.success('日程已删除');
    } catch {
      MessagePlugin.error('删除失败');
    } finally {
      setDeleteId(null);
    }
  };

  const handleToggleDone = async (id: string, done: boolean) => {
    try {
      await toggleScheduleDone(sessionId, id, !done);
      dispatch({
        type: 'UPDATE_SCHEDULE',
        payload: { ...(schedules.find((s) => s.id === id) as ScheduleItem), done: !done },
      });
    } catch {
      MessagePlugin.error('操作失败');
    }
  };

  // 生成日历格子（6行7列）
  const calendarDays = useMemo(() => {
    const year = currentMonth.getFullYear();
    const month = currentMonth.getMonth();
    const firstDay = new Date(year, month, 1);
    const lastDay = new Date(year, month + 1, 0);
    const startOffset = firstDay.getDay(); // 前面空格数
    const daysInMonth = lastDay.getDate();

    const days: { date: Date | null; day: number }[] = [];
    // 前置空格
    for (let i = 0; i < startOffset; i++) {
      days.push({ date: null, day: 0 });
    }
    // 当月日期
    for (let d = 1; d <= daysInMonth; d++) {
      days.push({ date: new Date(year, month, d), day: d });
    }
    // 补齐到42格
    while (days.length < 42) {
      days.push({ date: null, day: 0 });
    }
    return days;
  }, [currentMonth]);

  // 获取某天的日程数
  const getDayScheduleCount = (date: Date): number => {
    const dayStart = date.getTime() / 1000;
    const dayEnd = dayStart + 86400;
    return schedules.filter((s) => {
      if (s.start_time <= 0) return false;
      if (s.duration_days > 0) {
        const sEnd = s.start_time + s.duration_days * 86400;
        return s.start_time < dayEnd && sEnd > dayStart;
      }
      return s.start_time >= dayStart && s.start_time < dayEnd;
    }).length;
  };

  // 忙闲程度 → 颜色
  const getBusyLevel = (date: Date): { color: string; level: number } => {
    const count = getDayScheduleCount(date);
    if (count === 0) return { color: 'transparent', level: 0 };
    if (count <= 1) return { color: 'rgba(78, 124, 255, 0.15)', level: 1 };
    if (count <= 3) return { color: 'rgba(78, 124, 255, 0.35)', level: 2 };
    if (count <= 5) return { color: 'rgba(78, 124, 255, 0.6)', level: 3 };
    return { color: 'rgba(227, 115, 24, 0.6)', level: 4 };
  };

  const busyLabel = (level: number) => {
    return ['', '闲', '正常', '较忙', '满'][level] || '';
  };

  // 获取当前查看日期的日程（用于路线规划）
  const routeDaySchedules = useMemo(() => {
    const dayStart = effectiveDate.getTime() / 1000;
    const dayEnd = dayStart + 86400;
    return schedules
      .filter((s) => {
        if (s.start_time <= 0) return false;
        if (s.duration_days > 0) {
          const sEnd = s.start_time + s.duration_days * 86400;
          return s.start_time < dayEnd && sEnd > dayStart;
        }
        return s.start_time >= dayStart && s.start_time < dayEnd;
      })
      .sort((a, b) => a.start_time - b.start_time);
  }, [schedules, effectiveDate]);

  // 未定时日程
  const unscheduledItems = schedules.filter((s) => s.start_time <= 0);

  const isToday = (d: Date) => {
    const today = new Date();
    return d.toDateString() === today.toDateString();
  };

  const isSelected = (d: Date) => {
    return d.toDateString() === selectedDate.toDateString();
  };

  const monthLabel = `${currentMonth.getFullYear()}年${currentMonth.getMonth() + 1}月`;

  return (
    <aside className="my-panel">
      {/* 用户信息 */}
      <div className="my-panel-card">
        <div className="my-panel-user">
          <div className="my-panel-avatar">
            <UserIcon size="22px" />
          </div>
          <div>
            <div className="my-panel-username">我的</div>
            <div className="my-panel-subtext">
              {schedules.length > 0 ? `共 ${schedules.length} 项日程` : `Session: ${sessionId.slice(-8)}`}
            </div>
          </div>
          <Button
            variant="text"
            size="small"
            icon={<RefreshIcon />}
            onClick={() => { void refresh(false); }}
            loading={loading}
            style={{ marginLeft: 'auto' }}
          />
        </div>
      </div>

      {/* 日历 / 课程表视图 */}
      {scheduleViewDate ? (
        <div className="my-panel-card schedule-view-card">
          <ScheduleTableView
            selectedDate={scheduleViewDate}
            onClose={() => dispatch({ type: 'SHOW_SCHEDULE_VIEW', payload: null })}
            onDateChange={(date) => dispatch({ type: 'SHOW_SCHEDULE_VIEW', payload: date })}
            routeLocations={routeData?.locations}
            selectedAlts={selectedAlts}
            onAltChange={(scheduleId, altIdx) =>
              setSelectedAlts((prev) => ({ ...prev, [scheduleId]: altIdx }))
            }
          />
        </div>
      ) : (
      <div className="my-panel-card calendar-panel">
        {writeNoticeCount !== null && (
          <div className="calendar-write-notice">
            ✓ 已写入 {writeNoticeCount} 项安排
          </div>
        )}
        {/* 月份导航 */}
        <div className="calendar-header">
          <Button
            variant="text"
            size="small"
            icon={<ChevronLeftIcon />}
            onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1))}
          />
          <span className="calendar-month-label">{monthLabel}</span>
          <Button
            variant="text"
            size="small"
            icon={<ChevronRightIcon />}
            onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1))}
          />
        </div>

        {/* 星期表头 */}
        <div className="calendar-weekdays">
          {WEEKDAYS.map((w) => (
            <div key={w} className="calendar-weekday">{w}</div>
          ))}
        </div>

        {/* 日期格子 */}
        <div className="calendar-grid">
          {calendarDays.map((cell, i) => {
            if (!cell.date) return <div key={i} className="calendar-day empty" />;
            const cellDate = cell.date;
            const busy = getBusyLevel(cellDate);
            const isT = isToday(cellDate);
            const isSel = isSelected(cellDate);
            return (
              <button
                key={i}
                className={`calendar-day ${isT ? 'today' : ''} ${isSel ? 'selected' : ''} ${pulsingDate === dateKey(cellDate) ? 'calendar-day-pulse' : ''}`}
                style={{ background: busy.color }}
                onClick={() => {
                  setSelectedDate(cellDate);
                  dispatch({ type: 'SHOW_SCHEDULE_VIEW', payload: cellDate });
                }}
                title={busy.level > 0 ? `${busyLabel(busy.level)} (${getDayScheduleCount(cellDate)}项) · 点击查看详情` : '点击查看当天日程'}
              >
                <span className="calendar-day-num">{cell.day}</span>
                {busy.level > 0 && <span className="calendar-day-dot" />}
              </button>
            );
          })}
        </div>

        {/* 忙闲图例 */}
        <div className="calendar-legend">
          <span className="legend-item"><span className="legend-dot" style={{ background: 'rgba(78,124,255,0.15)' }} />闲</span>
          <span className="legend-item"><span className="legend-dot" style={{ background: 'rgba(78,124,255,0.35)' }} />正常</span>
          <span className="legend-item"><span className="legend-dot" style={{ background: 'rgba(78,124,255,0.6)' }} />较忙</span>
          <span className="legend-item"><span className="legend-dot" style={{ background: 'rgba(227,115,24,0.6)' }} />满</span>
        </div>
        </div>
      )}

      {/* 当日路线地图 - 日历下方常驻显示 */}
      <div className="my-panel-card">
        <DailyRouteMap
          date={effectiveDate}
          schedules={routeDaySchedules}
          selectedAlts={selectedAlts}
          onRouteLoaded={setRouteData}
        />
      </div>

      {/* 未定时日程 */}
      {!scheduleViewDate && unscheduledItems.length > 0 && (
        <div className="my-panel-card">
          <div className="section-title" style={{ marginBottom: 8 }}>
            📌 未定时日程
            <Tag size="small" variant="light" style={{ marginLeft: 'auto' }}>{unscheduledItems.length} 项</Tag>
          </div>
          <div className="schedule-day-list">
            {unscheduledItems.map((item) => {
              const cat = item.category as ScheduleCategory;
              const color = SCHEDULE_CATEGORY_COLORS[cat] || '#909399';
              const isExpanded = expandedId === item.id;
              const hasDetail = !!(item.markdown_content || item.description);
              return (
                <div key={item.id} className={`schedule-day-item ${item.done ? 'done' : ''}`}>
                  <div
                    className="schedule-day-main"
                    onClick={() => hasDetail && setExpandedId(isExpanded ? null : item.id)}
                    style={{ cursor: hasDetail ? 'pointer' : 'default' }}
                  >
                    <div className="schedule-day-cat-dot" style={{ background: color }} />
                    <div className="schedule-day-content">
                      <div className="schedule-day-title">{item.title}</div>
                      <div className="schedule-day-meta">
                        <Tag size="small" variant="light" style={{ fontSize: 10 }}>{SCHEDULE_CATEGORY_LABELS[cat]}</Tag>
                        {item.location && <span className="schedule-day-loc">📍 {item.location}</span>}
                        {item.duration_days > 0 && <span className="schedule-day-dur">{item.duration_days}天</span>}
                        {hasDetail && <span className="schedule-day-expand">{isExpanded ? '收起' : '详情'}</span>}
                      </div>
                    </div>
                  </div>
                  <div className="schedule-day-actions">
                    <Checkbox
                      checked={item.done}
                      onChange={() => handleToggleDone(item.id, item.done)}
                    />
                    <Button
                      variant="text"
                      size="small"
                      icon={<DeleteIcon />}
                      onClick={() => setDeleteId(item.id)}
                      style={{ opacity: 0.5 }}
                    />
                  </div>
                  {isExpanded && hasDetail && (
                    <div className="schedule-day-detail">
                      {item.description && <div className="schedule-day-desc">{item.description}</div>}
                      {item.markdown_content && <MarkdownRenderer content={item.markdown_content} />}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      <Dialog
        visible={!!deleteId}
        header="删除日程"
        confirmBtn={{ content: '删除', theme: 'danger' }}
        cancelBtn="取消"
        onConfirm={handleDelete}
        onCancel={() => setDeleteId(null)}
      >
        确定要删除这个日程吗？此操作不可撤销。
      </Dialog>

    </aside>
  );
}

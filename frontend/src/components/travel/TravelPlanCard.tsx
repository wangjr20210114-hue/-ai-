import { useState } from 'react';
import { Button, Tag, MessagePlugin, Collapse } from 'tdesign-react';
import { CheckIcon, DeleteIcon } from 'tdesign-icons-react';
import { workspaceOperation } from '../../services/api';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { TravelPlan, ScheduleItem } from '../../types';
import MarkdownRenderer from '../common/MarkdownRenderer';
import RouteMap from './RouteMap';
import { useLanguage } from '../../i18n';

const { Panel: CollapsePanel } = Collapse;

interface Props {
  plan: TravelPlan;
  startTs?: number;
  parsedSchedules?: Partial<ScheduleItem>[];
  isSaved?: boolean;
  onSaved?: (plan: TravelPlan) => void;
  onDeleted?: (planId: string) => void;
}

/** 旅游计划卡片：展示 Markdown 行程 + 百科信息 + 写入日程按钮。 */
export default function TravelPlanCard({ plan, startTs = 0, parsedSchedules, isSaved = false, onSaved, onDeleted }: Props) {
  const { t } = useLanguage();
  const { conversationId } = useAppState();
  const dispatch = useAppDispatch();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(isSaved);
  const [scheduleId, setScheduleId] = useState<string>('');

  const handleSave = async () => {
    setSaving(true);
    try {
      if (saved) {
        const savedPlan = await workspaceOperation(conversationId, 'save_travel_plan', { plan });
        const updated = savedPlan.travel_plan || plan;
        dispatch({ type: 'UPDATE_PLAN', payload: updated });
        if (scheduleId) {
          const response = await workspaceOperation(conversationId, 'direct_calendar_changes', {
            changes: [{
              operation: 'update', schedule_id: scheduleId,
              event: {
                title: plan.title, category: 'travel',
                description: `${plan.departure} → ${plan.destination}，${plan.travel_style}`,
              },
            }],
          });
          dispatch({ type: 'SET_SCHEDULES', payload: response.schedules });
        }
        MessagePlugin.success(t('scheduleUpdated'));
      } else {
        const savedPlan = await workspaceOperation(conversationId, 'save_travel_plan', { plan });
        const persisted = savedPlan.travel_plan || plan;
        plan.id = persisted.id;
        dispatch({ type: 'ADD_PLAN', payload: persisted });

        const changes: Array<Record<string, unknown>> = [];
        if (startTs > 0) {
          changes.push({
            operation: 'create',
            event: {
              title: plan.title, category: 'travel', start_time: startTs,
              duration_minutes: Math.max(60, plan.days * 24 * 60), location: plan.destination,
              description: `${plan.departure} → ${plan.destination}，${plan.travel_style}`,
            },
          });
        }
        for (const schedule of parsedSchedules || []) {
          if (Number(schedule.start_time || 0) > 0 && schedule.title) {
            changes.push({ operation: 'create', event: schedule });
          }
        }
        const scheduleResponse = changes.length
          ? await workspaceOperation(conversationId, 'direct_calendar_changes', { changes })
          : null;
        if (scheduleResponse) {
          dispatch({ type: 'SET_SCHEDULES', payload: scheduleResponse.schedules });
          const created = scheduleResponse.changed?.find((item) => !item.deleted);
          if (created) setScheduleId(created.id);
        }

        setSaved(true);
        MessagePlugin.success(changes.length ? t('travelSavedWithSchedule') : t('travelSavedWithoutDate'));
      }
      onSaved?.(plan);
    } catch {
      MessagePlugin.error(t('operationRetry'));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!saved) return;
    try {
      await workspaceOperation(conversationId, 'delete_travel_plan', { plan_id: plan.id });
      if (scheduleId) {
        const response = await workspaceOperation(conversationId, 'direct_calendar_changes', {
          changes: [{ operation: 'delete', schedule_id: scheduleId }],
        });
        dispatch({ type: 'SET_SCHEDULES', payload: response.schedules });
      }
      dispatch({ type: 'DELETE_PLAN', payload: plan.id });
      if (scheduleId) {
        dispatch({ type: 'DELETE_SCHEDULE', payload: scheduleId });
      }
      MessagePlugin.success(t('scheduleDeleted'));
      onDeleted?.(plan.id);
    } catch {
      MessagePlugin.error(t('deleteFailed'));
    }
  };

  const baike = plan.baike_info || {};

  return (
    <div className="travel-plan-card">
      <div className="travel-plan-header">
        <div className="travel-plan-title">{plan.title}</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Tag size="small" theme="primary" variant="light">{plan.destination}</Tag>
          <Tag size="small" theme="success" variant="light">{t('days', { count: plan.days })}</Tag>
          <Tag size="small" variant="light">{plan.travel_style}</Tag>
        </div>
      </div>

      <div className="travel-plan-meta">
        <span>{t('departure', { value: plan.departure })}</span>
        <span>{t('destination', { value: plan.destination })}</span>
        <span>{t('dayTotal', { count: t('days', { count: plan.days }) })}</span>
        <span>{t('travelStyle', { value: plan.travel_style })}</span>
        {plan.scenery_preference && <span>{t('preference', { value: plan.scenery_preference })}</span>}
        {plan.budget && <span>{t('budget', { value: plan.budget })}</span>}
      </div>

      <div className="travel-plan-markdown">
        <MarkdownRenderer content={plan.markdown_content} />
      </div>

      {/* 路线地图 */}
      <Collapse style={{ marginTop: 12 }}>
        <CollapsePanel value="route" header={t('routeAndCost')}>
          <RouteMap departure={plan.departure} destination={plan.destination} />
        </CollapsePanel>
      </Collapse>

      {baike.summary && (
        <Collapse style={{ marginTop: 12 }}>
          <CollapsePanel value="baike" header={t('encyclopedia', { name: plan.destination })}>
            <div style={{ fontSize: 13, lineHeight: 1.8, color: 'var(--app-text-2)' }}>
              <p>{baike.summary}</p>
              {baike.highlights && (
                <ul style={{ paddingLeft: 18, marginTop: 6 }}>
                  {baike.highlights.map((h: string, i: number) => (
                    <li key={i}>{h}</li>
                  ))}
                </ul>
              )}
              {baike.best_season && (
                <p style={{ marginTop: 6 }}>
                  <Tag size="small" theme="warning" variant="light">{t('bestSeason')}</Tag>{' '}
                  {baike.best_season}
                </p>
              )}
            </div>
          </CollapsePanel>
        </Collapse>
      )}
      {baike.error && (
        <div style={{ marginTop: 12, padding: '8px 12px', background: 'var(--app-panel-2)', borderRadius: 8, border: '1px solid var(--app-border)' }}>
          <Tag size="small" theme="warning" variant="light">{baike.error}</Tag>
        </div>
      )}

      <div className="travel-plan-actions">
        <Button
          theme="primary"
          icon={<CheckIcon />}
          loading={saving}
          onClick={handleSave}
        >
          {saved ? t('updateSchedule') : t('writeToCalendar')}
        </Button>
        {saved && (
          <Button variant="outline" icon={<DeleteIcon />} onClick={handleDelete}>
            {t('delete')}
          </Button>
        )}
      </div>
    </div>
  );
}

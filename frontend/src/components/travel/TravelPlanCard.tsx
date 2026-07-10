import { useState } from 'react';
import { Button, Tag, MessagePlugin, Collapse } from 'tdesign-react';
import { CheckIcon, DeleteIcon } from 'tdesign-icons-react';
import {
  deleteSchedule,
  deleteTravelPlan,
  listSchedules,
  saveSchedule,
  saveTravelPlan,
  updateSchedule,
  updateTravelPlan,
} from '../../services/api';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { TravelPlan, ScheduleItem } from '../../types';
import MarkdownRenderer from '../common/MarkdownRenderer';
import RouteMap from './RouteMap';

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
  const { sessionId } = useAppState();
  const dispatch = useAppDispatch();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(isSaved);
  const [scheduleId, setScheduleId] = useState<string>('');

  const handleSave = async () => {
    setSaving(true);
    try {
      if (saved) {
        await updateTravelPlan(sessionId, plan.id, plan);
        dispatch({ type: 'UPDATE_PLAN', payload: plan });
        if (scheduleId) {
          const schedule: Partial<ScheduleItem> = {
            title: plan.title,
            category: 'travel',
            duration_days: plan.days,
            location: plan.destination,
            description: `${plan.departure} → ${plan.destination}，${plan.travel_style}`,
            markdown_content: plan.markdown_content,
          };
          await updateSchedule(sessionId, scheduleId, schedule);
        }
        MessagePlugin.success('日程已更新');
      } else {
        const result = await saveTravelPlan(sessionId, plan);
        plan.id = result.plan_id;
        dispatch({ type: 'ADD_PLAN', payload: plan });

        // 同时写入通用日程（总览）
        const schedResult = await saveSchedule(sessionId, {
          title: plan.title,
          category: 'travel',
          start_time: startTs,
          duration_days: plan.days,
          location: plan.destination,
          description: `${plan.departure} → ${plan.destination}，${plan.travel_style}`,
          markdown_content: plan.markdown_content,
        });
        setScheduleId(schedResult.schedule_id);

        // 写入解析后的每日详细日程项
        if (parsedSchedules && parsedSchedules.length > 0) {
          for (const sched of parsedSchedules) {
            await saveSchedule(sessionId, sched);
          }
        }

        // 刷新右侧面板日程列表
        const schedules = await listSchedules(sessionId);
        dispatch({ type: 'SET_SCHEDULES', payload: schedules });

        setSaved(true);
        if (schedResult.conflicts && schedResult.conflicts.length > 0) {
          MessagePlugin.warning(`已写入日程，但检测到 ${schedResult.conflicts.length} 个时间冲突，请在日程表中查看`);
        } else {
          MessagePlugin.success('已写入我的日程');
        }
      }
      onSaved?.(plan);
    } catch {
      MessagePlugin.error('操作失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!saved) return;
    try {
      await deleteTravelPlan(sessionId, plan.id);
      if (scheduleId) {
        await deleteSchedule(sessionId, scheduleId);
      }
      dispatch({ type: 'DELETE_PLAN', payload: plan.id });
      if (scheduleId) {
        dispatch({ type: 'DELETE_SCHEDULE', payload: scheduleId });
      }
      MessagePlugin.success('日程已删除');
      onDeleted?.(plan.id);
    } catch {
      MessagePlugin.error('删除失败');
    }
  };

  const baike = plan.baike_info || {};

  return (
    <div className="travel-plan-card">
      <div className="travel-plan-header">
        <div className="travel-plan-title">{plan.title}</div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <Tag size="small" theme="primary" variant="light">{plan.destination}</Tag>
          <Tag size="small" theme="success" variant="light">{plan.days}天</Tag>
          <Tag size="small" variant="light">{plan.travel_style}</Tag>
        </div>
      </div>

      <div className="travel-plan-meta">
        <span>出发地：{plan.departure}</span>
        <span>目的地：{plan.destination}</span>
        <span>天数：{plan.days}天</span>
        <span>风格：{plan.travel_style}</span>
        {plan.scenery_preference && <span>偏好：{plan.scenery_preference}</span>}
        {plan.budget && <span>预算：{plan.budget}</span>}
      </div>

      <div className="travel-plan-markdown">
        <MarkdownRenderer content={plan.markdown_content} />
      </div>

      {/* 路线地图 */}
      <Collapse style={{ marginTop: 12 }}>
        <CollapsePanel value="route" header="🗺 路线地图与费用估算">
          <RouteMap departure={plan.departure} destination={plan.destination} />
        </CollapsePanel>
      </Collapse>

      {baike.summary && (
        <Collapse style={{ marginTop: 12 }}>
          <CollapsePanel value="baike" header={`${plan.destination}百科`}>
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
                  <Tag size="small" theme="warning" variant="light">最佳季节</Tag>{' '}
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
          {saved ? '更新日程' : '写入我的日程'}
        </Button>
        {saved && (
          <Button variant="outline" icon={<DeleteIcon />} onClick={handleDelete}>
            删除
          </Button>
        )}
      </div>
    </div>
  );
}

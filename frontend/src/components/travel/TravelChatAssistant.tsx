import { useState, useEffect, useCallback } from 'react';
import { Button, Tag, Loading, Input, MessagePlugin, Checkbox } from 'tdesign-react';
import { CheckIcon } from 'tdesign-icons-react';
import { searchCities, generateTravelPlan, analyzeTravelIntent } from '../../services/api';
import { useAppDispatch, useAppState } from '../../store/appState';
import type { ScheduleItem, TravelCollected, TravelPlan } from '../../types';

interface Props {
  initialDestination?: string;
  userMessage?: string;
  onComplete: (plan: TravelPlan, startTs?: number, parsedSchedules?: Partial<ScheduleItem>[]) => void;
  onCancel: () => void;
}

interface QAQuestion {
  field: string;
  question: string;
  options: string[];
  multi: boolean;
  allow_custom: boolean;
  is_date?: boolean;
}

/** Agent 驱动的旅游计划助手：AI 根据上下文推断还需要哪些信息。 */
export default function TravelChatAssistant({ initialDestination, userMessage, onComplete, onCancel }: Props) {
  const { sessionId } = useAppState();
  const dispatch = useAppDispatch();
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [collected, setCollected] = useState<TravelCollected>({});
  const [currentQuestion, setCurrentQuestion] = useState<QAQuestion | null>(null);
  const [history, setHistory] = useState<string[]>([]);

  // 多选状态
  const [multiSelected, setMultiSelected] = useState<string[]>([]);
  // 自定义输入
  const [customInput, setCustomInput] = useState('');
  const [showCustom, setShowCustom] = useState(false);

  // 城市搜索
  const [cityKeyword, setCityKeyword] = useState('');
  const [cityResults, setCityResults] = useState<{ name: string; province: string }[]>([]);
  const [searching, setSearching] = useState(false);

  // 初始化：调用 AI 分析用户消息
  useEffect(() => {
    const initCollected: TravelCollected = {};
    if (initialDestination) {
      initCollected.destination = initialDestination;
    }
    analyze(initCollected);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 进入新问题时重置多选和自定义状态
  useEffect(() => {
    setMultiSelected([]);
    setShowCustom(false);
    setCustomInput('');
    setCityKeyword('');
    setCityResults([]);
  }, [currentQuestion?.field]);

  const analyze = async (currentCollected: TravelCollected) => {
    setLoading(true);
    try {
      const res = await analyzeTravelIntent({
        session_id: sessionId,
        message: userMessage || `我想去${initialDestination || ''}旅游`,
        collected: currentCollected,
        history,
      });
      if (res.error) {
        MessagePlugin.warning(res.error);
        setLoading(false);
        return;
      }
      const newCollected = res.collected || currentCollected;
      setCollected(newCollected);

      // 推送旅游上下文到 Debug 栏
      dispatch({
        type: 'SET_TRAVEL_CONTEXT',
        payload: {
          collected: newCollected,
          missing: res.missing || [],
          reasoning: res.reasoning || '',
          context: res.context || {},
        },
      });

      if (res.ready) {
        // 所有信息收集完毕，生成计划
        setCurrentQuestion(null);
        generatePlan(newCollected);
      } else if (res.next_question) {
        setCurrentQuestion(res.next_question);
      } else {
        // 异常情况，直接生成
        generatePlan(newCollected);
      }
    } catch {
      MessagePlugin.error('分析失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const generatePlan = async (info: TravelCollected) => {
    setGenerating(true);
    try {
      // 日期优先，没有日期才用天数
      const startDate = info.start_date || '';
      const endDate = info.end_date || '';
      let days = 0;
      if (!startDate && !endDate) {
        days = typeof info.days === 'number' ? info.days : parseInt(String(info.days || '3').replace(/[^0-9]/g, '') || '3', 10);
      }
      const res = await generateTravelPlan({
        session_id: sessionId,
        departure: info.departure || '未指定',
        destination: info.destination || '未指定',
        days,
        start_date: startDate,
        end_date: endDate,
        travel_style: info.travel_style || '深度游',
        scenery_preference: info.scenery_preference || '人文景观',
        budget: '',
        extra_notes: '',
      });
      if (res.error) {
        MessagePlugin.warning(res.error);
        setGenerating(false);
        return;
      }
      if (res.plan) {
        onComplete(res.plan, res.start_ts, res.parsed_schedules);
        setGenerating(false);
      }
    } catch {
      MessagePlugin.error('生成计划失败，请稍后重试');
      setGenerating(false);
    }
  };

  // 单选：选择后直接进入下一步
  const handleSingleSelect = (value: string) => {
    const newCollected = { ...collected, [currentQuestion!.field]: value };
    setHistory((prev) => [...prev, `Q: ${currentQuestion!.question} A: ${value}`]);
    analyze(newCollected);
  };

  // 多选切换
  const handleMultiToggle = (value: string) => {
    setMultiSelected((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    );
  };

  // 多选确认
  const handleMultiConfirm = () => {
    const selected = [...multiSelected];
    if (showCustom && customInput.trim()) {
      selected.push(customInput.trim());
    }
    if (selected.length === 0) {
      MessagePlugin.warning('至少选择一项');
      return;
    }
    const value = selected.join('、');
    const newCollected = { ...collected, [currentQuestion!.field]: value };
    setHistory((prev) => [...prev, `Q: ${currentQuestion!.question} A: ${value}`]);
    analyze(newCollected);
  };

  // 自定义确认
  const handleCustomConfirm = () => {
    const val = customInput.trim();
    if (!val) return;
    if (currentQuestion!.multi) {
      setMultiSelected((prev) => [...prev, val]);
      setCustomInput('');
    } else {
      handleSingleSelect(val);
    }
  };

  const doSearchCities = useCallback(async (kw: string) => {
    setCityKeyword(kw);
    if (kw.trim()) {
      setSearching(true);
      try {
        const cities = await searchCities(kw);
        setCityResults(cities);
      } catch {
        setCityResults([]);
      } finally {
        setSearching(false);
      }
    } else {
      setCityResults([]);
    }
  }, []);

  const fieldLabels: Record<string, string> = {
    destination: '目的地',
    departure: '出发地',
    start_date: '出发日期',
    end_date: '结束日期',
    travel_style: '风格',
    scenery_preference: '偏好',
  };

  if (loading || generating) {
    return (
      <div className="travel-chat-assistant">
        <div className="travel-chat-loading">
          <Loading size="small" />
          <div style={{ marginTop: 12, fontSize: 14, color: 'var(--app-text-2)' }}>
            {generating ? '正在为你生成专属行程...' : 'AI 正在分析你的需求...'}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="travel-chat-assistant">
      <div className="travel-chat-header">
        <span>旅游计划助手</span>
        <Tag size="small" theme="primary" variant="light">
          AI 智能问答
        </Tag>
      </div>

      {/* 已收集信息回顾 */}
      {Object.keys(collected).length > 0 && (
        <div className="travel-chat-answers">
          {Object.entries(collected).map(([key, val]) => (
            <Tag key={key} size="small" theme="success" variant="light" style={{ marginRight: 6, marginBottom: 4 }}>
              {fieldLabels[key] || key}：{String(val)}
            </Tag>
          ))}
        </div>
      )}

      {/* 当前问题 */}
      {currentQuestion && (
        <>
          <div className="travel-chat-question">
            <div className="travel-chat-q-text">{currentQuestion.question}</div>
          </div>

          {/* 选项 */}
          {currentQuestion.options.length > 0 && (
            <div className="travel-chat-options">
              {currentQuestion.options.map((opt) => {
                const isSelected = currentQuestion.multi ? multiSelected.includes(opt) : false;
                return (
                  <button
                    key={opt}
                    className={`travel-chat-option ${isSelected ? 'selected' : ''}`}
                    onClick={() => currentQuestion.multi ? handleMultiToggle(opt) : handleSingleSelect(opt)}
                  >
                    {currentQuestion.multi && (
                      <Checkbox checked={isSelected} onChange={() => {}} style={{ marginRight: 4 }} />
                    )}
                    {opt}
                  </button>
                );
              })}
            </div>
          )}

          {/* 日期输入 */}
          {currentQuestion.is_date && (
            <div className="travel-chat-custom">
              <input
                type="date"
                className="form-input-simple"
                style={{ flex: 1 }}
                value={customInput}
                min={currentQuestion.field === 'start_date'
                  ? new Date().toISOString().split('T')[0]
                  : collected.start_date || undefined}
                max={currentQuestion.field === 'end_date'
                  ? undefined
                  : undefined}
                onChange={(e) => setCustomInput(e.target.value)}
              />
              <Button theme="primary" size="small" onClick={() => {
                if (customInput) handleSingleSelect(customInput);
              }} icon={<CheckIcon />}>
                确认
              </Button>
            </div>
          )}

          {/* 城市搜索（出发地/目的地步骤） */}
          {currentQuestion.allow_custom && (currentQuestion.field === 'departure' || currentQuestion.field === 'destination') && showCustom && (
            <div className="travel-chat-search">
              <Input
                value={cityKeyword}
                onChange={(v) => doSearchCities(v as string)}
                placeholder="输入城市名搜索..."
                suffixIcon={searching ? <Loading size="small" /> : undefined}
                style={{ width: '100%' }}
              />
              {cityResults.length > 0 && (
                <div className="travel-chat-city-list">
                  {cityResults.map((c) => (
                    <button
                      key={c.name}
                      className="travel-chat-city-item"
                      onClick={() => handleSingleSelect(c.name)}
                    >
                      {c.name}
                      <span className="travel-chat-city-province">{c.province}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 自定义输入（非日期、非城市字段） */}
          {currentQuestion.allow_custom && !currentQuestion.is_date && !showCustom && (
            <button className="travel-chat-other-btn" onClick={() => setShowCustom(true)}>
              + 其他
            </button>
          )}

          {currentQuestion.allow_custom && showCustom && currentQuestion.field !== 'departure' && currentQuestion.field !== 'destination' && !currentQuestion.is_date && (
            <div className="travel-chat-custom">
              <Input
                value={customInput}
                onChange={(v) => setCustomInput(v as string)}
                placeholder="输入你的选择..."
                style={{ width: '100%' }}
                onKeydown={(_, ctx) => {
                  const e = ctx.e as React.KeyboardEvent;
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleCustomConfirm();
                  }
                }}
              />
              {currentQuestion.multi ? (
                <Button theme="primary" size="small" onClick={handleCustomConfirm}>添加</Button>
              ) : (
                <Button theme="primary" size="small" onClick={handleCustomConfirm} icon={<CheckIcon />}>确认</Button>
              )}
            </div>
          )}

          {/* 多选确认 */}
          {currentQuestion.multi && (
            <div className="travel-chat-multi-confirm">
              {multiSelected.length > 0 && (
                <span style={{ fontSize: 12, color: 'var(--app-text-3)', marginRight: 8 }}>
                  已选 {multiSelected.length} 项
                </span>
              )}
              <Button theme="primary" size="small" onClick={handleMultiConfirm} disabled={multiSelected.length === 0}>
                确认选择
              </Button>
            </div>
          )}
        </>
      )}

      <div className="travel-chat-footer">
        <Button variant="text" size="small" onClick={onCancel}>
          取消
        </Button>
      </div>
    </div>
  );
}

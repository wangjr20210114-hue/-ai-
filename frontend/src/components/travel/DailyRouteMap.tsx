import { useState, useEffect, useRef } from 'react';
import { Tag, Loading, MessagePlugin } from 'tdesign-react';
import { planDailyRoute, type DailyRouteData, type DailyRouteLocation } from '../../services/api';
import type { ScheduleItem } from '../../types';

interface Props {
  date: Date;
  schedules: ScheduleItem[];
  selectedAlts: Record<string, number>; // scheduleId → altIndex
  onRouteLoaded?: (data: DailyRouteData | null) => void;
}

/** 当日路线地图：连接当天所有日程地点的路线。 */
export default function DailyRouteMap({ date, schedules, selectedAlts, onRouteLoaded }: Props) {
  const [loading, setLoading] = useState(true);
  const [routeData, setRouteData] = useState<DailyRouteData | null>(null);
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<TencentMapInstance | null>(null);
  const isInitialMount = useRef(true);

  // 提取当天日程的搜索关键词
  const dayLocations = useRef<{ id: string; keyword: string }[]>([]);

  useEffect(() => {
    dayLocations.current = schedules
      .filter((s) => {
        const kw = s.extra?.search_query || s.extra?.search_keyword || s.location;
        return kw && s.start_time > 0;
      })
      .sort((a, b) => a.start_time - b.start_time)
      .map((s) => ({
        id: s.id,
        keyword: s.extra?.search_query || s.extra?.search_keyword || s.location,
      }));
  }, [schedules]);

  // 初次加载路线
  useEffect(() => {
    const fetchRoute = async () => {
      if (dayLocations.current.length < 2) {
        setLoading(false);
        setRouteData(null);
        onRouteLoaded?.(null);
        return;
      }

      setLoading(true);
      try {
        const city = schedules.reduce((found: string, s) => {
          if (found) return found;
          return s.extra?.city || '';
        }, '');
        // 只传关键词，后端统一搜索 + 城市距离过滤
        const result = await planDailyRoute({
          city,
          locations: dayLocations.current.map((l) => ({ id: l.id, keyword: l.keyword })),
        });
        if (result.error) {
          MessagePlugin.warning(result.error);
          setRouteData(null);
          onRouteLoaded?.(null);
        } else {
          setRouteData(result);
          onRouteLoaded?.(result);
        }
      } catch {
        MessagePlugin.error('路线规划失败');
        setRouteData(null);
        onRouteLoaded?.(null);
      } finally {
        setLoading(false);
      }
    };
    fetchRoute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, schedules]);

  // 当用户选择不同方案时，重新规划路线
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    if (!routeData || !routeData.locations) return;

    const hasChange = Object.keys(selectedAlts).length > 0;
    if (!hasChange) return;

    // 构建更新后的坐标
    const updatedLocations = routeData.locations.map((loc) => {
      const altIdx = selectedAlts[loc.id] ?? 0;
      const alt = loc.alternatives[altIdx];
      if (alt) {
        return {
          id: loc.id,
          keyword: loc.keyword,
          name: alt.title,
          lat: alt.lat,
          lng: alt.lng,
          address: alt.address,
          alternatives: loc.alternatives,
        };
      }
      return {
        id: loc.id,
        keyword: loc.keyword,
        name: loc.name,
        lat: loc.lat,
        lng: loc.lng,
        address: loc.address,
        alternatives: loc.alternatives,
      };
    });

    const refetch = async () => {
      setLoading(true);
      try {
        const city = routeData.city;
        const result = await planDailyRoute({ city, locations: updatedLocations });
        if (!result.error) {
          setRouteData(result);
        }
      } catch {
        // 静默
      } finally {
        setLoading(false);
      }
    };
    refetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAlts]);

  // 渲染腾讯地图
  useEffect(() => {
    if (!routeData || !mapRef.current) return;

    const key = import.meta.env.VITE_TENCENT_MAP_KEY?.trim(); if (!key) return;
    const scriptId = 'qq-map-sdk-daily';

    const initMap = () => {
      const TMap = window.TMap;
      if (!TMap || !mapRef.current) return;

      // 清理旧地图
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy?.();
        mapInstanceRef.current = null;
      }

      const locations = routeData.locations.filter(
        (l: DailyRouteLocation) => l.lat !== 0 && l.lng !== 0 && !isNaN(l.lat) && !isNaN(l.lng)
      );
      if (locations.length < 2) return;

      // 计算中心点
      const centerLat = locations.reduce((s, l) => s + l.lat, 0) / locations.length;
      const centerLng = locations.reduce((s, l) => s + l.lng, 0) / locations.length;

      const map = new TMap.Map(mapRef.current, {
        center: new TMap.LatLng(centerLat, centerLng),
        zoom: 12,
      });
      mapInstanceRef.current = map;

      // 标记点
      const geometries = locations.map((loc, i) => ({
        id: `point-${i}`,
        position: new TMap.LatLng(loc.lat, loc.lng),
      }));

      new TMap.MultiMarker({
        map,
        geometries,
      });

      // 编号标签（使用 MultiLabel 而不是 Label）
      const labelGeos = locations.map((loc, i) => ({
        id: `label-${i}`,
        styleId: 'label',
        position: new TMap.LatLng(loc.lat, loc.lng),
        content: `${i + 1}`,
      }));
      new TMap.MultiLabel({
        map,
        styles: { label: new TMap.LabelStyle({ color: '#fff', size: 12, offset: { x: -8, y: -24 }, background: { color: '#2b5aed', padding: '2px 6px', borderRadius: '10px' } }) },
        geometries: labelGeos,
      });

      // 路线 polyline，过滤无效坐标
      if (routeData.polyline && routeData.polyline.length > 0) {
        const pts: unknown[] = [];
        for (let i = 0; i < routeData.polyline.length; i += 2) {
          const lat = routeData.polyline[i];
          const lng = routeData.polyline[i + 1];
          if (lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180) {
            pts.push(new TMap.LatLng(lat, lng));
          }
        }
        new TMap.MultiPolyline({
          map,
          styles: {
            style_blue: new TMap.PolylineStyle({
              color: '#2b5aed',
              width: 4,
            }),
          },
          geometries: [{
            id: 'route',
            styleId: 'style_blue',
            paths: pts,
          }],
        });
      }
    };

    if (!window.TMap) {
      if (!document.getElementById(scriptId)) {
        const script = document.createElement('script');
        script.id = scriptId;
        script.src = `https://map.qq.com/api/gljs?v=1.exp&key=${encodeURIComponent(key)}`;
        script.onload = initMap;
        document.head.appendChild(script);
      }
    } else {
      initMap();
    }

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy?.();
        mapInstanceRef.current = null;
      }
    };
  }, [routeData]);

  if (loading) {
    return (
      <div style={{ padding: 20, textAlign: 'center' }}>
        <Loading size="small" />
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--app-text-3)' }}>
          正在规划当日路线...
        </div>
      </div>
    );
  }

  if (!routeData || routeData.error) {
    return (
      <div className="daily-route-empty">
        {routeData?.error || '当天地点不足，无法规划路线'}
      </div>
    );
  }

  const validLocs = routeData.locations.filter(
    (l) => l.lat !== 0 && l.lng !== 0 && !isNaN(l.lat) && !isNaN(l.lng)
  );
  if (validLocs.length < 2) {
    return (
      <div className="daily-route-empty">
        有效地点不足，无法规划路线
      </div>
    );
  }

  return (
    <div className="daily-route-container">
      <div className="daily-route-header">
        <span className="daily-route-title">🗺 当日路线</span>
        <Tag size="small" theme="primary" variant="light">
          {routeData.total_distance_km}km · {Math.round(routeData.total_duration / 60)}分钟
        </Tag>
      </div>

      {/* 地图 */}
      <div ref={mapRef} className="daily-route-canvas" />

      {/* 地点列表 */}
      <div className="daily-route-stops">
        {routeData.locations.map((loc, i) => (
          <div key={i} className="daily-route-stop">
            <span className="daily-route-stop-num">{i + 1}</span>
            <div className="daily-route-stop-info">
              <div className="daily-route-stop-name">{loc.name}</div>
              {loc.address && <div className="daily-route-stop-addr">{loc.address}</div>}
            </div>
            {i < routeData.locations.length - 1 && routeData.segments[i] && (
              <div className="daily-route-stop-seg">
                ↓ {(routeData.segments[i].distance / 1000).toFixed(1)}km
              </div>
            )}
          </div>
        ))}
      </div>

      {/* 天气 */}
      {routeData.weather && !routeData.weather.error && (
        <div className="route-weather">
          <span className="route-weather-icon">🌤</span>
          <span className="route-weather-temp">{routeData.weather.temperature}°C</span>
          <span className="route-weather-desc">{routeData.weather.weather}</span>
          {routeData.weather.tips && (
            <span className="route-weather-tips">{routeData.weather.tips}</span>
          )}
        </div>
      )}

      {/* 费用 */}
      {routeData.cost_estimate && (
        <div className="route-cost">
          <div className="route-cost-title">💰 交通费用</div>
          <div className="route-cost-items">
            <div className="route-cost-item">
              <span>自驾</span>
              <span className="route-cost-value">¥{routeData.cost_estimate.self_driving}</span>
            </div>
            <div className="route-cost-item">
              <span>打车</span>
              <span className="route-cost-value">¥{routeData.cost_estimate.taxi}</span>
            </div>
            {routeData.cost_estimate.toll > 0 && (
              <div className="route-cost-item">
                <span>过路费</span>
                <span className="route-cost-value">¥{routeData.cost_estimate.toll}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

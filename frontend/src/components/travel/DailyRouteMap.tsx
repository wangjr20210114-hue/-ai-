import { useState, useEffect, useRef } from 'react';
import { Button, Tag, Loading, MessagePlugin } from 'tdesign-react';
import {
  getTencentMapBrowserKey,
  planDailyRoute,
  type DailyRouteData,
  type DailyRouteLocation,
} from '../../services/api';
import {
  LOCATION_EVENT,
  readSessionLocation,
  requestCurrentLocation,
  type UserLocation,
} from '../../services/location';
import type { ScheduleItem } from '../../types';

interface Props {
  date: Date;
  schedules: ScheduleItem[];
  selectedAlts: Record<string, number>; // scheduleId → altIndex
  onRouteLoaded?: (data: DailyRouteData | null) => void;
}

type MapRenderStatus = 'loading' | 'ready' | 'missing' | 'error';

const MAP_SCRIPT_ID = 'qq-map-sdk-daily';
let mapSdkPromise: Promise<TencentMapNamespace> | null = null;

function loadTencentMapSdk(key: string): Promise<TencentMapNamespace> {
  if (window.TMap) return Promise.resolve(window.TMap);
  if (mapSdkPromise) return mapSdkPromise;
  mapSdkPromise = new Promise<TencentMapNamespace>((resolve, reject) => {
    let script = document.getElementById(MAP_SCRIPT_ID) as HTMLScriptElement | null;
    const finish = () => window.TMap
      ? resolve(window.TMap)
      : reject(new Error('SDK 已加载但未通过鉴权'));
    const fail = () => reject(new Error('SDK 请求失败'));
    if (!script) {
      script = document.createElement('script');
      script.id = MAP_SCRIPT_ID;
      script.src = `https://map.qq.com/api/gljs?v=1.exp&key=${encodeURIComponent(key)}`;
      script.async = true;
      document.head.appendChild(script);
    }
    script.addEventListener('load', finish, { once: true });
    script.addEventListener('error', fail, { once: true });
    window.setTimeout(() => {
      if (!window.TMap) reject(new Error('SDK 加载超时'));
    }, 10000);
  }).catch((error) => {
    mapSdkPromise = null;
    throw error;
  });
  return mapSdkPromise!;
}

function resetTencentMapSdk() {
  mapSdkPromise = null;
  if (!window.TMap) document.getElementById(MAP_SCRIPT_ID)?.remove();
}

function RouteSchematic({ data }: { data: DailyRouteData }) {
  const routePoints: Array<{ lat: number; lng: number }> = [];
  for (let index = 0; index + 1 < (data.polyline?.length || 0); index += 2) {
    const lat = Number(data.polyline[index]);
    const lng = Number(data.polyline[index + 1]);
    if (Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
      routePoints.push({ lat, lng });
    }
  }
  const points = routePoints.length >= 2
    ? routePoints
    : data.locations.map((item) => ({ lat: item.lat, lng: item.lng }));
  const all = [...points, ...data.locations.map((item) => ({ lat: item.lat, lng: item.lng }))];
  const minLat = Math.min(...all.map((item) => item.lat));
  const maxLat = Math.max(...all.map((item) => item.lat));
  const minLng = Math.min(...all.map((item) => item.lng));
  const maxLng = Math.max(...all.map((item) => item.lng));
  const latRange = Math.max(maxLat - minLat, 0.001);
  const lngRange = Math.max(maxLng - minLng, 0.001);
  const project = (item: { lat: number; lng: number }) => ({
    x: 22 + ((item.lng - minLng) / lngRange) * 256,
    y: 158 - ((item.lat - minLat) / latRange) * 136,
  });
  const path = points.map((item) => {
    const point = project(item);
    return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
  }).join(' ');

  return (
    <div className="daily-route-schematic" aria-label="路线地图概览">
      <svg viewBox="0 0 300 180" role="img">
        <defs>
          <linearGradient id="route-bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#eef4ff" />
            <stop offset="1" stopColor="#f1edff" />
          </linearGradient>
        </defs>
        <rect width="300" height="180" rx="12" fill="url(#route-bg)" />
        <polyline points={path} fill="none" stroke="#4e7cff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        {data.locations.map((location, index) => {
          const point = project(location);
          return (
            <g key={location.id || index} transform={`translate(${point.x} ${point.y})`}>
              <circle r="10" fill="#2b5aed" stroke="#fff" strokeWidth="2" />
              <text y="4" textAnchor="middle" fill="#fff" fontSize="10" fontWeight="700">{index + 1}</text>
            </g>
          );
        })}
      </svg>
      <span>路线由腾讯地图服务端规划</span>
    </div>
  );
}

/** 当日路线地图：连接当天所有日程地点的路线。 */
export default function DailyRouteMap({
  date,
  schedules,
  selectedAlts,
  onRouteLoaded,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [routeData, setRouteData] = useState<DailyRouteData | null>(null);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(() => readSessionLocation());
  const [locating, setLocating] = useState(false);
  const [mapAnimating, setMapAnimating] = useState(false);
  const [browserMapKey, setBrowserMapKey] = useState('');
  const [mapConfigLoading, setMapConfigLoading] = useState(true);
  const [mapStatus, setMapStatus] = useState<MapRenderStatus>('loading');
  const [mapError, setMapError] = useState('');
  const [mapAttempt, setMapAttempt] = useState(0);
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<TencentMapInstance | null>(null);
  const isInitialMount = useRef(true);
  const routeRequestRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    getTencentMapBrowserKey().then((key) => {
      if (cancelled) return;
      setBrowserMapKey(key);
      setMapConfigLoading(false);
      if (!key) setMapStatus('missing');
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!routeData?.locations?.length) return;
    setMapAnimating(true);
    const timer = window.setTimeout(() => setMapAnimating(false), 1100);
    return () => window.clearTimeout(timer);
  }, [routeData]);

  // 提取当天日程的搜索关键词
  const dayLocations = useRef<{
    id: string; keyword: string; name?: string; address?: string; lat?: number; lng?: number;
  }[]>([]);

  useEffect(() => {
    const sync = (event: Event) => {
      const detail = (event as CustomEvent<UserLocation>).detail;
      setUserLocation(detail || readSessionLocation());
    };
    window.addEventListener(LOCATION_EVENT, sync);
    return () => window.removeEventListener(LOCATION_EVENT, sync);
  }, []);

  useEffect(() => {
    const scheduleLocations = schedules
      .filter((s) => {
        const kw = s.extra?.search_query || s.extra?.search_keyword || s.location;
        return kw && s.start_time > 0;
      })
      .sort((a, b) => a.start_time - b.start_time)
      .map((s) => ({
        id: s.id,
        keyword: s.extra?.search_query || s.extra?.search_keyword || s.location,
        name: s.title,
        address: s.location,
        lat: Number(s.extra?.lat || 0),
        lng: Number(s.extra?.lng || 0),
      }));
    // The calendar is the sole map data source. Recommendations from another
    // date/conversation must never leak into the selected day's big-screen map.
    dayLocations.current = scheduleLocations;
  }, [schedules]);

  // 初次加载路线
  useEffect(() => {
    const requestId = ++routeRequestRef.current;
    let cancelled = false;
    const isCurrent = () => !cancelled && routeRequestRef.current === requestId;
    const requestedLocations = dayLocations.current.map((location) => ({ ...location }));

    const fetchRoute = async () => {
      if (requestedLocations.length < 2) {
        if (!isCurrent()) return;
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
          locations: requestedLocations,
        });
        if (!isCurrent()) return;
        if (result.error) {
          MessagePlugin.warning(result.error);
          setRouteData(null);
          onRouteLoaded?.(null);
        } else {
          setRouteData(result);
          onRouteLoaded?.(result);
        }
      } catch {
        if (!isCurrent()) return;
        MessagePlugin.error('路线规划失败');
        setRouteData(null);
        onRouteLoaded?.(null);
      } finally {
        if (isCurrent()) setLoading(false);
      }
    };
    fetchRoute();
    return () => {
      cancelled = true;
    };
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

    const requestId = ++routeRequestRef.current;
    let cancelled = false;
    const isCurrent = () => !cancelled && routeRequestRef.current === requestId;
    const refetch = async () => {
      setLoading(true);
      try {
        const city = routeData.city;
        const result = await planDailyRoute({ city, locations: updatedLocations });
        if (isCurrent() && !result.error) {
          setRouteData(result);
          onRouteLoaded?.(result);
        }
      } catch {
        // 静默
      } finally {
        if (isCurrent()) setLoading(false);
      }
    };
    void refetch();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedAlts]);

  // 渲染腾讯地图
  useEffect(() => {
    if ((!routeData && !userLocation) || !mapRef.current) return;

    const key = browserMapKey;
    if (mapConfigLoading) return;
    if (!key) {
      setMapStatus('missing');
      return;
    }
    let disposed = false;
    let tileTimer = 0;
    setMapStatus('loading');
    setMapError('');

    const initMap = (TMap: TencentMapNamespace) => {
      if (disposed || !mapRef.current) return;

      try {
        // 清理旧地图
        if (mapInstanceRef.current) {
          mapInstanceRef.current.destroy?.();
          mapInstanceRef.current = null;
        }

      const locations = routeData
        ? routeData.locations.filter(
          (l: DailyRouteLocation) => l.lat !== 0 && l.lng !== 0 && !isNaN(l.lat) && !isNaN(l.lng)
        )
        : userLocation ? [{
          id: 'current-location', keyword: '当前位置', name: '当前位置', address: '',
          lat: userLocation.lat, lng: userLocation.lng, alternatives: [],
        }] : [];
        if (locations.length < 1) return;

      // 计算中心点
      const centerLat = locations.reduce((s, l) => s + l.lat, 0) / locations.length;
      const centerLng = locations.reduce((s, l) => s + l.lng, 0) / locations.length;

        const map = new TMap.Map(mapRef.current, {
          center: new TMap.LatLng(centerLat, centerLng),
          zoom: 12,
        });
        mapInstanceRef.current = map;

        const markReady = () => {
          if (disposed) return;
          window.clearTimeout(tileTimer);
          setMapStatus('ready');
          setMapError('');
        };
        if (map.on) {
          map.on('tilesloaded', markReady);
          tileTimer = window.setTimeout(() => {
            if (!disposed) {
              setMapStatus('error');
              setMapError('底图瓦片未返回');
            }
          }, 10000);
        } else {
          tileTimer = window.setTimeout(markReady, 500);
        }

        if (locations.length > 1 && TMap.LatLngBounds && map.fitBounds) {
        const Bounds = TMap.LatLngBounds;
        const bounds = new Bounds();
        locations.forEach((location) => bounds.extend(new TMap.LatLng(location.lat, location.lng)));
        window.setTimeout(() => map.fitBounds?.(bounds, { padding: 48 }), 160);
      }

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
        if (routeData?.polyline && routeData.polyline.length > 0) {
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
      } catch (error) {
        setMapStatus('error');
        setMapError(error instanceof Error ? error.message : '地图初始化失败');
      }
    };

    loadTencentMapSdk(key).then(initMap).catch((error) => {
      if (!disposed) {
        setMapStatus('error');
        setMapError(error instanceof Error ? error.message : '地图 SDK 加载失败');
      }
    });

    return () => {
      disposed = true;
      window.clearTimeout(tileTimer);
      if (mapInstanceRef.current) {
        mapInstanceRef.current.destroy?.();
        mapInstanceRef.current = null;
      }
    };
  }, [routeData, userLocation, browserMapKey, mapConfigLoading, mapAttempt]);

  const mapFailureText = mapStatus === 'missing'
    ? '腾讯地图浏览器底图尚未配置；路线与地点数据仍可使用。'
    : `腾讯地图底图加载失败${mapError ? `（${mapError}）` : ''}。可能是 Key 权限、生产域名白名单或调用额度限制；路线数据仍可使用。`;

  const mapWarning = (mapStatus === 'missing' || mapStatus === 'error') && (
    <div className="daily-route-map-warning" role="status">
      <span>{mapFailureText}</span>
      {mapStatus === 'error' && (
        <Button
          size="small"
          variant="text"
          onClick={() => {
            resetTencentMapSdk();
            setMapAttempt((value) => value + 1);
          }}
        >
          重试底图
        </Button>
      )}
    </div>
  );

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

  if ((!routeData || routeData.error) && userLocation) {
    return (
      <div className="daily-route-container">
        <div className="daily-route-header">
          <span className="daily-route-title">📍 当前位置</span>
          <Tag size="small" variant="light">当天暂无可连接路线</Tag>
        </div>
        <div className="daily-route-map-stage">
          <div ref={mapRef} className="daily-route-canvas" />
          {mapStatus === 'loading' && <div className="daily-route-map-overlay">正在加载腾讯地图…</div>}
        </div>
        {mapWarning}
        <div className="daily-route-empty">
          定位精度约 {Math.round(userLocation.accuracy)} 米；添加至少两个带地点的日程后会自动显示路线。
        </div>
      </div>
    );
  }

  if (!routeData || routeData.error) {
    return (
      <div className="daily-route-empty">
        <div>{routeData?.error || '当天地点不足，无法规划路线'}</div>
        <Button
          size="small"
          theme="primary"
          variant="outline"
          loading={locating}
          style={{ marginTop: 10 }}
          onClick={async () => {
            setLocating(true);
            try {
              setUserLocation(await requestCurrentLocation());
            } catch (error) {
              MessagePlugin.warning(error instanceof Error ? error.message : '无法获取位置');
            } finally {
              setLocating(false);
            }
          }}
        >
          提供位置或先补充日程
        </Button>
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
    <div className={`daily-route-container ${mapAnimating ? 'is-updating' : ''}`}>
      <div className="daily-route-header">
        <span className="daily-route-title">🗺 当日路线</span>
        <Tag size="small" theme="primary" variant="light">
          {routeData.total_distance_km}km · {Math.round(routeData.total_duration / 60)}分钟
        </Tag>
      </div>

      {/* 地图 */}
      <div className="daily-route-map-stage">
        <div
          ref={mapRef}
          className={`daily-route-canvas ${mapStatus === 'missing' || mapStatus === 'error' ? 'is-fallback' : ''}`}
        />
        {(mapStatus === 'missing' || mapStatus === 'error') && <RouteSchematic data={routeData} />}
        {mapStatus === 'loading' && <div className="daily-route-map-overlay">正在加载腾讯地图…</div>}
      </div>
      {mapWarning}

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

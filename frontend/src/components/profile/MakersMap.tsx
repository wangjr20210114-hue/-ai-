import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'tdesign-react';
import { planMakersRoute, proactiveOperation } from '../../services/api';
import { useAppDispatch } from '../../store/appState';
import type { MakersMapPlace, MakersRoutePlan } from '../../types';
import { LOCATION_OPTIONS, locationErrorMessage } from './makersMapLocation';
import { shouldPlanMakersRoute } from './makersMapRouting';

interface Props {
  conversationId: string;
  title: string;
  places: MakersMapPlace[];
  revision: number;
  /** Whether this map represents an ordered plan (for example a day's schedule). */
  showRoute?: boolean;
  optimize?: boolean;
}

type PermissionState = 'checking' | 'prompt' | 'granted' | 'denied' | 'unavailable';

let sdkPromise: Promise<TencentMapNamespace> | null = null;
const MAP_SDK_TIMEOUT_MS = 12_000;

function resetTencentMapSdk() {
  sdkPromise = null;
  document.getElementById('qq-map-sdk-production')?.remove();
}

function loadTencentMap(key: string): Promise<TencentMapNamespace> {
  if (window.TMap) return Promise.resolve(window.TMap);
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.id = 'qq-map-sdk-production';
    script.src = `https://map.qq.com/api/gljs?v=1.exp&libraries=service&key=${encodeURIComponent(key)}`;
    script.async = true;
    let settled = false;
    const timer = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      resetTencentMapSdk();
      reject(new Error('地图 SDK 加载超时'));
    }, MAP_SDK_TIMEOUT_MS);
    script.onload = () => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      if (window.TMap) resolve(window.TMap);
      else {
        resetTencentMapSdk();
        reject(new Error('地图 SDK 加载失败'));
      }
    };
    script.onerror = () => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      resetTencentMapSdk();
      reject(new Error('地图 SDK 加载失败'));
    };
    document.head.appendChild(script);
  });
  return sdkPromise;
}

function hoursMinutes(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} 分钟`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分钟`;
}

export default function MakersMap({ conversationId, title, places, revision, showRoute = false, optimize = false }: Props) {
  const dispatch = useAppDispatch();
  const containerRef = useRef<HTMLDivElement>(null);
  const [animating, setAnimating] = useState(false);
  const [mapUnavailable, setMapUnavailable] = useState(false);
  const [mapLoading, setMapLoading] = useState(false);
  const [route, setRoute] = useState<MakersRoutePlan | null>(null);
  const [routeError, setRouteError] = useState('');
  const [permission, setPermission] = useState<PermissionState>('checking');
  const [userLocation, setUserLocation] = useState<MakersMapPlace | null>(null);
  const [renderAttempt, setRenderAttempt] = useState(0);
  const [locationError, setLocationError] = useState('');
  const locationRequestRef = useRef(0);

  const displayPlaces = useMemo(
    () => places.length ? places : userLocation ? [userLocation] : [],
    [places, userLocation],
  );

  const readCurrentLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setPermission('unavailable');
      setLocationError('当前浏览器不支持定位。');
      return;
    }
    const requestId = ++locationRequestRef.current;
    setPermission('checking');
    setLocationError('');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (requestId !== locationRequestRef.current) return;
        const latitude = Number(position.coords.latitude.toFixed(2));
        const longitude = Number(position.coords.longitude.toFixed(2));
        setPermission('granted');
        setLocationError('');
        setMapUnavailable(false);
        setUserLocation({
          place_id: 'browser-current-location',
          provider: 'browser',
          name: '当前位置',
          address: '仅在当前浏览器会话中使用',
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
        const localDay = new Date().toLocaleDateString('en-CA');
        void proactiveOperation(conversationId, 'ingest_signal', {
          signal_type: 'browser_location_weather',
          dedup_key: `${localDay}:${latitude.toFixed(2)}:${longitude.toFixed(2)}`,
          payload: { latitude, longitude },
        }).then((next) => {
          dispatch({ type: 'HYDRATE_PROACTIVE', payload: next });
        }).catch(() => {
          // Weather enrichment is optional and must never block the map.
        });
        setRenderAttempt((value) => value + 1);
      },
      (error) => {
        if (requestId !== locationRequestRef.current) return;
        setPermission(error.code === 1 ? 'denied' : 'prompt');
        setLocationError(locationErrorMessage(error));
      },
      LOCATION_OPTIONS,
    );
  }, [conversationId, dispatch]);

  useEffect(() => {
    if (!navigator.permissions) {
      setPermission('prompt');
      return;
    }
    let disposed = false;
    void navigator.permissions.query({ name: 'geolocation' }).then((status) => {
      if (disposed) return;
      const update = () => {
        const next = status.state === 'granted' ? 'granted' : status.state === 'denied' ? 'denied' : 'prompt';
        setPermission(next);
        if (next === 'granted') readCurrentLocation();
      };
      update();
      status.onchange = update;
    }).catch(() => setPermission('prompt'));
    return () => { disposed = true; };
  }, [readCurrentLocation]);

  useEffect(() => {
    if (!shouldPlanMakersRoute(showRoute, places.length)) {
      setRoute(null);
      setRouteError('');
      return;
    }
    let disposed = false;
    setRoute(null);
    setRouteError('');
    void planMakersRoute(conversationId, places, optimize)
      .then((next) => { if (!disposed) setRoute(next); })
      .catch((error) => { if (!disposed) setRouteError(error instanceof Error ? error.message : '路线规划失败'); });
    return () => { disposed = true; };
  }, [conversationId, places, revision, showRoute, optimize]);

  useEffect(() => {
    if (!displayPlaces.length) return;
    setAnimating(true);
    const timer = window.setTimeout(() => setAnimating(false), 900);
    return () => window.clearTimeout(timer);
  }, [revision, displayPlaces.length, route]);

  useEffect(() => {
    const key = import.meta.env.VITE_TENCENT_MAP_KEY?.trim();
    const container = containerRef.current;
    if (!key || !container || !displayPlaces.length) {
      setMapLoading(false);
      setMapUnavailable(Boolean(displayPlaces.length && !key));
      return;
    }
    let cancelled = false;
    let map: TencentMapInstance | null = null;
    let fitBoundsTimer: number | null = null;
    let resizeTimer: number | null = null;
    let resizeObserver: ResizeObserver | null = null;
    setMapLoading(true);
    void loadTencentMap(key).then((TMap) => {
      if (cancelled || !containerRef.current) return;
      setMapLoading(false);
      setMapUnavailable(false);
      const renderedPlaces = route?.places?.length ? route.places : displayPlaces;
      const first = renderedPlaces[0];
      map = new TMap.Map(containerRef.current, {
        center: new TMap.LatLng(first.latitude, first.longitude),
        zoom: renderedPlaces.length === 1 ? 16 : 12,
      });
      const resizeMap = () => map?.resize?.();
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(resizeMap);
        resizeObserver.observe(containerRef.current);
      }
      resizeTimer = window.setTimeout(resizeMap, 180);
      new TMap.MultiMarker({
        map,
        geometries: renderedPlaces.map((place, index) => ({
          id: `makers-place-${place.place_id || index}`,
          position: new TMap.LatLng(place.latitude, place.longitude),
          properties: { title: `${index + 1}. ${place.name}` },
        })),
      });
      new TMap.MultiLabel({
        map,
        styles: {
          label: new TMap.LabelStyle({
            color: '#1d2129', size: 12, offset: { x: 0, y: -34 },
            backgroundColor: '#ffffff', borderColor: '#d8dce8', borderWidth: 1,
            borderRadius: 6, padding: '4px 7px',
          }),
        },
        geometries: renderedPlaces.map((place, index) => ({
          id: `makers-label-${place.place_id || index}`,
          styleId: 'label',
          position: new TMap.LatLng(place.latitude, place.longitude),
          content: place.name === '当前位置' ? place.name : `${index + 1}. ${place.name}`,
        })),
      });
      if (route?.path?.length) {
        new TMap.MultiPolyline({
          map,
          styles: { route: new TMap.PolylineStyle({ color: '#4e7cff', width: 5, borderWidth: 1, borderColor: '#ffffff' }) },
          geometries: [{
            id: 'makers-road-route',
            styleId: 'route',
            paths: route.path.map((point) => new TMap.LatLng(point.latitude, point.longitude)),
          }],
        });
      }
      if (renderedPlaces.length > 1 && TMap.LatLngBounds && map.fitBounds) {
        const bounds = new TMap.LatLngBounds();
        const fitPoints = route?.path?.length ? route.path : renderedPlaces;
        fitPoints.forEach((point) => bounds.extend(new TMap.LatLng(point.latitude, point.longitude)));
        fitBoundsTimer = window.setTimeout(() => map?.fitBounds?.(bounds, { padding: 56 }), 150);
      }
    }).catch(() => {
      if (cancelled) return;
      setMapLoading(false);
      setMapUnavailable(true);
    });
    return () => {
      cancelled = true;
      if (fitBoundsTimer !== null) window.clearTimeout(fitBoundsTimer);
      if (resizeTimer !== null) window.clearTimeout(resizeTimer);
      resizeObserver?.disconnect();
      map?.destroy?.();
    };
  }, [displayPlaces, places.length, route, routeError, revision, renderAttempt]);

  if (!displayPlaces.length) {
    return (
      <div className="makers-map-empty makers-location-state">
        {permission === 'checking' && <><div>正在取得当前位置…</div><Button size="small" variant="outline" disabled>定位中</Button></>}
        {permission === 'prompt' && <><div>{locationError || '今天还没有可连成路线的日程'}</div><Button size="small" theme="primary" onClick={readCurrentLocation}>显示我的位置</Button></>}
        {permission === 'denied' && <><div>{locationError || '位置权限已关闭。请在浏览器的网站设置中允许定位后重试。'}</div><Button size="small" variant="outline" onClick={readCurrentLocation}>重新检查位置</Button></>}
        {permission === 'unavailable' && <div>当前浏览器不支持定位；添加至少两个有效日程地点后仍可显示路线。</div>}
        {permission === 'granted' && <><div>位置权限已开启，正在读取位置…</div><Button size="small" variant="outline" onClick={readCurrentLocation}>重新定位</Button></>}
      </div>
    );
  }

  return (
    <div className={`makers-map ${animating ? 'is-updating' : ''}`}>
      <div className="makers-map-title">{places.length ? title : '当前位置'}</div>
      <div ref={containerRef} className="makers-map-canvas" aria-label={`${title}地图`} />
      {mapLoading && <div className="makers-map-loading" role="status">正在加载腾讯地图…</div>}
      {mapUnavailable && (
        <div className="makers-map-fallback" role="status">
          <strong>底图暂时未加载，已核实地点仍可查看</strong>
          <div className="makers-map-fallback-places">
            {(route?.places?.length ? route.places : displayPlaces).map((place, index) => <div key={`${place.place_id}-${index}`}>
              <b>{index + 1}. {place.name}</b>
              <span>{place.address || `${place.latitude.toFixed(5)}, ${place.longitude.toFixed(5)}`}</span>
            </div>)}
          </div>
          <Button size="small" variant="outline" onClick={() => {
            resetTencentMapSdk();
            setMapUnavailable(false);
            setRenderAttempt((value) => value + 1);
          }}>重试加载底图</Button>
        </div>
      )}
      {showRoute && routeError && <div className="makers-route-error">未能取得真实道路路线：{routeError}</div>}
      {shouldPlanMakersRoute(showRoute, places.length) && !route && !routeError && <div className="makers-route-loading">正在计算真实道路路线…</div>}
      {showRoute && route && (
        <div className="makers-route-summary">
          <span>{(route.distance_meters / 1000).toFixed(1)} 公里</span>
          <span>{hoursMinutes(route.duration_seconds)}</span>
          <span>自驾约 ¥{route.fare.self_driving.estimate.toFixed(0)}</span>
          <span>打车约 ¥{route.fare.taxi.low.toFixed(0)}–{route.fare.taxi.high.toFixed(0)}</span>
          <small>{route.fare.basis}</small>
          <small>{route.cache?.hit ? '已复用 6 小时内的 Makers 路线缓存' : '路线已保存到 Makers 缓存，6 小时内相同地点不重复计算'}</small>
        </div>
      )}
      <div className="makers-place-chips">
        {(route?.places?.length ? route.places : displayPlaces).map((place, index) => <span key={`${place.place_id}-${index}`}>{place.name === '当前位置' ? '📍' : index + 1} {place.name}</span>)}
      </div>
    </div>
  );
}

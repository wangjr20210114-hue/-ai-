import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'tdesign-react';
import { planMakersRoute } from '../../services/api';
import type { MakersMapPlace, MakersRoutePlan } from '../../types';

interface Props {
  conversationId: string;
  title: string;
  places: MakersMapPlace[];
  revision: number;
  optimize?: boolean;
}

type PermissionState = 'checking' | 'prompt' | 'granted' | 'denied' | 'unavailable';

let sdkPromise: Promise<TencentMapNamespace> | null = null;

function loadTencentMap(key: string): Promise<TencentMapNamespace> {
  if (window.TMap) return Promise.resolve(window.TMap);
  if (sdkPromise) return sdkPromise;
  sdkPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.id = 'qq-map-sdk-production';
    script.src = `https://map.qq.com/api/gljs?v=1.exp&libraries=service&key=${encodeURIComponent(key)}`;
    script.async = true;
    script.onload = () => window.TMap ? resolve(window.TMap) : reject(new Error('地图 SDK 加载失败'));
    script.onerror = () => reject(new Error('地图 SDK 加载失败'));
    document.head.appendChild(script);
  });
  return sdkPromise;
}

function hoursMinutes(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} 分钟`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分钟`;
}

export default function MakersMap({ conversationId, title, places, revision, optimize = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [animating, setAnimating] = useState(false);
  const [mapUnavailable, setMapUnavailable] = useState(false);
  const [route, setRoute] = useState<MakersRoutePlan | null>(null);
  const [routeError, setRouteError] = useState('');
  const [permission, setPermission] = useState<PermissionState>('checking');
  const [userLocation, setUserLocation] = useState<MakersMapPlace | null>(null);

  const displayPlaces = useMemo(
    () => places.length ? places : userLocation ? [userLocation] : [],
    [places, userLocation],
  );

  const readCurrentLocation = (interactive: boolean) => {
    if (!navigator.geolocation) {
      setPermission('unavailable');
      return;
    }
    if (interactive) setPermission('checking');
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setPermission('granted');
        setUserLocation({
          place_id: 'browser-current-location',
          provider: 'browser',
          name: '当前位置',
          address: '仅在当前浏览器会话中使用',
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
      },
      (error) => setPermission(error.code === error.PERMISSION_DENIED ? 'denied' : 'prompt'),
      { enableHighAccuracy: true, timeout: 12_000, maximumAge: 60_000 },
    );
  };

  useEffect(() => {
    if (places.length) return;
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
        if (next === 'granted') readCurrentLocation(false);
      };
      update();
      status.onchange = update;
    }).catch(() => setPermission('prompt'));
    return () => { disposed = true; };
  }, [places.length]);

  useEffect(() => {
    if (places.length < 2) {
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
  }, [conversationId, places, revision, optimize]);

  useEffect(() => {
    if (!displayPlaces.length) return;
    setAnimating(true);
    const timer = window.setTimeout(() => setAnimating(false), 900);
    return () => window.clearTimeout(timer);
  }, [revision, displayPlaces.length, route]);

  useEffect(() => {
    const key = import.meta.env.VITE_TENCENT_MAP_KEY?.trim();
    const container = containerRef.current;
    if (places.length >= 2 && !route && !routeError) return;
    if (!key || !container || !displayPlaces.length) {
      setMapUnavailable(Boolean(displayPlaces.length && !key));
      return;
    }
    let cancelled = false;
    let map: TencentMapInstance | null = null;
    let fitBoundsTimer: number | null = null;
    void loadTencentMap(key).then((TMap) => {
      if (cancelled || !containerRef.current) return;
      setMapUnavailable(false);
      const renderedPlaces = route?.places?.length ? route.places : displayPlaces;
      const first = renderedPlaces[0];
      map = new TMap.Map(containerRef.current, {
        center: new TMap.LatLng(first.latitude, first.longitude),
        zoom: renderedPlaces.length === 1 ? 16 : 12,
      });
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
    }).catch(() => setMapUnavailable(true));
    return () => {
      cancelled = true;
      if (fitBoundsTimer !== null) window.clearTimeout(fitBoundsTimer);
      map?.destroy?.();
    };
  }, [displayPlaces, places.length, route, routeError, revision]);

  if (!displayPlaces.length) {
    return (
      <div className="makers-map-empty makers-location-state">
        {permission === 'checking' && '正在检查位置权限…'}
        {permission === 'prompt' && <><div>今天还没有可连成路线的日程</div><Button size="small" theme="primary" onClick={() => readCurrentLocation(true)}>显示我的位置</Button></>}
        {permission === 'denied' && <div>位置权限已关闭。可在浏览器的网站设置中允许定位，或先添加至少两个有效日程地点。</div>}
        {permission === 'unavailable' && <div>当前浏览器不支持定位；添加至少两个有效日程地点后仍可显示路线。</div>}
        {permission === 'granted' && '正在获取当前位置…'}
      </div>
    );
  }

  return (
    <div className={`makers-map ${animating ? 'is-updating' : ''}`}>
      <div className="makers-map-title">{places.length ? title : '当前位置'}</div>
      <div ref={containerRef} className="makers-map-canvas" aria-label={`${title}地图`} />
      {mapUnavailable && (
        <div className="makers-map-fallback">地图 SDK 未配置或加载失败，地点数据已保留。</div>
      )}
      {routeError && <div className="makers-route-error">未能取得真实道路路线：{routeError}</div>}
      {places.length >= 2 && !route && !routeError && <div className="makers-route-loading">正在计算真实道路路线…</div>}
      {route && (
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
        {(route?.places?.length ? route.places : displayPlaces).map((place, index) => <span key={place.place_id}>{place.name === '当前位置' ? '📍' : index + 1} {place.name}</span>)}
      </div>
    </div>
  );
}

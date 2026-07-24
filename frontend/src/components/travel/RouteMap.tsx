import { useState, useEffect, useRef } from 'react';
import { Tag, Loading, MessagePlugin } from 'tdesign-react';
import { planMakersRoute, searchMakersPlaces } from '../../services/api';
import { useAppState } from '../../store/appState';
import type { MakersRoutePlan } from '../../types';
import { useLanguage } from '../../i18n';

interface Props {
  departure: string;
  destination: string;
}

/** 路线地图组件：调用腾讯位置服务显示旅游路线 + 费用估算。 */
export default function RouteMap({ departure, destination }: Props) {
  const { t } = useLanguage();
  const { conversationId } = useAppState();
  const [loading, setLoading] = useState(true);
  const [routeData, setRouteData] = useState<MakersRoutePlan | null>(null);
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchRoute = async () => {
      setLoading(true);
      try {
        const [origins, destinations] = await Promise.all([
          searchMakersPlaces(conversationId, departure),
          searchMakersPlaces(conversationId, destination),
        ]);
        if (!origins[0] || !destinations[0]) throw new Error(t('noVerifiedEndpoints'));
        setRouteData(await planMakersRoute(conversationId, [origins[0], destinations[0]]));
      } catch {
        MessagePlugin.error(t('routePlanningFailed'));
      } finally {
        setLoading(false);
      }
    };
    fetchRoute();
  }, [conversationId, departure, destination, t]);

  // 渲染腾讯地图（通过 JS API GL）
  useEffect(() => {
    if (!routeData || !mapRef.current) return;

    const key = import.meta.env.VITE_TENCENT_MAP_KEY?.trim();
    if (!key) {
      console.warn('VITE_TENCENT_MAP_KEY is not configured; skipping Tencent map rendering.');
      return;
    }

    // 动态加载腾讯地图 JS SDK
    const scriptId = 'qq-map-sdk';
    const initMap = () => {
      const TMap = window.TMap;
      const container = mapRef.current;
      if (!TMap || !container) return;

      const originLoc = routeData.places[0];
      const destLoc = routeData.places[routeData.places.length - 1];
      if (!originLoc || !destLoc) return;

      // 计算中心点和缩放
      const centerLat = (originLoc.latitude + destLoc.latitude) / 2;
      const centerLng = (originLoc.longitude + destLoc.longitude) / 2;

      const map = new TMap.Map(container, {
        center: new TMap.LatLng(centerLat, centerLng),
        zoom: 6,
      });

      // 起点 Marker
      new TMap.MultiMarker({
        map,
        geometries: [{
          id: 'origin',
          position: new TMap.LatLng(originLoc.latitude, originLoc.longitude),
        }],
      });

      // 终点 Marker
      new TMap.MultiMarker({
        map,
        styles: {
          endpoint: new TMap.MarkerStyle({
            color: '#FF0000',
          }),
        },
        geometries: [{
          id: 'destination',
          styleId: 'endpoint',
          position: new TMap.LatLng(destLoc.latitude, destLoc.longitude),
        }],
      });

      // 途经点 Marker
      if (routeData.places.length > 2) {
        routeData.places.slice(1, -1).forEach((wp, i) => {
          new TMap.MultiMarker({
            map,
            geometries: [{
              id: `wp-${i}`,
              position: new TMap.LatLng(wp.latitude, wp.longitude),
            }],
          });
        });
      }

      // 绘制路线 polyline
      if (routeData.path.length > 0) {
        const pts = routeData.path.map((point) => new TMap.LatLng(point.latitude, point.longitude));
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
  }, [routeData]);

  if (loading) {
    return (
      <div style={{ padding: 20, textAlign: 'center' }}>
        <Loading size="small" />
        <div style={{ marginTop: 8, fontSize: 13, color: 'var(--app-text-2)' }}>
          {t('planningRoute')}
        </div>
      </div>
    );
  }

  if (!routeData) return null;
  const segments = routeData.places.slice(1).map((place, index) => ({
    from: routeData.places[index].name,
    to: place.name,
  }));

  return (
    <div className="route-map-container">
      {/* 地图 */}
      <div ref={mapRef} className="route-map-canvas" style={{ width: '100%', height: 240, borderRadius: 10, overflow: 'hidden' }} />

      {/* 路线信息 */}
      <div className="route-info">
        <div className="route-info-header">
          <span className="route-info-title">{t('routeInfo')}</span>
          <Tag size="small" theme="primary" variant="light">
            {t('distanceDuration', { distance: (routeData.distance_meters / 1000).toFixed(1), minutes: Math.round(routeData.duration_seconds / 60) })}
          </Tag>
        </div>

        {/* 路段详情 */}
        {segments.length > 0 && (
          <div className="route-segments">
            {segments.map((seg, i) => (
              <div key={i} className="route-segment">
                <div className="route-segment-dot" style={{ background: i === 0 ? '#2b5aed' : i === segments.length - 1 ? '#FF0000' : '#7c5cff' }} />
                <div className="route-segment-content">
                  <div className="route-segment-route">{seg.from} → {seg.to}</div>
                  <div className="route-segment-meta">
                    {t('routeVerified')}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 费用估算 */}
        {routeData.fare && (
          <div className="route-cost">
            <div className="route-cost-title">{t('costEstimate')}</div>
            <div className="route-cost-items">
              <div className="route-cost-item">
                <span>{t('selfDrive')}</span>
                <span className="route-cost-value">{t('aboutCurrency', { amount: routeData.fare.self_driving.estimate })}</span>
              </div>
              <div className="route-cost-item">
                <span>{t('taxi')}</span>
                <span className="route-cost-value">{t('aboutCurrencyRange', { low: routeData.fare.taxi.low, high: routeData.fare.taxi.high })}</span>
              </div>
              {routeData.fare.self_driving.toll > 0 && (
                <div className="route-cost-item">
                  <span>{t('toll')}</span>
                  <span className="route-cost-value">¥{routeData.fare.self_driving.toll}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

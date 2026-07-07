import { useState, useEffect, useRef } from 'react';
import { Button, Tag, Loading, MessagePlugin, Collapse } from 'tdesign-react';
import { LocationIcon } from 'tdesign-icons-react';
import { planRoute } from '../../services/api';
import MarkdownRenderer from '../common/MarkdownRenderer';

const { Panel: CollapsePanel } = Collapse;

interface Props {
  departure: string;
  destination: string;
}

/** 路线地图组件：调用腾讯位置服务显示旅游路线 + 费用估算。 */
export default function RouteMap({ departure, destination }: Props) {
  const [loading, setLoading] = useState(true);
  const [routeData, setRouteData] = useState<any>(null);
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fetchRoute = async () => {
      setLoading(true);
      try {
        const result = await planRoute(departure, destination);
        if (result.error) {
          MessagePlugin.warning(result.error);
        } else {
          setRouteData(result);
        }
      } catch {
        MessagePlugin.error('路线规划失败');
      } finally {
        setLoading(false);
      }
    };
    fetchRoute();
  }, [departure, destination]);

  // 渲染腾讯地图（通过 JS API GL）
  useEffect(() => {
    if (!routeData || !mapRef.current) return;

    const key = import.meta.env.VITE_TENCENT_MAP_KEY?.trim(); if (!key) return;

    // 动态加载腾讯地图 JS SDK
    const scriptId = 'qq-map-sdk';
    const initMap = () => {
      const TMap = (window as any).TMap;
      if (!TMap) return;

      const originLoc = routeData.origin_location;
      const destLoc = routeData.destination_location;

      // 计算中心点和缩放
      const centerLat = (originLoc.lat + destLoc.lat) / 2;
      const centerLng = (originLoc.lng + destLoc.lng) / 2;

      const map = new TMap.Map(mapRef.current, {
        center: new TMap.LatLng(centerLat, centerLng),
        zoom: 6,
      });

      // 起点 Marker
      const markers: any[] = [];
      markers.push(new TMap.MultiMarker({
        map,
        geometries: [{
          id: 'origin',
          position: new TMap.LatLng(originLoc.lat, originLoc.lng),
        }],
      }));

      // 终点 Marker
      markers.push(new TMap.MultiMarker({
        map,
        styles: {
          endpoint: new TMap.MarkerStyle({
            color: '#FF0000',
          }),
        },
        geometries: [{
          id: 'destination',
          styleId: 'endpoint',
          position: new TMap.LatLng(destLoc.lat, destLoc.lng),
        }],
      }));

      // 途经点 Marker
      if (routeData.waypoint_locations) {
        routeData.waypoint_locations.forEach((wp: any, i: number) => {
          markers.push(new TMap.MultiMarker({
            map,
            geometries: [{
              id: `wp-${i}`,
              position: new TMap.LatLng(wp.lat, wp.lng),
            }],
          }));
        });
      }

      // 绘制路线 polyline
      if (routeData.polyline && routeData.polyline.length > 0) {
        const pts: any[] = [];
        for (let i = 0; i < routeData.polyline.length; i += 2) {
          pts.push(new TMap.LatLng(routeData.polyline[i], routeData.polyline[i + 1]));
        }
        const polyline = new TMap.MultiPolyline({
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

    if (!(window as any).TMap) {
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
          正在规划路线...
        </div>
      </div>
    );
  }

  if (!routeData) return null;

  return (
    <div className="route-map-container">
      {/* 地图 */}
      <div ref={mapRef} className="route-map-canvas" style={{ width: '100%', height: 240, borderRadius: 10, overflow: 'hidden' }} />

      {/* 路线信息 */}
      <div className="route-info">
        <div className="route-info-header">
          <span className="route-info-title">🚗 路线信息</span>
          <Tag size="small" theme="primary" variant="light">
            {routeData.total_distance_km}km · {Math.round(routeData.total_duration_hours * 60)}分钟
          </Tag>
        </div>

        {/* 天气信息 */}
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

        {/* 路段详情 */}
        {routeData.segments && (
          <div className="route-segments">
            {routeData.segments.map((seg: any, i: number) => (
              <div key={i} className="route-segment">
                <div className="route-segment-dot" style={{ background: i === 0 ? '#2b5aed' : i === routeData.segments.length - 1 ? '#FF0000' : '#7c5cff' }} />
                <div className="route-segment-content">
                  <div className="route-segment-route">{seg.from} → {seg.to}</div>
                  <div className="route-segment-meta">
                    {(seg.distance / 1000).toFixed(1)}km · {(seg.duration / 3600).toFixed(1)}h
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 费用估算 */}
        {routeData.cost_estimate && (
          <div className="route-cost">
            <div className="route-cost-title">💰 费用估算</div>
            <div className="route-cost-items">
              <div className="route-cost-item">
                <span>自驾</span>
                <span className="route-cost-value">约 ¥{routeData.cost_estimate.self_driving}</span>
              </div>
              <div className="route-cost-item">
                <span>打车</span>
                <span className="route-cost-value">约 ¥{routeData.cost_estimate.taxi}</span>
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
    </div>
  );
}

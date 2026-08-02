import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'tdesign-react';
import { useAppDispatch } from '../../../store/appState';
import type { MakersMapPlace, MakersRouteMode, MakersRoutePlan, MakersRouteStrategy } from '../../../shared/types';
import { LOCATION_OPTIONS, locationErrorMessage, permissionAfterLocationFailure } from '../model/makersMapLocation';
import { shouldPlanMakersRoute } from '../model/makersMapRouting';
import { translate, useLanguage } from '../../../i18n';
import {
  BROWSER_LOCATION_EVENT,
  clearBrowserLocation,
  currentBrowserLocation,
  publishBrowserLocation,
} from '../../../services/browserLocation';
import { useMapsController } from '../controller/useMapsController';

interface Props {
  conversationId: string;
  title: string;
  places: MakersMapPlace[];
  revision: number;
  /** Whether this map represents an ordered plan (for example a day's schedule). */
  showRoute?: boolean;
  routeMode?: MakersRouteMode;
  routeStrategy?: MakersRouteStrategy;
}

type PermissionState = 'checking' | 'prompt' | 'granted' | 'denied' | 'unavailable';
type RouteViewLevel = 1 | 2 | 3;

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
      reject(new Error(translate('mapSdkTimeout')));
    }, MAP_SDK_TIMEOUT_MS);
    script.onload = () => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      if (window.TMap) resolve(window.TMap);
      else {
        resetTencentMapSdk();
        reject(new Error(translate('mapSdkFailed')));
      }
    };
    script.onerror = () => {
      if (settled) return;
      settled = true;
      window.clearTimeout(timer);
      resetTencentMapSdk();
      reject(new Error(translate('mapSdkFailed')));
    };
    document.head.appendChild(script);
  });
  return sdkPromise;
}

function hoursMinutes(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return translate('minutes', { count: minutes });
  return translate('hoursMinutes', { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
}

export default function MakersMap({
  conversationId, title, places, revision, showRoute = false, routeMode, routeStrategy,
}: Props) {
  const { t } = useLanguage();
  const dispatch = useAppDispatch();
  const { ingestSignal, planVerifiedRoute } = useMapsController(conversationId);
  const containerRef = useRef<HTMLDivElement>(null);
  const [animating, setAnimating] = useState(false);
  const [mapUnavailable, setMapUnavailable] = useState(false);
  const [mapLoading, setMapLoading] = useState(false);
  const [route, setRoute] = useState<MakersRoutePlan | null>(null);
  const routeGroups = useMemo(() => {
    const grouped = new Map<string, MakersMapPlace[]>();
    places.forEach((place) => {
      const city = String(place.city || t('routeWholeTrip'));
      grouped.set(city, [...(grouped.get(city) || []), place]);
    });
    return [...grouped.entries()].map(([city, items]) => ({ city, places: items }));
  }, [places, t]);
  const [routeViewLevel, setRouteViewLevel] = useState<RouteViewLevel>(1);
  const [routeCity, setRouteCity] = useState('');
  const [routeSegment, setRouteSegment] = useState(0);
  const [routeModeOverride, setRouteModeOverride] = useState<MakersRouteMode | undefined>(routeMode);
  const [routeError, setRouteError] = useState('');
  const [permission, setPermission] = useState<PermissionState>('checking');
  const [userLocation, setUserLocation] = useState<MakersMapPlace | null>(() => {
    const location = currentBrowserLocation();
    return location ? {
      place_id: 'browser-current-location',
      provider: 'browser-wgs84',
      name: translate('currentLocation'),
      address: translate('sessionOnlyLocation'),
      latitude: location.latitude,
      longitude: location.longitude,
    } : null;
  });
  const [renderAttempt, setRenderAttempt] = useState(0);
  const [locationError, setLocationError] = useState('');
  const locationRequestRef = useRef(0);

  useEffect(() => {
    setRouteModeOverride(routeMode);
  }, [routeMode]);

  useEffect(() => {
    if (!routeGroups.length) return;
    setRouteCity((current) => (
      routeGroups.some((group) => group.city === current)
        ? current
        : routeGroups[0].city
    ));
    setRouteViewLevel(routeGroups.length > 1 ? 1 : 2);
    setRouteSegment(0);
  }, [routeGroups]);

  const selectedRouteGroup = routeGroups.find((group) => group.city === routeCity)
    || routeGroups[0];
  const routeDisplayPlaces = useMemo(() => {
    if (!showRoute || places.length < 3 || !routeGroups.length) return places;
    if (routeViewLevel === 1 && routeGroups.length > 1) {
      return routeGroups.map((group, index) => (
        index === routeGroups.length - 1
          ? group.places[group.places.length - 1]
          : group.places[0]
      ));
    }
    const cityPlaces = selectedRouteGroup?.places || places;
    if (routeViewLevel === 3 && cityPlaces.length > 1) {
      const start = Math.min(routeSegment, cityPlaces.length - 2);
      return cityPlaces.slice(start, start + 2);
    }
    return cityPlaces;
  }, [places, routeGroups, routeSegment, routeViewLevel, selectedRouteGroup, showRoute]);
  const displayPlaces = useMemo(
    () => routeDisplayPlaces.length ? routeDisplayPlaces : userLocation ? [userLocation] : [],
    [routeDisplayPlaces, userLocation],
  );

  const readCurrentLocation = useCallback(() => {
    if (!navigator.geolocation) {
      setPermission('unavailable');
      setLocationError(t('geolocationUnsupported'));
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
          ...publishBrowserLocation(position),
          name: t('currentLocation'),
          address: t('sessionOnlyLocation'),
        });
        const localDay = new Date().toLocaleDateString('en-CA');
        void ingestSignal({
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
        setLocationError(locationErrorMessage(error));
        if (!navigator.permissions) {
          setPermission(permissionAfterLocationFailure(error.code));
          return;
        }
        void navigator.permissions.query({ name: 'geolocation' })
          .then((status) => {
            if (requestId !== locationRequestRef.current) return;
            setPermission(permissionAfterLocationFailure(error.code, status.state));
          })
          .catch(() => setPermission(permissionAfterLocationFailure(error.code)));
      },
      LOCATION_OPTIONS,
    );
  }, [dispatch, ingestSignal, t]);

  useEffect(() => {
    const syncSharedLocation = () => {
      const location = currentBrowserLocation();
      if (!location) {
        setUserLocation(null);
        return;
      }
      setPermission('granted');
      setLocationError('');
      setUserLocation({
        place_id: 'browser-current-location',
        provider: 'browser-wgs84',
        name: t('currentLocation'),
        address: t('sessionOnlyLocation'),
        latitude: location.latitude,
        longitude: location.longitude,
      });
    };
    window.addEventListener(BROWSER_LOCATION_EVENT, syncSharedLocation);
    // Keep the blue point and the chat request truth contract aligned. A map
    // must not keep showing an expired fix after the backend would reject it.
    const timer = window.setInterval(syncSharedLocation, 60_000);
    syncSharedLocation();
    return () => {
      window.removeEventListener(BROWSER_LOCATION_EVENT, syncSharedLocation);
      window.clearInterval(timer);
    };
  }, [t]);

  const checkPermissionAndRead = useCallback(() => {
    if (!navigator.geolocation) {
      setPermission('unavailable');
      setLocationError(t('geolocationUnsupported'));
      return;
    }
    if (!navigator.permissions) {
      readCurrentLocation();
      return;
    }
    setPermission('checking');
    setLocationError('');
    void navigator.permissions.query({ name: 'geolocation' })
      .then((status) => {
        if (status.state === 'denied') {
          clearBrowserLocation('denied');
          setPermission('denied');
          setLocationError(t('locationPermissionClosed'));
          return;
        }
        // Both "granted" and "prompt" must go through the browser's native
        // geolocation request. The latter may show the permission prompt.
        readCurrentLocation();
      })
      .catch(readCurrentLocation);
  }, [readCurrentLocation, t]);

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
        if (next === 'denied') clearBrowserLocation('denied');
        setPermission(next);
        if (next === 'granted') readCurrentLocation();
      };
      update();
      status.onchange = update;
    }).catch(() => setPermission('prompt'));
    return () => { disposed = true; };
  }, [readCurrentLocation]);

  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'visible') {
        if (!navigator.permissions) return;
        void navigator.permissions.query({ name: 'geolocation' }).then((status) => {
          const next = status.state === 'granted' ? 'granted' : status.state === 'denied' ? 'denied' : 'prompt';
          setPermission(next);
          if (next === 'granted' && !userLocation) readCurrentLocation();
        }).catch(() => {});
      }
    };
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [readCurrentLocation, userLocation]);

  useEffect(() => {
    if (!shouldPlanMakersRoute(showRoute, routeDisplayPlaces.length)) {
      setRoute(null);
      setRouteError('');
      return;
    }
    let disposed = false;
    setRoute(null);
    setRouteError('');
    void planVerifiedRoute(routeDisplayPlaces, routeModeOverride, routeStrategy)
      .then((next) => { if (!disposed) setRoute(next); })
      .catch((error) => { if (!disposed) setRouteError(error instanceof Error ? error.message : t('routePlanningFailed')); });
    return () => { disposed = true; };
  }, [planVerifiedRoute, revision, routeDisplayPlaces, routeModeOverride, routeStrategy, showRoute, t]);

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
          content: place.name === t('currentLocation') ? place.name : `${index + 1}. ${place.name}`,
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
  }, [displayPlaces, places.length, route, routeError, revision, renderAttempt, t]);

  if (!displayPlaces.length) {
    return (
      <div className="makers-map-empty makers-location-state">
        {permission === 'checking' && <><div>{t('gettingLocation')}</div><Button size="small" variant="outline" disabled>{t('locating')}</Button></>}
        {permission === 'prompt' && <><div>{locationError || t('noRouteScheduleToday')}</div><Button size="small" theme="primary" onClick={checkPermissionAndRead}>{t('showMyLocation')}</Button></>}
        {permission === 'denied' && <><div>{locationError || t('locationPermissionClosed')}</div><Button size="small" variant="outline" onClick={checkPermissionAndRead}>{t('recheckLocation')}</Button></>}
        {permission === 'unavailable' && <div>{t('locationUnsupportedRouteAvailable')}</div>}
        {permission === 'granted' && <><div>{locationError || t('permissionReadingLocation')}</div><Button size="small" variant="outline" onClick={checkPermissionAndRead}>{t('relocate')}</Button></>}
      </div>
    );
  }

  return (
    <div className={`makers-map ${animating ? 'is-updating' : ''}`}>
      <div className="makers-map-title">{places.length ? title : t('currentLocation')}</div>
      {showRoute && places.length > 2 && <div className="makers-route-hierarchy" aria-label={t('routeHierarchy')}>
        <div className="makers-route-levels">
          {routeGroups.length > 1 && <button type="button" className={routeViewLevel === 1 ? 'is-active' : ''} onClick={() => setRouteViewLevel(1)}>{t('routeLevelCities')}</button>}
          <button type="button" className={routeViewLevel === 2 ? 'is-active' : ''} onClick={() => setRouteViewLevel(2)}>{t('routeLevelCity')}</button>
          <button type="button" className={routeViewLevel === 3 ? 'is-active' : ''} onClick={() => setRouteViewLevel(3)}>{t('routeLevelSegment')}</button>
        </div>
        {routeViewLevel > 1 && <div className="makers-route-filters">
          {routeGroups.length > 1 && <select value={selectedRouteGroup?.city || ''} onChange={(event) => { setRouteCity(event.target.value); setRouteSegment(0); }}>
            {routeGroups.map((group) => <option value={group.city} key={group.city}>{group.city}</option>)}
          </select>}
          {routeViewLevel === 3 && (selectedRouteGroup?.places.length || 0) > 1 && <select value={routeSegment} onChange={(event) => setRouteSegment(Number(event.target.value))}>
            {selectedRouteGroup.places.slice(1).map((place, index) => <option value={index} key={`${place.place_id}-${index}`}>
              {selectedRouteGroup.places[index].name} → {place.name}
            </option>)}
          </select>}
          {routeViewLevel === 3 && <select value={routeModeOverride || 'driving'} onChange={(event) => setRouteModeOverride(event.target.value as MakersRouteMode)}>
            <option value="driving">{t('routeModeDriving')}</option>
            <option value="transit">{t('routeModeTransit')}</option>
            <option value="walking">{t('routeModeWalking')}</option>
            <option value="bicycling">{t('routeModeBicycling')}</option>
          </select>}
        </div>}
      </div>}
      <div ref={containerRef} className="makers-map-canvas" aria-label={t('mapAria', { title })} />
      {mapLoading && <div className="makers-map-loading" role="status">{t('loadingTencentMap')}</div>}
      {mapUnavailable && (
        <div className="makers-map-fallback" role="status">
          <strong>{t('mapBaseUnavailable')}</strong>
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
          }}>{t('retryMapBase')}</Button>
        </div>
      )}
      {showRoute && routeError && <div className="makers-route-error">{t('realRouteFailed', { error: routeError })}</div>}
      {shouldPlanMakersRoute(showRoute, routeDisplayPlaces.length) && !route && !routeError && <div className="makers-route-loading">{t('calculatingRoute')}</div>}
      {showRoute && route && (
        <div className="makers-route-summary">
          <span>{t(
            route.mode === 'transit' ? 'routeModeTransit'
              : route.mode === 'walking' ? 'routeModeWalking'
                : route.mode === 'bicycling' ? 'routeModeBicycling'
                  : 'routeModeDriving',
          )}</span>
          <span>{t('kilometers', { count: (route.distance_meters / 1000).toFixed(1) })}</span>
          <span>{hoursMinutes(route.duration_seconds)}</span>
          {route.fare.self_driving && <span>{t('drivingEstimate', { amount: route.fare.self_driving.estimate.toFixed(0) })}</span>}
          {route.fare.taxi && <span>{t('taxiEstimate', { low: route.fare.taxi.low.toFixed(0), high: route.fare.taxi.high.toFixed(0) })}</span>}
          {route.fare.transit?.provider_estimate && <span>{t('transitFareEstimate', { amount: route.fare.transit.estimate.toFixed(0) })}</span>}
          {route.transit?.lines?.length ? <span>{t('transitLines', { lines: route.transit.lines.join(' → ') })}</span> : null}
          {route.transit?.walking_distance_meters !== undefined && <span>{t('transitWalkingDistance', { count: route.transit.walking_distance_meters })}</span>}
          <small>{route.fare.basis}</small>
          <small>{route.cache?.hit ? t('routeCacheHit') : t('routeCacheSaved')}</small>
        </div>
      )}
      <div className="makers-place-chips">
        {(route?.places?.length ? route.places : displayPlaces).map((place, index) => <span key={`${place.place_id}-${index}`}>{place.name === t('currentLocation') ? '📍' : index + 1} {place.name}</span>)}
      </div>
    </div>
  );
}

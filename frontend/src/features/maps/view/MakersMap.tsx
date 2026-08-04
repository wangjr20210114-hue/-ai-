import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'tdesign-react';
import { useAppDispatch } from '../../../store/appState';
import type {
  MakersMapPlace,
  MakersRouteMode,
  MakersRoutePlan,
  MakersRouteSectionMode,
  MakersRouteStrategy,
} from '../model';
import { LOCATION_OPTIONS, locationErrorMessage, permissionAfterLocationFailure } from '../model/makersMapLocation';
import { shouldPlanMakersRoute, shouldRequestMakersRoute } from '../model/makersMapRouting';
import {
  closestRouteSectionIndex,
  legModeSequence,
  ROUTE_MODE_COLORS,
  routeCities,
  routeLegs,
  routeSectionPath,
  routeSectionSteps,
  routeZoomLevel,
  type RouteZoomLevel,
  visibleRouteSections,
} from '../model/routePresentation';
import { translate, useLanguage } from '../../../i18n';
import {
  BROWSER_LOCATION_EVENT,
  clearBrowserLocation,
  currentBrowserLocation,
  publishBrowserLocation,
} from '../../../services/browserLocation';
import { useMapsController } from '../controller/useMapsController';
import RouteJourneyCard from './RouteJourneyCard';

interface Props {
  conversationId: string;
  title: string;
  places: MakersMapPlace[];
  revision: number;
  /** Whether this map represents an ordered plan (for example a day's schedule). */
  showRoute?: boolean;
  routeMode?: MakersRouteMode;
  routeStrategy?: MakersRouteStrategy;
  routeSnapshot?: MakersRoutePlan;
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

function mapCenterPoint(center: TencentMapCoordinate | undefined) {
  if (!center) return null;
  const latitude = center.getLat?.() ?? center.lat;
  const longitude = center.getLng?.() ?? center.lng;
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    ? { latitude: Number(latitude), longitude: Number(longitude) }
    : null;
}

export default function MakersMap({
  conversationId, title, places, revision, showRoute = false, routeMode, routeStrategy, routeSnapshot,
}: Props) {
  const { t } = useLanguage();
  const dispatch = useAppDispatch();
  const { ingestSignal, planVerifiedRoute } = useMapsController(conversationId);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<TencentMapInstance | null>(null);
  const mapNamespaceRef = useRef<TencentMapNamespace | null>(null);
  const [animating, setAnimating] = useState(false);
  const [mapUnavailable, setMapUnavailable] = useState(false);
  const [mapLoading, setMapLoading] = useState(false);
  const [route, setRoute] = useState<MakersRoutePlan | null>(null);
  const [visibleRouteLevel, setVisibleRouteLevel] = useState<RouteZoomLevel>('legs');
  const [activeRouteStep, setActiveRouteStep] = useState(0);
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

  const displayPlaces = useMemo(
    () => places.length ? places : userLocation ? [userLocation] : [],
    [places, userLocation],
  );

  useEffect(() => {
    const stepCount = route ? routeSectionSteps(route).length : 0;
    setActiveRouteStep((current) => Math.max(0, Math.min(current, Math.max(0, stepCount - 1))));
  }, [route]);

  const focusRouteStep = useCallback((index: number) => {
    if (!route) return;
    const steps = routeSectionSteps(route);
    const nextIndex = Math.max(0, Math.min(index, Math.max(0, steps.length - 1)));
    setActiveRouteStep(nextIndex);
    const map = mapRef.current;
    const TMap = mapNamespaceRef.current;
    const path = steps[nextIndex] ? routeSectionPath(steps[nextIndex]) : [];
    if (!map || !TMap?.LatLngBounds || !map.fitBounds || path.length < 2) return;
    const bounds = new TMap.LatLngBounds();
    path.forEach((point) => bounds.extend(new TMap.LatLng(point.latitude, point.longitude)));
    map.fitBounds(bounds, { padding: 72 });
  }, [route]);

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
    if (!shouldPlanMakersRoute(showRoute, places.length)) {
      setRoute(null);
      setRouteError('');
      return;
    }
    if (!shouldRequestMakersRoute(showRoute, places.length, routeSnapshot) && routeSnapshot?.places?.length) {
      setRoute(routeSnapshot);
      setRouteError('');
      return;
    }
    let disposed = false;
    setRoute(null);
    setRouteError('');
    void planVerifiedRoute(places, routeMode, routeStrategy)
      .then((next) => { if (!disposed) setRoute(next); })
      .catch((error) => { if (!disposed) setRouteError(error instanceof Error ? error.message : t('routePlanningFailed')); });
    return () => { disposed = true; };
  }, [planVerifiedRoute, revision, places, routeMode, routeStrategy, routeSnapshot, showRoute, t]);

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
    let zoomListener: (() => void) | null = null;
    let centerListener: (() => void) | null = null;
    let attentionTimer: number | null = null;
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
      mapRef.current = map;
      mapNamespaceRef.current = TMap;
      const resizeMap = () => map?.resize?.();
      if (typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(resizeMap);
        resizeObserver.observe(containerRef.current);
      }
      resizeTimer = window.setTimeout(resizeMap, 180);
      const placeMarkers = new TMap.MultiMarker({
        map,
        geometries: renderedPlaces.map((place, index) => ({
          id: `makers-place-${place.place_id || index}`,
          position: new TMap.LatLng(place.latitude, place.longitude),
          properties: { title: `${index + 1}. ${place.name}` },
        })),
      });
      const placeLabels = new TMap.MultiLabel({
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
      const cityStops = routeCities(renderedPlaces);
      const cityMarkers = cityStops.length > 1 ? new TMap.MultiMarker({
        map: null,
        geometries: cityStops.map(({ city, place }, index) => ({
          id: `makers-city-${index}`,
          position: new TMap.LatLng(place.latitude, place.longitude),
          properties: { title: city },
        })),
      }) : null;
      const cityLabels = cityStops.length > 1 ? new TMap.MultiLabel({
        map: null,
        styles: {
          city: new TMap.LabelStyle({
            color: '#162033', size: 13, offset: { x: 0, y: -34 },
            backgroundColor: '#ffffff', borderColor: '#c7cfdd', borderWidth: 1,
            borderRadius: 7, padding: '5px 8px',
          }),
        },
        geometries: cityStops.map(({ city, place }, index) => ({
          id: `makers-city-label-${index}`,
          styleId: 'city',
          position: new TMap.LatLng(place.latitude, place.longitude),
          content: `${index + 1}. ${city}`,
        })),
      }) : null;
      const routeStyles = Object.fromEntries(
        (Object.entries(ROUTE_MODE_COLORS) as Array<[MakersRouteSectionMode, string]>).map(
          ([mode, color]) => [mode, new TMap.PolylineStyle({
            color, width: 6, borderWidth: 2, borderColor: '#ffffff',
          })],
        ),
      );
      const overviewGeometry = route?.path && route.path.length > 1 ? [{
        id: 'makers-route-overview',
        styleId: 'overview',
        paths: route.path.map((point) => new TMap.LatLng(point.latitude, point.longitude)),
      }] : [];
      const overviewPolyline = overviewGeometry.length ? new TMap.MultiPolyline({
        map,
        styles: {
          overview: new TMap.PolylineStyle({
            color: '#64748b', width: 5, borderWidth: 2, borderColor: '#ffffff',
          }),
        },
        geometries: overviewGeometry,
      }) : null;
      const legGeometries = route ? routeLegs(route)
        .filter((leg) => leg.path.length > 1)
        .map((leg, index) => {
          const mode = legModeSequence(leg).find((item) => item !== 'walking') || leg.mode;
          return {
            id: `makers-route-leg-${index}`,
            styleId: mode,
            paths: leg.path.map((point) => new TMap.LatLng(point.latitude, point.longitude)),
          };
        }) : [];
      const legPolyline = legGeometries.length ? new TMap.MultiPolyline({
        map: null,
        styles: routeStyles,
        geometries: legGeometries,
      }) : null;
      const sectionGeometries = route ? visibleRouteSections(route)
        .filter((section) => section.path.length > 1)
        .map((section, index) => ({
          id: `makers-route-section-${index}`,
          styleId: section.mode,
          paths: section.path.map((point) => new TMap.LatLng(point.latitude, point.longitude)),
        })) : [];
      const sectionPolyline = sectionGeometries.length ? new TMap.MultiPolyline({
        map: null,
        styles: routeStyles,
        geometries: sectionGeometries,
      }) : null;
      const updateRouteLayers = () => {
        if (!map || !route) return;
        const level = routeZoomLevel(map.getZoom?.() ?? 12);
        setVisibleRouteLevel(level);
        overviewPolyline?.setMap?.(level === 'overview' ? map : null);
        legPolyline?.setMap?.(level === 'legs' ? map : null);
        sectionPolyline?.setMap?.(level === 'sections' ? map : null);
        const cityOverview = level === 'overview' && cityStops.length > 1;
        cityMarkers?.setMap?.(cityOverview ? map : null);
        cityLabels?.setMap?.(cityOverview ? map : null);
        placeMarkers.setMap?.(cityOverview ? null : map);
        placeLabels.setMap?.(cityOverview ? null : map);
        const center = mapCenterPoint(map.getCenter?.());
        if (center) {
          const focused = closestRouteSectionIndex(route, center);
          if (focused >= 0) setActiveRouteStep((current) => current === focused ? current : focused);
        }
      };
      zoomListener = updateRouteLayers;
      centerListener = () => {
        if (attentionTimer !== null) window.clearTimeout(attentionTimer);
        attentionTimer = window.setTimeout(updateRouteLayers, 80);
      };
      map.on?.('zoom_changed', updateRouteLayers);
      map.on?.('center_changed', centerListener);
      updateRouteLayers();
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
      if (attentionTimer !== null) window.clearTimeout(attentionTimer);
      resizeObserver?.disconnect();
      if (zoomListener) map?.off?.('zoom_changed', zoomListener);
      if (centerListener) map?.off?.('center_changed', centerListener);
      if (mapRef.current === map) {
        mapRef.current = null;
        mapNamespaceRef.current = null;
      }
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
      <div ref={containerRef} className="makers-map-canvas" aria-label={t('mapAria', { title })} />
      {showRoute && route && <div className="makers-route-zoom-hint">
        {t(
          visibleRouteLevel === 'overview' ? 'routeZoomOverview'
            : visibleRouteLevel === 'sections' ? 'routeZoomSections'
              : 'routeZoomLegs',
        )}
        <small>{t('routeZoomHint')}</small>
      </div>}
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
      {shouldPlanMakersRoute(showRoute, places.length) && !route && !routeError && <div className="makers-route-loading">{t('calculatingRoute')}</div>}
      {showRoute && route && <RouteJourneyCard
        route={route}
        activeStep={activeRouteStep}
        onSelectStep={focusRouteStep}
      />}
      {(!showRoute || !route) && <div className="makers-place-chips">
        {(route?.places?.length ? route.places : displayPlaces).map((place, index) => <span key={`${place.place_id}-${index}`}>{place.name === t('currentLocation') ? '📍' : index + 1} {place.name}</span>)}
      </div>}
    </div>
  );
}

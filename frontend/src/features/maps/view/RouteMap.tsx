import { useEffect, useState } from 'react';
import { Loading, MessagePlugin } from 'tdesign-react';
import { useAppState } from '../../../store/appState';
import type { MakersMapPlace, MakersRouteMode, MakersRouteStrategy } from '../../../shared/types';
import { useLanguage } from '../../../i18n';
import { useMapsController } from '../controller/useMapsController';
import MakersMap from './MakersMap';

interface Props {
  departure: string;
  destination: string;
  routeMode?: MakersRouteMode;
  routeStrategy?: MakersRouteStrategy;
}

/**
 * Adapter used by travel cards.
 *
 * Endpoint lookup stays here, while all map rendering and route geometry is
 * delegated to MakersMap. That keeps the Tencent adapter, zoom hierarchy,
 * mixed-transport colours, and section contract identical across the app.
 */
export default function RouteMap({
  departure,
  destination,
  routeMode,
  routeStrategy = 'time_then_cost',
}: Props) {
  const { t } = useLanguage();
  const { conversationId } = useAppState();
  const { searchVerifiedPlaces } = useMapsController(conversationId);
  const [loading, setLoading] = useState(true);
  const [places, setPlaces] = useState<MakersMapPlace[]>([]);

  useEffect(() => {
    let disposed = false;
    const fetchPlaces = async () => {
      setLoading(true);
      try {
        const [origins, destinations] = await Promise.all([
          searchVerifiedPlaces(departure),
          searchVerifiedPlaces(destination),
        ]);
        if (!origins[0] || !destinations[0]) throw new Error(t('noVerifiedEndpoints'));
        if (!disposed) setPlaces([origins[0], destinations[0]]);
      } catch {
        if (!disposed) MessagePlugin.error(t('routePlanningFailed'));
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    void fetchPlaces();
    return () => { disposed = true; };
  }, [departure, destination, searchVerifiedPlaces, t]);

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

  if (!places.length) return null;
  return (
    <MakersMap
      conversationId={conversationId}
      title={`${departure} → ${destination}`}
      places={places}
      revision={places.length}
      showRoute
      routeMode={routeMode}
      routeStrategy={routeStrategy}
    />
  );
}

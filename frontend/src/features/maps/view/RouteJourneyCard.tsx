import type { CSSProperties } from 'react';
import { Button } from 'tdesign-react';
import { ChevronLeftIcon, ChevronRightIcon } from 'tdesign-icons-react';
import { useLanguage } from '../../../i18n';
import type { MakersRoutePlan, MakersRouteSectionMode } from '../model';
import {
  ROUTE_MODE_COLORS,
  routeHasIntercityLeg,
  routeLegScope,
  routeSectionEndpoints,
  routeSectionSteps,
} from '../model/routePresentation';

interface Props {
  route: MakersRoutePlan;
  activeStep: number;
  onSelectStep: (index: number) => void;
}

export default function RouteJourneyCard({ route, activeStep, onSelectStep }: Props) {
  const { t } = useLanguage();
  const steps = routeSectionSteps(route);
  const activeIndex = Math.max(0, Math.min(activeStep, Math.max(0, steps.length - 1)));
  const current = steps[activeIndex];

  const duration = (seconds: number) => {
    const minutes = Math.max(1, Math.round(seconds / 60));
    return minutes < 60
      ? t('minutes', { count: minutes })
      : t('hoursMinutes', { hours: Math.floor(minutes / 60), minutes: minutes % 60 });
  };
  const distance = (meters: number) => t('kilometers', { count: (meters / 1000).toFixed(1) });
  const modeName = (mode: MakersRouteSectionMode) => t(
    mode === 'driving' ? 'routeModeDriving'
      : mode === 'walking' ? 'routeModeWalking'
        : mode === 'bicycling' ? 'routeModeBicycling'
          : mode === 'rail' ? 'routeModeRail'
            : mode === 'bus' ? 'routeModeBus'
              : 'routeModeTransit',
  );
  const routeName = t(
    route.mode === 'transit' && routeHasIntercityLeg(route)
      ? 'routeModeTransitIntercity'
      : route.mode === 'transit' ? 'routeModeTransit'
        : route.mode === 'walking' ? 'routeModeWalking'
          : route.mode === 'bicycling' ? 'routeModeBicycling'
            : 'routeModeDriving',
  );
  const fare = route.fare.self_driving
    ? t('drivingEstimate', { amount: route.fare.self_driving.estimate.toFixed(0) })
    : route.fare.taxi
      ? t('taxiEstimate', {
        low: route.fare.taxi.low.toFixed(0),
        high: route.fare.taxi.high.toFixed(0),
      })
      : route.fare.transit?.provider_estimate
        ? t('transitFareEstimate', { amount: route.fare.transit.estimate.toFixed(0) })
        : '';
  const sectionTitle = current
    ? current.section.line || current.section.vehicle || modeName(current.section.mode)
    : '';
  const sectionEndpoints = current ? routeSectionEndpoints(steps, activeIndex) : null;
  const sectionStops = current?.section.instruction || (sectionEndpoints
    ? t('routeStepStops', { from: sectionEndpoints.from, to: sectionEndpoints.to })
    : '');

  return (
    <section className="makers-route-journey" aria-label={t('routeWholeTrip')}>
      <div className="makers-route-overview">
        <strong>{routeName}</strong>
        <div className="makers-route-primary-metrics">
          <span>{distance(route.distance_meters)}</span>
          <span>{duration(route.duration_seconds)}</span>
          {fare && <span>{fare}</span>}
        </div>
        {(Boolean(route.transit?.transfer_count) || Boolean(route.transit?.walking_distance_meters)) && (
          <div className="makers-route-secondary-metrics">
            {Boolean(route.transit?.transfer_count) && <span>{t('routeTransferCount', { count: route.transit?.transfer_count || 0 })}</span>}
            {Boolean(route.transit?.walking_distance_meters) && <span>{t('transitWalkingDistance', { count: route.transit?.walking_distance_meters || 0 })}</span>}
          </div>
        )}
        {route.fare.basis && <details className="makers-route-fare-note">
          <summary>{t('routeFareDetails')}</summary>
          <p>{route.fare.basis}</p>
        </details>}
      </div>

      {current && <div className="makers-route-focus" key={`${activeIndex}-${sectionTitle}`}>
        <div className="makers-route-focus-heading">
          <div>
            <span>{t('routeCurrentSection', { current: activeIndex + 1, total: steps.length })}</span>
            {routeLegScope(current.leg) !== 'unknown' && <em>{t(
              routeLegScope(current.leg) === 'intercity' ? 'routeScopeIntercity' : 'routeScopeLocal',
            )}</em>}
          </div>
          <nav aria-label={t('routeSectionNavigation')}>
            <Button
              shape="circle"
              size="small"
              variant="text"
              icon={<ChevronLeftIcon />}
              aria-label={t('routePreviousSection')}
              title={t('routePreviousSection')}
              disabled={activeIndex === 0}
              onClick={() => onSelectStep(activeIndex - 1)}
            />
            <Button
              shape="circle"
              size="small"
              variant="text"
              icon={<ChevronRightIcon />}
              aria-label={t('routeNextSection')}
              title={t('routeNextSection')}
              disabled={activeIndex === steps.length - 1}
              onClick={() => onSelectStep(activeIndex + 1)}
            />
          </nav>
        </div>
        <div className="makers-route-focus-body">
          <i
            aria-hidden="true"
            style={{ '--route-mode-color': ROUTE_MODE_COLORS[current.section.mode] } as CSSProperties}
          />
          <div>
            <strong>{sectionTitle}</strong>
            {sectionStops && <p>{sectionStops}</p>}
            <small>
              {distance(current.section.distance_meters)} · {duration(current.section.duration_seconds)}
              {current.section.station_count ? ` · ${t('routeStationCount', { count: current.section.station_count })}` : ''}
            </small>
          </div>
        </div>
      </div>}

      {steps.length > 1 && <details className="makers-route-all-steps">
        <summary>{t('routeAllSections', { count: steps.length })}</summary>
        <ol>
          {steps.map(({ leg, section }, index) => {
            const title = section.line || section.vehicle || modeName(section.mode);
            const endpoints = routeSectionEndpoints(steps, index);
            const stops = section.instruction || (endpoints
              ? t('routeStepStops', { from: endpoints.from, to: endpoints.to })
              : '');
            return <li key={`${leg.from.place_id}-${leg.to.place_id}-${section.mode}-${index}`}>
              <button
                type="button"
                className={index === activeIndex ? 'is-active' : ''}
                aria-current={index === activeIndex ? 'step' : undefined}
                onClick={() => onSelectStep(index)}
              >
                <i
                  aria-hidden="true"
                  style={{ '--route-mode-color': ROUTE_MODE_COLORS[section.mode] } as CSSProperties}
                />
                <span>
                  <strong>{title}</strong>
                  {stops && <small>{stops}</small>}
                </span>
              </button>
            </li>;
          })}
        </ol>
      </details>}
    </section>
  );
}

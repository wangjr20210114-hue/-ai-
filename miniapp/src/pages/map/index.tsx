import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { Button, Map, Text, View } from '@tarojs/components'
import { getOrCreateConversationId } from '@/services/conversations'
import {
  planOrderedRoute,
  type PlannedRoute,
  type RoutePlace,
} from '@/services/routes'
import { apiUrl } from '@/services/config'
import { ensureSession } from '@/services/session'
import { requestCurrentLocation } from '@/services/location'
import { readLanguage, translate, type Language } from '@/i18n'
import './index.scss'

type MapState = {
  title?: string
  places?: RoutePlace[]
  route_mode?: string
  route_strategy?: string
  show_route?: boolean
}

export default function MapPage() {
  const [mapState] = useState<MapState>(() => Taro.getStorageSync('floris.miniapp.active-map.v1') || {})
  const [route, setRoute] = useState<PlannedRoute | null>(null)
  const [routeError, setRouteError] = useState('')
  const [locating, setLocating] = useState(false)
  const [language] = useState<Language>(readLanguage())
  const places = mapState.places || []
  const center = places[0] || { latitude: 39.9042, longitude: 116.4074 }

  useEffect(() => {
    void Taro.setNavigationBarTitle({ title: translate('navMap', {}, language) })
    if (!mapState.show_route || places.length < 2) return
    void ensureSession().then((session) => planOrderedRoute(
      getOrCreateConversationId(session),
      places,
      mapState.route_mode || undefined,
      mapState.route_strategy || undefined,
    )).then((result) => setRoute(result.route || null))
      .catch((reason) => setRouteError(String((reason as Error)?.message || reason)))
  }, [])

  const markers = useMemo(() => places.map((place, index) => ({
    id: index + 1,
    iconPath: apiUrl('/floris-avatar.png'),
    width: 32,
    height: 32,
    latitude: Number(place.latitude),
    longitude: Number(place.longitude),
    title: `${index + 1}. ${place.name || translate('place', {}, language)}`,
    callout: {
      content: `${index + 1}. ${place.name || translate('place', {}, language)}`,
      display: 'ALWAYS' as const,
      padding: 6,
      borderRadius: 8,
      borderWidth: 1,
      borderColor: '#efd8c6',
      color: '#70442c',
      bgColor: '#fff8ef',
      fontSize: 12,
      anchorX: 0,
      anchorY: 0,
      textAlign: 'center' as const,
    },
  })), [places, language])
  const polyline = route?.path?.length
    ? [{
      points: route.path,
      color: '#e98140',
      width: 6,
      borderColor: '#ffffff',
      borderWidth: 2,
      arrowLine: true,
    }]
    : []

  const moveToCurrentLocation = async () => {
    if (locating) return
    setLocating(true)
    try {
      const result = await requestCurrentLocation()
      if (result.location) {
        Taro.createMapContext('floris-map').moveToLocation({
          latitude: result.location.latitude,
          longitude: result.location.longitude,
        })
        return
      }
      if (result.request.state === 'denied') {
        const answer = await Taro.showModal({
          title: translate('locationPermissionTitle', {}, language),
          content: translate('locationPermissionBody', {}, language),
          confirmText: translate('openSettings', {}, language),
          cancelText: translate('cancel', {}, language),
        })
        if (answer.confirm) await Taro.openSetting()
        return
      }
      void Taro.showToast({ title: translate('locationUnavailable', {}, language), icon: 'none' })
    } finally {
      setLocating(false)
    }
  }

  return <View className='map-page'>
    <View className='map-stage'>
      <Map
        id='floris-map'
        className='native-map'
        latitude={Number(center.latitude)}
        longitude={Number(center.longitude)}
        scale={12}
        markers={markers}
        includePoints={places}
        polyline={polyline}
        showLocation
        enableTraffic
        onError={() => undefined}
      />
      <Button className='locate-button' loading={locating}
        aria-label={translate('showMyLocation', {}, language)}
        onClick={() => void moveToCurrentLocation()}>
        <Text>⌖</Text>
        <Text>{translate(locating ? 'locating' : 'showMyLocation', {}, language)}</Text>
      </Button>
    </View>
    <View className='map-sheet'>
      <View className='map-sheet-handle' />
      <Text className='map-title'>{mapState.title || translate('relatedPlaces', {}, language)}</Text>
      {route ? <Text className='route-summary'>{translate('routeSummary', {
        distance: (Number(route.distance_meters || 0) / 1000).toFixed(1),
        minutes: Math.round(Number(route.duration_seconds || 0) / 60),
      }, language)}</Text> : null}
      {routeError ? <Text className='route-error'>{routeError}</Text> : null}
      {places.map((place, index) => <View className='place-row' key={place.place_id || `${place.latitude}-${place.longitude}`}>
        <Text className='place-index'>{index + 1}</Text>
        <View><Text className='place-name'>{place.name}</Text><Text className='place-address'>{place.address}</Text></View>
      </View>)}
    </View>
  </View>
}

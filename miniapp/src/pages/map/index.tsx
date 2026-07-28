import { useEffect, useMemo, useState } from 'react'
import Taro from '@tarojs/taro'
import { Map, Text, View } from '@tarojs/components'
import { getOrCreateConversationId } from '@/services/conversations'
import {
  planOrderedRoute,
  type PlannedRoute,
  type RoutePlace,
} from '@/services/routes'
import { ensureSession } from '@/services/session'
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
  const places = mapState.places || []
  const center = places[0] || { latitude: 39.9042, longitude: 116.4074 }

  useEffect(() => {
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
    iconPath: 'https://floris.jlutx.com/floris-avatar.png',
    width: 32,
    height: 32,
    latitude: Number(place.latitude),
    longitude: Number(place.longitude),
    title: `${index + 1}. ${place.name || '地点'}`,
    callout: {
      content: `${index + 1}. ${place.name || '地点'}`,
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
  })), [places])
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

  return <View className='map-page'>
    <Map
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
    <View className='map-sheet'>
      <Text className='map-title'>{mapState.title || '相关地点'}</Text>
      {route ? <Text className='route-summary'>约 {(Number(route.distance_meters || 0) / 1000).toFixed(1)} 公里 · {Math.round(Number(route.duration_seconds || 0) / 60)} 分钟</Text> : null}
      {routeError ? <Text className='route-error'>{routeError}</Text> : null}
      {places.map((place, index) => <View className='place-row' key={place.place_id || `${place.latitude}-${place.longitude}`}>
        <Text className='place-index'>{index + 1}</Text>
        <View><Text className='place-name'>{place.name}</Text><Text className='place-address'>{place.address}</Text></View>
      </View>)}
    </View>
  </View>
}

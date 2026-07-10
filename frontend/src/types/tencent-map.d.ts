interface TencentMapInstance {
  destroy?: () => void;
}

interface TencentMapNamespace {
  Map: new (container: HTMLElement, options: Record<string, unknown>) => TencentMapInstance;
  LatLng: new (lat: number, lng: number) => unknown;
  MultiMarker: new (options: Record<string, unknown>) => unknown;
  MarkerStyle: new (options: Record<string, unknown>) => unknown;
  MultiPolyline: new (options: Record<string, unknown>) => unknown;
  PolylineStyle: new (options: Record<string, unknown>) => unknown;
  MultiLabel: new (options: Record<string, unknown>) => unknown;
  LabelStyle: new (options: Record<string, unknown>) => unknown;
}

interface Window {
  TMap?: TencentMapNamespace;
}

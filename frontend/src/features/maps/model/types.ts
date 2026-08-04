/** Provider-verified location and route contracts rendered by every client. */
export interface MakersMapPlace {
  schema_version?: number;
  place_id: string;
  provider?: string;
  name: string;
  address: string;
  latitude: number;
  longitude: number;
  city?: string;
  category?: string;
}

export type MakersRouteMode = 'driving' | 'transit' | 'walking' | 'bicycling';
export type MakersRouteStrategy = 'time_then_cost' | 'least_time' | 'least_cost';
export type MakersRouteSectionMode = MakersRouteMode | 'bus' | 'rail';

export interface MakersRouteSection {
  mode: MakersRouteSectionMode;
  path: Array<{ latitude: number; longitude: number }>;
  distance_meters: number;
  duration_seconds: number;
  line?: string;
  vehicle?: string;
  geton?: string;
  getoff?: string;
  station_count?: number;
  instruction?: string;
}

export interface MakersRouteLeg {
  from: MakersMapPlace;
  to: MakersMapPlace;
  scope?: 'intercity' | 'local' | 'unknown';
  mode: MakersRouteMode;
  path: Array<{ latitude: number; longitude: number }>;
  sections: MakersRouteSection[];
  distance_meters: number;
  duration_seconds: number;
}

export interface MakersRoutePlan {
  schema_version: number;
  provider: string;
  mode: MakersRouteMode;
  places: MakersMapPlace[];
  path: Array<{ latitude: number; longitude: number }>;
  legs?: MakersRouteLeg[];
  distance_meters: number;
  duration_seconds: number;
  fare: {
    currency: string;
    basis: string;
    self_driving?: { estimate: number; toll: number };
    taxi?: { low: number; high: number };
    transit?: { estimate: number; provider_estimate?: boolean };
  };
  transit?: {
    coverage?: 'bus_metro';
    walking_distance_meters?: number;
    lines?: string[];
    transfer_count?: number;
  };
  cache?: { hit: boolean; expires_at: number };
}

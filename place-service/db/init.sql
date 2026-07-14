CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS places (
  id text PRIMARY KEY,
  name text NOT NULL,
  name_zh text NOT NULL DEFAULT '',
  name_en text NOT NULL DEFAULT '',
  aliases text NOT NULL DEFAULT '',
  city text NOT NULL DEFAULT '',
  country_code text NOT NULL DEFAULT '',
  category text NOT NULL DEFAULT 'other',
  address text NOT NULL DEFAULT '',
  phone text NOT NULL DEFAULT '',
  rating double precision NOT NULL DEFAULT 0,
  importance double precision NOT NULL DEFAULT 0,
  source text NOT NULL,
  source_region text NOT NULL DEFAULT '',
  import_run_id uuid,
  source_updated_at timestamptz,
  geom geometry(Point, 4326) NOT NULL
);

CREATE INDEX IF NOT EXISTS places_geom_gix ON places USING gist (geom);
CREATE INDEX IF NOT EXISTS places_name_trgm ON places USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_name_zh_trgm ON places USING gin (name_zh gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_name_en_trgm ON places USING gin (name_en gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_aliases_trgm ON places USING gin (aliases gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_city_category_idx ON places (city, category);
CREATE INDEX IF NOT EXISTS places_importance_idx ON places (importance DESC);
CREATE INDEX IF NOT EXISTS places_source_region_idx ON places (source, source_region);

CREATE OR REPLACE VIEW place_api_stats AS
SELECT country_code, category, count(*) AS place_count
FROM places
GROUP BY country_code, category;

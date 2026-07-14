BEGIN;

ALTER TABLE places ADD COLUMN IF NOT EXISTS aliases text NOT NULL DEFAULT '';
ALTER TABLE places ADD COLUMN IF NOT EXISTS source_region text NOT NULL DEFAULT '';
ALTER TABLE places ADD COLUMN IF NOT EXISTS import_run_id uuid;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'places' AND column_name = 'tags'
  ) THEN
    UPDATE places
    SET aliases = left(concat_ws(' ',
      NULLIF(tags->>'alt_name', ''),
      NULLIF(tags->>'official_name', ''),
      NULLIF(tags->>'short_name', ''),
      NULLIF(tags->>'old_name', '')
    ), 1000)
    WHERE aliases = '';
    ALTER TABLE places DROP COLUMN tags;
  END IF;
END $$;

-- Commercial POIs are deliberately delegated to Tencent WebService.  Remove
-- legacy OSM rows from the earlier broad importer before the compact refresh.
DELETE FROM places
WHERE source = 'openstreetmap' AND category IN ('restaurant', 'hotel', 'shopping');

CREATE INDEX IF NOT EXISTS places_aliases_trgm ON places USING gin (aliases gin_trgm_ops);
CREATE INDEX IF NOT EXISTS places_source_region_idx ON places (source, source_region);

COMMIT;

ANALYZE places;

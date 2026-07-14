import sys
import unittest
from pathlib import Path


IMPORTER = Path(__file__).resolve().parents[1] / "importer"
sys.path.insert(0, str(IMPORTER))

from import_china_regions import ALLOWED_REGIONS, DEFAULT_REGIONS  # noqa: E402
from place_rules import category_for, compact_aliases, is_place  # noqa: E402


class CompactPlaceRulesTests(unittest.TestCase):
    def test_keeps_stable_attractions_transport_and_settlements(self):
        self.assertTrue(is_place({"name": "西湖", "tourism": "attraction"}))
        self.assertTrue(is_place({"name": "杭州东站", "railway": "station"}))
        self.assertTrue(is_place({"name": "某镇", "place": "town"}))
        self.assertTrue(is_place({"name": "某社区", "place": "neighbourhood"}))
        self.assertTrue(is_place({"name": "某岛", "natural": "island"}))
        self.assertTrue(is_place({"name": "某灯塔", "man_made": "lighthouse"}))

    def test_drops_dynamic_commercial_pois(self):
        self.assertFalse(is_place({"name": "某餐厅", "amenity": "restaurant"}))
        self.assertFalse(is_place({"name": "某酒店", "tourism": "hotel"}))
        self.assertEqual(category_for({"shop": "mall"}), "other")

    def test_aliases_are_compact_and_deduplicated(self):
        aliases = compact_aliases({"alt_name": "West Lake;西湖", "old_name": "West Lake"})
        self.assertEqual(aliases, "West Lake 西湖")

    def test_default_regions_avoid_known_overlaps(self):
        self.assertIn("hebei", DEFAULT_REGIONS)
        self.assertNotIn("beijing", DEFAULT_REGIONS)
        self.assertNotIn("tianjin", DEFAULT_REGIONS)
        self.assertTrue(set(DEFAULT_REGIONS) <= ALLOWED_REGIONS)


if __name__ == "__main__":
    unittest.main()

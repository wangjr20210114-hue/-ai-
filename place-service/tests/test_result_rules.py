import sys
import unittest
from pathlib import Path


SERVICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE))

from app.result_rules import deduplicate_nearby_names, rank_and_deduplicate  # noqa: E402


class ResultRulesTests(unittest.TestCase):
    def test_collapses_same_name_node_and_way_nearby(self):
        rows = [
            {"id": "way", "name": "五公祠", "lat": 20.00956, "lng": 110.35536},
            {"id": "node", "name": "五公祠", "lat": 20.01010, "lng": 110.35526},
        ]
        self.assertEqual(["way"], [row["id"] for row in deduplicate_nearby_names(rows, 5)])

    def test_keeps_same_name_places_far_apart_and_honors_limit(self):
        rows = [
            {"id": "one", "name": "人民公园", "lat": 20.0, "lng": 110.0},
            {"id": "two", "name": "人民公园", "lat": 21.0, "lng": 111.0},
            {"id": "three", "name": "西湖", "lat": 30.0, "lng": 120.0},
        ]
        self.assertEqual(["one", "two"], [row["id"] for row in deduplicate_nearby_names(rows, 2)])

    def test_merged_ranking_prefers_exact_high_confidence_match(self):
        rows = [
            {"id": "near", "name": "西湖山", "lat": 30.1, "lng": 120.0,
             "importance": 0.8, "source": "openstreetmap"},
            {"id": "exact", "name": "西湖", "lat": 30.2, "lng": 120.1,
             "importance": 0.95, "source": "overture_places"},
        ]
        self.assertEqual("exact", rank_and_deduplicate(rows, "西湖", 2)[0]["id"])


if __name__ == "__main__":
    unittest.main()

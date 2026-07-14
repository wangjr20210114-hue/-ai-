"""Pure filtering and compaction rules shared by the low-disk importers."""
from __future__ import annotations


# Commercial POIs change quickly and are supplied by Tencent WebService.  The
# private OSM layer intentionally keeps only stable attractions, settlements,
# and transport hubs.
CATEGORY_TAGS = {
    "transport": {
        "amenity": {"bus_station", "ferry_terminal"},
        "railway": {"station", "halt", "tram_stop"},
        "aeroway": {"aerodrome", "terminal"},
    },
    "attraction": {
        "tourism": {
            "aquarium", "artwork", "attraction", "camp_site", "gallery", "museum",
            "picnic_site", "theme_park", "viewpoint", "zoo",
        },
        "historic": {"*"},
        "leisure": {"garden", "nature_reserve", "park", "sports_centre", "stadium"},
        "natural": {
            "bay", "beach", "cape", "cave_entrance", "glacier", "hot_spring", "island",
            "peak", "ridge", "saddle", "spring", "valley", "volcano", "waterfall",
        },
        "man_made": {"lighthouse", "observatory", "tower"},
    },
}

SETTLEMENTS = {
    "borough", "city", "hamlet", "isolated_dwelling", "locality", "neighbourhood",
    "quarter", "suburb", "town", "village",
}
ALIAS_KEYS = ("alt_name", "official_name", "short_name", "old_name", "loc_name")


def category_for(tags: dict[str, str]) -> str:
    for category, selectors in CATEGORY_TAGS.items():
        for key, accepted in selectors.items():
            value = tags.get(key, "")
            if value and ("*" in accepted or value in accepted):
                return category
    return "other"


def is_place(tags: dict[str, str]) -> bool:
    named = tags.get("name") or tags.get("name:zh") or tags.get("name:en")
    return bool(named) and (category_for(tags) != "other" or tags.get("place") in SETTLEMENTS)


def compact_aliases(tags: dict[str, str], max_length: int = 1000) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for key in ALIAS_KEYS:
        for value in tags.get(key, "").replace(";", "|").split("|"):
            normalized = value.strip()
            folded = normalized.casefold()
            if normalized and folded not in seen:
                values.append(normalized)
                seen.add(folded)
    return " ".join(values)[:max_length]


def importance(tags: dict[str, str]) -> float:
    score = 0.05 + (0.45 if tags.get("wikipedia") else 0) + (0.3 if tags.get("wikidata") else 0)
    score += 0.15 if tags.get("heritage") else 0
    try:
        score += min(int(tags.get("population", "0").replace(",", "")) / 10_000_000, 0.5)
    except ValueError:
        pass
    return min(score, 1.0)

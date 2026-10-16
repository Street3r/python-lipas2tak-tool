"""Synthetic Nuuksio test data mimicking the Lipas data structure.

Coordinates and names are approximate and NOT real data. The structure
(field names, nesting) is taken from Lipas v2 API responses.
Run: python tests/fixtures/make_nuuksio.py  -> tests/fixtures/nuuksio/*.json
"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "nuuksio"


def pt(lon, lat):
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}}]}


def site(lid, type_code, name, lon, lat, props=None, comment="", admin="state", city=49, **kw):
    s = {"lipas-id": lid, "type": {"type-code": type_code}, "name": name, "status": "active",
         "admin": admin, "owner": "state", "comment": comment, "properties": props or {},
         "event-date": "2026-09-01T10:00:00Z",
         "location": {"city": {"city-code": city}, "geometries": pt(lon, lat)}}
    s.update(kw)
    return s


def line(coords, fid=None):
    f = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords}}
    if fid:
        f["id"] = fid
    return f


sites = [
    site(900001, 301, "Haukkalammen laavu", 24.5052, 60.3082, {"toilet?": True, "water-point": "seasonal"},
         "Laavu Haukkalammen rannalla. Puuvaja vieressä."),
    site(900002, 301, "Mustalammen kota", 24.4890, 60.3170, {}, "Tulisija kodan sisällä."),
    site(900003, 206, "Haukkalammen nuotiopaikka", 24.5060, 60.3075, {"toilet?": True}),
    site(900004, 206, "Iso-Holman keittokatos", 24.4700, 60.3230, {}),
    site(900005, 204, "Kattilajärven lintutorni", 24.5600, 60.2960, {}, name_localized=None),
    site(900006, 202, "Mustalammen telttailualue", 24.4880, 60.3160, {"toilet?": True}),
    site(900007, 207, "Haukkalammen opastuspiste", 24.5040, 60.3090, {"parking-place?": True, "toilet?": True},
         www="https://www.luontoon.fi/nuuksio"),
    site(900008, 301, "Testilaavu", 24.5000, 60.3000, {}),  # filtered out by name
    site(900009, 301, "Aulangon laavu", 24.4600, 61.0100, {}, admin="city-sports", city=109),
    site(900010, 302, "Kaitalammen tupa", 24.4950, 60.2950, {}, status="out-of-service-temporarily"),
]
for s in sites:
    s.pop("name_localized", None)
sites[1]["name-localized"] = {"se": "Mustalammens kåta", "en": "Mustalampi hut"}

# Route in two pieces + elevation (Z), Luontoon.fi enrichment in the activities field
hauk1 = [[24.5040, 60.3090, 40.0], [24.5000, 60.3110, 42.0], [24.4950, 60.3120, 44.0], [24.4920, 60.3140, 46.1]]
hauk2 = [[24.4920, 60.3140, 46.1], [24.4950, 60.3160, 45.0], [24.5010, 60.3150, 43.0], [24.5040, 60.3090, 40.0]]
sites.append({
    "lipas-id": 900020, "type": {"type-code": 4404}, "name": "Haukankierros", "status": "active",
    "admin": "state", "owner": "state", "comment": "", "www": "https://www.luontoon.fi/nuuksio/reitit",
    "properties": {"route-length-km": 4.2, "surface-material": ["soil"]},
    "event-date": "2026-09-01T10:00:00Z",
    "location": {"city": {"city-code": 49},
                 "geometries": {"type": "FeatureCollection",
                                "features": [line(hauk1, "f-1"), line(hauk2, "f-2")]}},
    "activities": {"outdoor-recreation-routes": {"routes": [{
        "id": "1b9c2c4e-0000-4000-8000-000000000020",
        "fids": ["f-1", "f-2"],
        "route-name": {"fi": "Haukankierros", "en": "Haukankierros trail"},
        "description-short": {"fi": "Vaativa kierros Haukkalammen ympäristön kallioilla.",
                              "en": "Demanding loop on the rocky hills around Haukkalampi."},
        "route-marking": {"fi": "Punaiset merkit", "en": "Red markers"},
        "accessibility-classification": "inaccessible",
        "travel-direction": "no-preference",
    }]}},
})
korppi = [[24.5040, 60.3090], [24.5100, 60.3150], [24.5200, 60.3200], [24.5300, 60.3150],
          [24.5250, 60.3080], [24.5040, 60.3090]]
sites.append({
    "lipas-id": 900021, "type": {"type-code": 4405}, "name": "Korpinkierros", "status": "active",
    "admin": "state", "owner": "state", "comment": "Pidempi retkeilyreitti järvimaisemissa.",
    "properties": {}, "event-date": "2026-09-01T10:00:00Z",
    "location": {"city": {"city-code": 49},
                 "geometries": {"type": "FeatureCollection", "features": [line(korppi)]}},
})

# Official snowmobile route: only in the nationwide route type layer, not in area packages
sites.append({
    "lipas-id": 900022, "type": {"type-code": 4421}, "name": "Nuuksion moottorikelkkareitti", "status": "active",
    "admin": "city-sports", "owner": "city", "comment": "",
    "properties": {"route-length-km": 6.0}, "event-date": "2026-09-01T10:00:00Z",
    "location": {"city": {"city-code": 49},
                 "geometries": {"type": "FeatureCollection",
                                "features": [line([[24.4800, 60.3000], [24.5000, 60.3050], [24.5300, 60.3000]])]}},
})

sites.append({
    "lipas-id": 900023, "type": {"type-code": 4422}, "name": "Nuuksion kelkkaura", "status": "active",
    "admin": "private-association", "owner": "registered-association", "comment": "",
    "properties": {"route-length-km": 3.0}, "event-date": "2026-09-01T10:00:00Z",
    "location": {"city": {"city-code": 49},
                 "geometries": {"type": "FeatureCollection",
                                "features": [line([[24.5300, 60.3000], [24.5400, 60.2950], [24.5500, 60.2900]])]}},
})

lois = [
    {"id": "aaaaaaaa-0000-4000-8000-000000000001", "loi-type": "dry-toilet", "loi-category": "outdoor-recreation-facilities",
     "name": {"fi": "Haukkalammen kuivakäymälä"}, "status": "active", "event-date": "2026-09-01T10:00:00Z",
     "geometries": pt(24.5055, 60.3085)},
    {"id": "aaaaaaaa-0000-4000-8000-000000000002", "loi-type": "woodshed", "loi-category": "outdoor-recreation-facilities",
     "name": {"fi": "Haukkalammen puuvaja"}, "status": "active", "event-date": "2026-09-01T10:00:00Z",
     "geometries": pt(24.5050, 60.3079)},
    {"id": "aaaaaaaa-0000-4000-8000-000000000003", "loi-type": "dry-toilet", "loi-category": "outdoor-recreation-facilities",
     "name": {"fi": "UTP-testikohde kuivakäymälä"}, "status": "active", "event-date": "2026-09-01T10:00:00Z",
     "geometries": pt(24.5100, 60.3100)},
]

osm = {"laavu": [
    {"type": "node", "id": 3001, "lat": 60.30850, "lon": 24.50600, "tags": {"amenity": "shelter", "shelter_type": "lean_to", "name": "Haukkalammen laavu"}},  # already in Lipas
    {"type": "node", "id": 3002, "lat": 60.3135, "lon": 24.4935, "tags": {"amenity": "shelter", "shelter_type": "lean_to", "name": "Kolmoislammen laavu"}},  # new, along the route
    {"type": "node", "id": 3003, "lat": 60.5000, "lon": 25.5000, "tags": {"amenity": "shelter", "shelter_type": "lean_to"}},  # far from everything
], "kaymala": [
    {"type": "node", "id": 1001, "lat": 60.30852, "lon": 24.50555, "tags": {"amenity": "toilets"}},  # duplicate
    {"type": "node", "id": 1002, "lat": 60.3172, "lon": 24.4870, "tags": {"amenity": "toilets", "name": "Mustalammen huussi"}},
    {"type": "way", "id": 2001, "center": {"lat": 60.1699, "lon": 24.9384}, "tags": {"amenity": "toilets"}},  # Helsinki
]}

park = [[24.40, 60.27], [24.62, 60.27], [24.62, 60.36], [24.40, 60.36], [24.40, 60.27]]
area_sites = {"kansallispuistot": [{
    "lipas-id": 606198, "type": {"type-code": 111}, "name": "Nuuksion kansallispuisto", "status": "active",
    "name-localized": {"en": "Nuuksio National Park"},
    "location": {"city": {"city-code": 49}, "geometries": {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [park]}}]}},
}]}

regions = [
    {"type": "Feature", "properties": {"maakunta": "01", "nimi": "Uusimaa", "name": "Uusimaa"},
     "geometry": {"type": "Polygon", "coordinates": [[[22.8, 59.8], [26.5, 59.8], [26.5, 60.85], [22.8, 60.85], [22.8, 59.8]]]}},
    {"type": "Feature", "properties": {"maakunta": "05", "nimi": "Kanta-Häme", "name": "Kanta-Häme"},
     # deliberately in lat/lon order: tests the axis-order fix
     "geometry": {"type": "Polygon", "coordinates": [[[60.85, 23.5], [60.85, 25.2], [61.3, 25.2], [61.3, 23.5], [60.85, 23.5]]]}},
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, data in [("sites", sites), ("lois", lois), ("osm", osm), ("area_sites", area_sites), ("regions", regions)]:
        (OUT / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()

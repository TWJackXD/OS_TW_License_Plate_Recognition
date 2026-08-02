#!/usr/bin/env python3
"""Campus-scoped location resolution via OSM.

1. Point must fall inside configured campus polygon(s) (e.g. 國立高雄科技大學第一校區).
2. Inside campus, pick the nearest named landmark and format as「管理學院附近 (lat, lon)」.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
CUSTOM_LANDMARKS_PATH = ROOT / "data" / "campus_buildings.geojson"

OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
OVERPASS_MIRRORS = [
    OVERPASS_URL,
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
NOMINATIM_LOOKUP_URL = os.environ.get(
    "NOMINATIM_LOOKUP_URL", "https://nominatim.openstreetmap.org/lookup"
)
USER_AGENT = os.environ.get(
    "OSM_USER_AGENT", "NKUST-PlatePermit/1.0 (campus-parking; local-dev)"
)

# Default NKUST campuses (Nominatim / OSM)
DEFAULT_CAMPUS_OSM_IDS = ",".join(
    [
        "relation/7242146",  # 第一校區
        "relation/7961309",  # 建工校區
        "relation/6842066",  # 楠梓校區
        "relation/7267075",  # 燕巢校區
        "relation/7961310",  # 旗津校區
        "way/237921751",  # 東方校區
    ]
)

_campus_cache: dict[str, Any] | None = None
_campus_cache_at = 0.0
_landmark_cache: dict[str, list[dict[str, Any]]] = {}
_landmark_cache_at: dict[str, float] = {}


@dataclass
class LocationResult:
    ok: bool
    location_name: str | None = None
    campus_name: str | None = None
    landmark_name: str | None = None
    distance_m: float | None = None
    error: str | None = None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def campus_enforce_enabled() -> bool:
    raw = os.environ.get("CAMPUS_ENFORCE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def configured_campus_ids() -> list[tuple[str, int]]:
    raw = os.environ.get("CAMPUS_OSM_IDS", DEFAULT_CAMPUS_OSM_IDS)
    out: list[tuple[str, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            kind, _, sid = part.partition("/")
        elif part.isdigit():
            kind, sid = "relation", part
        else:
            continue
        kind = kind.strip().lower()
        if kind not in {"relation", "way"}:
            continue
        try:
            out.append((kind, int(sid)))
        except ValueError:
            continue
    return out or [("relation", 7242146)]


def _http_json(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 40.0,
) -> Any:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _overpass(query: str, timeout: float = 45.0) -> dict[str, Any]:
    last_err: Exception | None = None
    mirrors = []
    for url in OVERPASS_MIRRORS:
        if url and url not in mirrors:
            mirrors.append(url)
    for url in mirrors:
        try:
            return _http_json(
                url,
                data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=timeout,
            )
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"Overpass 查詢失敗：{last_err}")


def _nominatim_campus_polygons(kind: str, oid: int) -> tuple[str, list[list[list[float]]]]:
    """Fetch campus multipolygon via Nominatim (more reliable than Overpass for boundaries)."""
    prefix = "R" if kind == "relation" else "W"
    qs = urllib.parse.urlencode(
        {
            "osm_ids": f"{prefix}{oid}",
            "format": "geojson",
            "polygon_geojson": 1,
        }
    )
    data = _http_json(f"{NOMINATIM_LOOKUP_URL}?{qs}", timeout=30.0)
    features = data.get("features") or []
    if not features:
        raise RuntimeError(f"Nominatim 找不到 {kind}/{oid}")
    feat = features[0]
    props = feat.get("properties") or {}
    name = props.get("name") or (props.get("display_name") or "").split(",")[0].strip()
    geom = feat.get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    polys: list[list[list[float]]] = []
    if gtype == "Polygon":
        polys = [coords]
    elif gtype == "MultiPolygon":
        polys = list(coords)
    else:
        raise RuntimeError(f"校區幾何類型不支援：{gtype}")
    return name or f"{kind}/{oid}", polys


# Local corrections for known OSM naming errors (NKUST etc.).
_LANDMARK_NAME_FIXES: dict[str, str] = {
    "財經學院": "財金學院",
}


def _correct_landmark_name(name: str | None) -> str | None:
    if not name:
        return name
    text = name.strip()
    if not text:
        return None
    fixed = _LANDMARK_NAME_FIXES.get(text)
    if fixed:
        return fixed
    # Also fix when the wrong token appears inside a longer label.
    for wrong, right in _LANDMARK_NAME_FIXES.items():
        if wrong in text:
            text = text.replace(wrong, right)
    return text


def _pick_name(tags: dict[str, Any] | None) -> str | None:
    if not tags:
        return None
    for key in ("name:zh", "name:zh-Hant", "name:zh-Hans", "name", "official_name", "ref"):
        val = tags.get(key)
        if isinstance(val, str) and val.strip():
            return _correct_landmark_name(val.strip())
    return None


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = float(ring[i][0]), float(ring[i][1])
        xj, yj = float(ring[j][0]), float(ring[j][1])
        intersect = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-16) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _point_in_polygon(lon: float, lat: float, coords: list) -> bool:
    if not coords:
        return False
    if not _point_in_ring(lon, lat, coords[0]):
        return False
    for hole in coords[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _rings_from_relation_geom(el: dict[str, Any]) -> list[list[list[float]]]:
    """Convert Overpass `out geom` relation to list of polygon rings (lon,lat)."""
    members = el.get("members") or []
    outers: list[list[list[float]]] = []
    inners: list[list[list[float]]] = []
    for m in members:
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        ring = [[float(p["lon"]), float(p["lat"])] for p in m["geometry"]]
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        role = m.get("role") or "outer"
        if role == "inner":
            inners.append(ring)
        else:
            outers.append(ring)
    # Approximate multipolygon: each outer + all inners (good enough for campus)
    polys: list[list[list[float]]] = []
    for outer in outers:
        polys.append([outer, *inners])
    return polys


def _bbox_of_polygons(polys: list[list[list[float]]]) -> tuple[float, float, float, float]:
    lats: list[float] = []
    lons: list[float] = []
    for poly in polys:
        for ring in poly:
            for lon, lat in ring:
                lats.append(float(lat))
                lons.append(float(lon))
    return min(lats), min(lons), max(lats), max(lons)


def _load_campus_bundle(force: bool = False) -> dict[str, Any]:
    """Load/cached campus polygons + names for configured OSM ids."""
    global _campus_cache, _campus_cache_at
    ttl = _env_float("CAMPUS_CACHE_SECONDS", 86400.0)
    if (
        not force
        and _campus_cache is not None
        and (time.time() - _campus_cache_at) < ttl
    ):
        return _campus_cache

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    campuses: list[dict[str, Any]] = []

    for kind, oid in configured_campus_ids():
        cache_file = CACHE_DIR / f"campus_{kind}_{oid}.json"
        cached = None
        if cache_file.is_file() and not force:
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                cached = None

        if cached and cached.get("polygons"):
            campuses.append(cached)
            continue

        name, polys = _nominatim_campus_polygons(kind, oid)
        entry = {
            "id": f"{kind}/{oid}",
            "name": name,
            "polygons": polys,
        }
        cache_file.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        campuses.append(entry)
        # Nominatim usage policy: max ~1 req/sec
        time.sleep(1.05)

    _campus_cache = {"campuses": campuses}
    _campus_cache_at = time.time()
    return _campus_cache


def find_campus(lat: float, lon: float) -> dict[str, Any] | None:
    bundle = _load_campus_bundle()
    for campus in bundle["campuses"]:
        for poly in campus["polygons"]:
            if _point_in_polygon(lon, lat, poly):
                return campus
    return None


def _custom_landmarks() -> list[dict[str, Any]]:
    path = Path(os.environ.get("CAMPUS_BUILDINGS_GEOJSON", str(CUSTOM_LANDMARKS_PATH)))
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for feat in data.get("features") or []:
        props = feat.get("properties") or {}
        name = props.get("name") or props.get("name:zh")
        geom = feat.get("geometry") or {}
        if not name or not geom:
            continue
        # centroid of outer ring / point
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        clat = clon = None
        if gtype == "Point":
            clon, clat = float(coords[0]), float(coords[1])
        elif gtype == "Polygon" and coords and coords[0]:
            ring = coords[0]
            clon = sum(p[0] for p in ring) / len(ring)
            clat = sum(p[1] for p in ring) / len(ring)
        if clat is None:
            continue
        corrected = _correct_landmark_name(str(name).strip())
        if not corrected:
            continue
        out.append({"name": corrected, "lat": clat, "lon": clon, "source": "custom"})
    return out


def _load_osm_landmarks(campus: dict[str, Any], force: bool = False) -> list[dict[str, Any]]:
    cid = campus["id"]
    ttl = _env_float("LANDMARK_CACHE_SECONDS", 86400.0)
    if (
        not force
        and cid in _landmark_cache
        and (time.time() - _landmark_cache_at.get(cid, 0)) < ttl
    ):
        return _landmark_cache[cid]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    kind, _, sid = cid.partition("/")
    cache_file = CACHE_DIR / f"landmarks_{kind}_{sid}.json"
    landmarks: list[dict[str, Any]] = []

    if cache_file.is_file() and not force:
        try:
            landmarks = json.loads(cache_file.read_text(encoding="utf-8"))
            for item in landmarks:
                if isinstance(item, dict) and item.get("name"):
                    item["name"] = _correct_landmark_name(str(item["name"]))
        except Exception:
            landmarks = []

    if not landmarks:
        south, west, north, east = _bbox_of_polygons(campus["polygons"])
        # Slight pad
        pad = 0.001
        south, west, north, east = south - pad, west - pad, north + pad, east + pad
        query = f"""
        [out:json][timeout:60];
        (
          way({south},{west},{north},{east})[building][name];
          way({south},{west},{north},{east})[amenity][name];
          way({south},{west},{north},{east})[tourism][name];
          way({south},{west},{north},{east})[leisure][name];
          node({south},{west},{north},{east})[amenity][name];
          node({south},{west},{north},{east})[tourism][name];
          way({south},{west},{north},{east})[name~"學院|大樓|中心|館|場|堂|宿舍|行政"];
          node({south},{west},{north},{east})[name~"學院|大樓|中心|館|場|堂|宿舍|行政"];
        );
        out center tags;
        """
        try:
            data = _overpass(query, timeout=70.0)
            campus_name = campus.get("name") or ""
            for el in data.get("elements") or []:
                tags = el.get("tags") or {}
                name = _pick_name(tags)
                if not name:
                    continue
                if campus_name and name == campus_name:
                    continue
                if re.search(r"校區$|Campus$", name):
                    continue
                center = el.get("center")
                if not center and el.get("type") == "node":
                    center = {"lat": el.get("lat"), "lon": el.get("lon")}
                if not center or center.get("lat") is None or center.get("lon") is None:
                    continue
                clat, clon = float(center["lat"]), float(center["lon"])
                if not any(_point_in_polygon(clon, clat, poly) for poly in campus["polygons"]):
                    continue
                landmarks.append(
                    {
                        "name": name,
                        "lat": clat,
                        "lon": clon,
                        "source": "osm",
                        "osm_type": el.get("type"),
                        "osm_id": el.get("id"),
                    }
                )
            cache_file.write_text(json.dumps(landmarks, ensure_ascii=False), encoding="utf-8")
        except Exception:
            landmarks = landmarks or []

    _landmark_cache[cid] = landmarks
    _landmark_cache_at[cid] = time.time()
    return landmarks


def nearest_landmark(
    lat: float, lon: float, campus: dict[str, Any]
) -> tuple[str | None, float | None]:
    radius = _env_float("LANDMARK_SEARCH_RADIUS_M", 180.0)
    candidates = list(_custom_landmarks()) + list(_load_osm_landmarks(campus))
    best_name = None
    best_d = None
    for item in candidates:
        # Prefer landmarks that are also inside campus (custom may be approximate)
        if campus["polygons"]:
            inside = any(
                _point_in_polygon(item["lon"], item["lat"], poly) for poly in campus["polygons"]
            )
            if not inside and item.get("source") == "osm":
                continue
        d = _haversine_m(lat, lon, item["lat"], item["lon"])
        if d > radius:
            continue
        if best_d is None or d < best_d:
            best_d = d
            best_name = item["name"]
    return best_name, best_d


def format_location_label(
    landmark: str | None,
    lat: float,
    lon: float,
    campus_name: str | None = None,
) -> str:
    coord = f"{lat:.5f}, {lon:.5f}"
    if landmark:
        return f"{landmark}附近 ({coord})"
    if campus_name:
        return f"{campus_name}內 ({coord})"
    return f"校區範圍內 ({coord})"


def resolve_campus_location(lat: float | None, lon: float | None) -> LocationResult:
    if lat is None or lon is None:
        return LocationResult(
            ok=False,
            error="缺少 GPS 座標，無法確認是否位於校區內",
        )
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return LocationResult(ok=False, error="GPS 座標格式錯誤")

    try:
        campus = find_campus(lat_f, lon_f)
    except Exception as exc:
        return LocationResult(ok=False, error=f"載入校區範圍失敗：{exc}")

    if campus is None:
        return LocationResult(
            ok=False,
            error="座標不在允許的校區範圍內，無法舉發",
        )

    landmark, dist = nearest_landmark(lat_f, lon_f, campus)
    label = format_location_label(landmark, lat_f, lon_f, campus.get("name"))
    return LocationResult(
        ok=True,
        location_name=label,
        campus_name=campus.get("name"),
        landmark_name=landmark,
        distance_m=dist,
    )


# Backwards-compatible helper used by older call sites
def resolve_location_name(lat: float | None, lon: float | None) -> str | None:
    result = resolve_campus_location(lat, lon)
    return result.location_name if result.ok else None


def campus_boundaries_geojson() -> dict[str, Any]:
    bundle = _load_campus_bundle()
    features = []
    for campus in bundle["campuses"]:
        for poly in campus["polygons"]:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "name": campus["name"],
                        "id": campus["id"],
                        "kind": "campus",
                    },
                    "geometry": {"type": "Polygon", "coordinates": poly},
                }
            )
    return {"type": "FeatureCollection", "features": features}


def fetch_buildings_geojson(
    south: float, west: float, north: float, east: float
) -> dict[str, Any]:
    """Buildings/landmarks overlay for admin map (bbox), plus campus outline."""
    if abs(north - south) > 0.03 or abs(east - west) > 0.03:
        raise ValueError("查詢範圍過大，請縮小地圖再試")

    query = f"""
    [out:json][timeout:25];
    (
      way({south},{west},{north},{east})[building];
      relation({south},{west},{north},{east})[building];
    );
    out body;
    >;
    out skel qt;
    """
    data = _overpass(query, timeout=35.0)
    nodes: dict[int, tuple[float, float]] = {}
    for el in data.get("elements") or []:
        if el.get("type") == "node" and "lat" in el and "lon" in el:
            nodes[el["id"]] = (el["lon"], el["lat"])

    features = []
    for el in data.get("elements") or []:
        if el.get("type") != "way" or "nodes" not in el:
            continue
        tags = el.get("tags") or {}
        if "building" not in tags:
            continue
        ring = []
        for nid in el["nodes"]:
            pt = nodes.get(nid)
            if pt:
                ring.append([pt[0], pt[1]])
        if len(ring) < 3:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        name = _pick_name(tags) or tags.get("building") or "building"
        features.append(
            {
                "type": "Feature",
                "properties": {"name": name, "kind": "building"},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )

    # Include campus boundary always
    try:
        for feat in campus_boundaries_geojson().get("features") or []:
            features.append(feat)
    except Exception:
        pass

    return {"type": "FeatureCollection", "features": features}

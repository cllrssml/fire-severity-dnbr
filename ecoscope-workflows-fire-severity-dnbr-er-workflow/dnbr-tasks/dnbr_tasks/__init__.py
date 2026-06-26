"""
Custom tasks for the Ecoscope Platform dNBR (Differenced Normalized Burn Ratio)
fire severity workflow.

Science: Parks et al. 2018 (doi:10.3390/rs10060879) — Landsat mean compositing.
Thresholds: Key & Benson 2006 (USGS standard severity classes).
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Optional

import geopandas as gpd
import numpy as np
from pydantic import Field
from pydantic.json_schema import WithJsonSchema
from shapely.geometry import box
from wt_registry import register

# Type shims — no ecoscope imports at module level so wt-registry can import
# this package during compiler task discovery (before ecoscope is on sys.path).
# Pattern is identical to hex-tasks/__init__.py.
_GDF = Annotated[Any, WithJsonSchema({"type": "ecoscope.platform.annotations.DataFrame"})]
_GEE = Annotated[str, WithJsonSchema({"type": "string", "description": "A named Google Earth Engine connection."})]
_ER  = Annotated[str, WithJsonSchema({"type": "string", "description": "A named EarthRanger data source."})]

# ── Severity class table ─────────────────────────────────────────────────────
# Each entry: (label, dNBR_low_inclusive, dNBR_high_exclusive, rgba_uint8, hex_str)
# dNBR values use the ×1000 convention (unitless scaled NBR).
SEVERITY_CLASSES = [
    ("Enhanced Regrowth", -np.inf,  -100, [0,   102,  0,   220], "#006600"),
    ("Unburned",          -100,      100, [200, 200,  200, 200], "#C8C8C8"),
    ("Low",                100,      270, [255, 255,  0,   220], "#FFFF00"),
    ("Moderate-Low",       270,      440, [255, 165,  0,   220], "#FFA500"),
    ("Moderate-High",      440,      660, [220,  50,  0,   220], "#DC3200"),
    ("High",               660, np.inf,  [153,   0,  0,   220], "#990000"),
]

_CLASS_NAMES = [c[0] for c in SEVERITY_CLASSES]
_CLASS_HEX   = [c[4] for c in SEVERITY_CLASSES]


def _classify(dnbr_val: float):
    """Return (name, index, rgba, hex) for a dNBR value."""
    for i, (name, lo, hi, rgba, hex_) in enumerate(SEVERITY_CLASSES):
        if lo <= dnbr_val < hi:
            return name, i, rgba, hex_
    return SEVERITY_CLASSES[-1][0], len(SEVERITY_CLASSES) - 1, SEVERITY_CLASSES[-1][3], SEVERITY_CLASSES[-1][4]


# ── Cloud / NBR helpers (called inside GEE .map()) ───────────────────────────
# Each function has its own lazy `import ee` so there are no closure / scoping
# issues when these are passed as callbacks to ee.ImageCollection.map().

def _mask_clouds_l89(img):
    """Cloud + cloud-shadow mask for Landsat 8/9 Collection 2 Level-2."""
    import ee
    qa = img.select("QA_PIXEL")
    mask = (
        qa.bitwiseAnd(1 << 1).eq(0)          # dilated cloud
        .And(qa.bitwiseAnd(1 << 3).eq(0))    # cloud shadow
        .And(qa.bitwiseAnd(1 << 4).eq(0))    # cloud
    )
    return img.updateMask(mask)


def _nbr_l89(img):
    """NBR from Landsat 8/9 OLI/OLI-2: (SR_B5 − SR_B7) / (SR_B5 + SR_B7)."""
    import ee
    return img.normalizedDifference(["SR_B5", "SR_B7"]).rename("NBR")


def _mask_clouds_l57(img):
    """Cloud + cloud-shadow mask for Landsat 5/7 Collection 2 Level-2."""
    import ee
    qa = img.select("QA_PIXEL")
    mask = (
        qa.bitwiseAnd(1 << 3).eq(0)          # cloud shadow
        .And(qa.bitwiseAnd(1 << 4).eq(0))    # cloud
    )
    return img.updateMask(mask)


def _nbr_l57(img):
    """NBR from Landsat 5/7 TM/ETM+: (SR_B4 − SR_B7) / (SR_B4 + SR_B7)."""
    import ee
    return img.normalizedDifference(["SR_B4", "SR_B7"]).rename("NBR")


# ── Registered tasks ─────────────────────────────────────────────────────────

@register()
def set_fire_date(
    fire_date: Annotated[
        str,
        Field(
            title="Fire Date",
            description="Approximate start date of the fire (YYYY-MM-DD).",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
) -> str:
    """Pass the fire date string through so downstream tasks can reference it."""
    return fire_date


@register(tags=["gee", "fire"])
def calculate_dnbr(
    client: _GEE,
    roi: _GDF,
    fire_date: Annotated[
        str,
        Field(
            title="Fire Date",
            description="Approximate start date of the fire (YYYY-MM-DD).",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
    pre_fire_days: Annotated[
        int,
        Field(
            title="Pre-Fire Window (days)",
            description=(
                "Days before the fire date used to build the pre-fire Landsat mean composite. "
                "Longer windows include more cloud-free images but capture more seasonal variation. "
                "365 days (one year) follows Parks et al. 2018."
            ),
            ge=30,
            le=730,
        ),
    ] = 365,
    post_fire_days: Annotated[
        int,
        Field(
            title="Post-Fire Window (days)",
            description=(
                "Days after the fire date used to build the post-fire Landsat mean composite. "
                "60 days is recommended for savanna ecosystems — it captures charred ground "
                "before the rainy season triggers rapid regrowth. "
                "Use 180–365 days for severe wildfires in forests where recovery is slow."
            ),
            ge=30,
            le=730,
        ),
    ] = 60,
    scale: Annotated[
        int,
        Field(
            title="Analysis Scale (metres)",
            description=(
                "Pixel resolution for dNBR computation. Native Landsat resolution is 30 m. "
                "Use 100–500 m for large fires to keep computation fast. "
                "Lower values give more detail but are slower for large fire areas."
            ),
            ge=30,
            le=1000,
        ),
    ] = 100,
) -> _GDF:
    """
    Compute the Differenced Normalized Burn Ratio (dNBR) for a fire perimeter.

    Uses Landsat mean compositing on Google Earth Engine (Parks et al. 2018):

        NBR  = (NIR − SWIR2) / (NIR + SWIR2)
        dNBR = (NBR_pre − NBR_post) × 1000

    Automatically includes all available Landsat sensors for the analysis period:
        Landsat 9 OLI-2  (2022 – present)
        Landsat 8 OLI    (2013 – present)
        Landsat 7 ETM+   (1999 – 2013)
        Landsat 5 TM     (1984 – 2013)

    Returns a GeoDataFrame of pixel square polygons with columns:
        dNBR           – raw dNBR value (NBR × 1000)
        severity_class – USGS severity label (Key & Benson 2006)
        severity_index – class index 0 (Enhanced Regrowth) … 5 (High)
        fill_color     – RGBA uint8 list for per-pixel map colouring
        fill_color_hex – hex colour string for legend display
    """
    import ee
    from ecoscope.platform.connections import EarthEngineConnection

    # Resolve the named GEE connection → initialises ee.Initialize() internally.
    if isinstance(client, str):
        EarthEngineConnection.client_from_named_connection(client)

    # Real-world shapefiles often have self-intersecting rings; make_valid fixes them
    # before unary_union (which raises GEOSException on invalid geometries).
    roi = roi.set_geometry(roi.geometry.make_valid())

    fire_dt    = datetime.strptime(fire_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    pre_start  = (fire_dt - timedelta(days=pre_fire_days)).strftime("%Y-%m-%d")
    post_end   = (fire_dt + timedelta(days=post_fire_days)).strftime("%Y-%m-%d")
    pre_end    = fire_date   # pre composite covers [pre_start, fire_date)
    post_start = fire_date   # post composite covers [fire_date, post_end)

    # Estimate pixel count before hitting GEE to give a useful error message.
    roi_utm    = roi.to_crs(roi.estimate_utm_crs())
    area_m2    = float(roi_utm.geometry.unary_union.area)
    est_pixels = area_m2 / (scale ** 2)
    if est_pixels > 25_000:
        suggest = int((area_m2 / 25_000) ** 0.5) + 10
        raise ValueError(
            f"Fire area ({area_m2 / 10_000:.0f} ha) at {scale} m scale would produce "
            f"~{est_pixels:,.0f} pixels (limit: 25,000). "
            f"Increase 'Analysis Scale' to at least {suggest} m."
        )

    # Dissolve all perimeter features to one GEE geometry.
    roi_4326 = roi.to_crs("EPSG:4326")
    union_geom = roi_4326.geometry.unary_union
    if hasattr(union_geom, "geoms"):
        union_geom = union_geom.convex_hull  # MultiPolygon → single simple polygon
    # GEE requires CCW exterior ring; ER-drawn polygons are often CW (complement).
    from shapely.geometry import mapping
    from shapely.geometry.polygon import orient
    union_geom = orient(union_geom, sign=1.0)  # sign=1.0 → CCW exterior
    roi_geom = ee.Geometry(mapping(union_geom))

    # normalizedDifference() strips system:time_start, so filterDate on a post-mapped
    # collection returns nothing. Fix: apply filterDate per window BEFORE mapping.
    _sensors = [
        ("LANDSAT/LC09/C02/T1_L2", _mask_clouds_l89, _nbr_l89),
        ("LANDSAT/LC08/C02/T1_L2", _mask_clouds_l89, _nbr_l89),
        ("LANDSAT/LE07/C02/T1_L2", _mask_clouds_l57, _nbr_l57),
        ("LANDSAT/LT05/C02/T1_L2", _mask_clouds_l57, _nbr_l57),
    ]

    def _window_collection(start, end):
        colls = [
            ee.ImageCollection(cid).filterBounds(roi_geom).filterDate(start, end)
            .map(mask_fn).map(nbr_fn)
            for cid, mask_fn, nbr_fn in _sensors
        ]
        merged = colls[0]
        for c in colls[1:]:
            merged = merged.merge(c)
        return merged

    pre_coll  = _window_collection(pre_start,  pre_end)
    post_coll = _window_collection(post_start, post_end)

    # Check image counts on raw L8+L9 (unmapped) so the check is timestamp-safe.
    def _raw_count(start, end):
        return int(
            ee.ImageCollection("LANDSAT/LC08/C02/T1_L2").filterBounds(roi_geom).filterDate(start, end)
            .merge(ee.ImageCollection("LANDSAT/LC09/C02/T1_L2").filterBounds(roi_geom).filterDate(start, end))
            .size().getInfo()
        )

    pre_count  = _raw_count(pre_start,  pre_end)
    post_count = _raw_count(post_start, post_end)
    if pre_count == 0:
        raise ValueError(
            f"No Landsat imagery found for the pre-fire window ({pre_start} – {pre_end}). "
            "Try increasing 'Pre-Fire Window (days)' or check that the fire perimeter "
            "overlaps a Landsat scene footprint."
        )
    if post_count == 0:
        raise ValueError(
            f"No Landsat imagery found for the post-fire window ({post_start} – {post_end}). "
            "Try increasing 'Post-Fire Window (days)' or use a more recent fire date."
        )

    # Mean composites for pre- and post-fire periods.
    pre_nbr  = pre_coll.mean()
    post_nbr = post_coll.mean()

    # dNBR = (NBR_pre − NBR_post) × 1000, clipped to the fire perimeter.
    dnbr_img = (
        pre_nbr.subtract(post_nbr)
        .multiply(1000)
        .rename("dNBR")
        .clip(roi_geom)
    )

    # Sample pixel centres within the fire perimeter.
    sample_fc = dnbr_img.sample(
        region=roi_geom,
        scale=scale,
        geometries=True,
        tileScale=4,   # reduces GEE server-side memory pressure
    )
    features = sample_fc.getInfo()["features"]

    if not features:
        raise ValueError(
            f"No Landsat imagery found over the fire perimeter for "
            f"{pre_start} – {post_end}. "
            "Try increasing pre_fire_days or post_fire_days, or verify that the "
            "fire perimeter geometry overlaps a Landsat scene footprint."
        )

    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")

    # Convert point centres to square pixel polygons (in UTM, then back to WGS84).
    gdf  = gdf.to_crs(roi_utm.crs)
    half = scale / 2.0
    gdf["geometry"] = gdf.geometry.apply(
        lambda pt: box(pt.x - half, pt.y - half, pt.x + half, pt.y + half)
    )
    gdf = gdf.to_crs("EPSG:4326")

    # Classify each pixel.
    classified            = gdf["dNBR"].apply(_classify)
    gdf["severity_class"] = [c[0] for c in classified]
    gdf["severity_index"] = [c[1] for c in classified]
    gdf["fill_color"]     = [c[2] for c in classified]
    gdf["fill_color_hex"] = [c[3] for c in classified]

    # Observability: store composite image counts as constant columns so
    # downstream tasks can surface them as dashboard KPIs.
    gdf["pre_image_count"]  = pre_count
    gdf["post_image_count"] = post_count

    return gdf


@register(tags=["fire"])
def create_dnbr_layer(
    geodataframe: _GDF,
    opacity: Annotated[
        float,
        Field(
            title="Layer Opacity",
            description="Transparency of the dNBR pixel layer (0 = transparent, 1 = fully opaque).",
            ge=0.0,
            le=1.0,
        ),
    ] = 0.85,
) -> Any:
    """
    Build a lonboard polygon LayerDefinition for dNBR fire severity visualisation.

    Colours each pixel by severity class using the USGS standard palette and
    attaches a discrete legend showing all six severity classes.
    """
    from ecoscope.platform.tasks.results._ecomap import (
        LayerDefinition,
        LegendDefinition,
        PolygonLayerStyle,
    )

    style = PolygonLayerStyle(
        filled=True,
        stroked=False,
        fill_color_column="fill_color",
        opacity=opacity,
    )

    # Explicit labels + hex colours → draw_ecomap renders a discrete swatch legend
    # (see _ecomap.py: legend_labels.extend / legend_colors.extend path).
    legend = LegendDefinition(
        labels=_CLASS_NAMES,
        colors=_CLASS_HEX,
    )

    return LayerDefinition(
        geodataframe=geodataframe,
        layer_style=style,
        legend=legend,
        tooltip_columns=["dNBR", "severity_class"],
        zoom=True,
    )


@register(tags=["fire"])
def combine_dnbr_layers(
    dnbr_layer: Any,
    perimeter_layer: Any,
) -> Any:
    """Combine the dNBR severity layer with the fire perimeter overlay for draw_ecomap.

    Perimeter overlay goes on top of the dNBR pixels so the user can see
    where the burn scar polygon was drawn in EarthRanger. Handles SkipSentinel
    so a skipped dNBR layer propagates correctly.
    """
    from wt_task.skip import SkipSentinel

    if isinstance(dnbr_layer, SkipSentinel):
        return dnbr_layer
    layers = [dnbr_layer]
    if not isinstance(perimeter_layer, SkipSentinel) and perimeter_layer is not None:
        if isinstance(perimeter_layer, list):
            layers.extend(perimeter_layer)
        else:
            layers.append(perimeter_layer)
    return layers


@register(tags=["fire", "stats"])
def count_burned_area_ha(geodataframe: _GDF) -> float:
    """
    Total area classified as burned (Low severity or higher, severity_index ≥ 2) in hectares.

    Includes Low, Moderate-Low, Moderate-High, and High severity pixels.
    Excludes Enhanced Regrowth and Unburned pixels.
    """
    burned = geodataframe[geodataframe["severity_index"] >= 2]
    if burned.empty:
        return 0.0
    area_m2 = float(burned.to_crs(burned.estimate_utm_crs()).geometry.area.sum())
    return area_m2 / 10_000.0


@register(tags=["fire", "stats"])
def count_high_severity_area_ha(geodataframe: _GDF) -> float:
    """Total area classified Moderate-High or High severity (severity_index ≥ 4) in hectares."""
    high = geodataframe[geodataframe["severity_index"] >= 4]
    if high.empty:
        return 0.0
    area_m2 = float(high.to_crs(high.estimate_utm_crs()).geometry.area.sum())
    return area_m2 / 10_000.0


@register(tags=["fire", "stats"])
def format_area_ha(
    area_ha: Annotated[
        float,
        Field(description="Area in hectares to format for display."),
    ],
) -> str:
    """Format an area value (hectares) as a human-readable string (m², ha, or km²)."""
    if area_ha >= 10_000:
        return f"{area_ha / 10_000:.1f} km²"
    elif area_ha >= 1:
        return f"{int(round(area_ha)):,} ha"
    else:
        return f"{int(round(area_ha * 10_000)):,} m²"


@register(tags=["fire", "overlay"])
def create_styled_overlay_layer(
    geodataframe: _GDF,
) -> Any:
    """
    Overlay layer for ER spatial features.

    Splits by geometry class so lonboard never receives mixed types:
    LineString/MultiLineString → PolylineLayerStyle
    Polygon/MultiPolygon       → PolygonLayerStyle (outline only, no fill)
    Point/MultiPoint           → PointLayerStyle
    """
    from ecoscope.platform.tasks.results._ecomap import (
        LayerDefinition,
        PointLayerStyle,
        PolygonLayerStyle,
        PolylineLayerStyle,
    )

    gdf = geodataframe.copy()
    geom_col = gdf.geometry.geom_type
    color = "#FF8C00"
    width = 2.0
    layers = []

    line_gdf = gdf[geom_col.isin({"LineString", "MultiLineString"})].copy()
    if not line_gdf.empty:
        layers.append(LayerDefinition(
            geodataframe=line_gdf,
            layer_style=PolylineLayerStyle(
                get_color=color,
                get_width=width,
                width_units="pixels",
                cap_rounded=True,
            ),
            legend=None,
            tooltip_columns=[],
        ))

    polygon_gdf = gdf[geom_col.isin({"Polygon", "MultiPolygon"})].copy()
    if not polygon_gdf.empty:
        layers.append(LayerDefinition(
            geodataframe=polygon_gdf,
            layer_style=PolygonLayerStyle(
                filled=False,
                stroked=True,
                get_line_color=color,
                get_line_width=width,
                line_width_units="pixels",
            ),
            legend=None,
            tooltip_columns=[],
        ))

    point_gdf = gdf[geom_col.isin({"Point", "MultiPoint"})].copy()
    if not point_gdf.empty:
        layers.append(LayerDefinition(
            geodataframe=point_gdf,
            layer_style=PointLayerStyle(
                get_fill_color=color,
                get_radius=5,
                radius_units="pixels",
            ),
            legend=None,
            tooltip_columns=[],
        ))

    return layers


@register(tags=["fire", "earthranger"])
def load_fire_event_from_er(
    client: _ER,
    event_type: Annotated[
        str,
        Field(
            title="Event Type",
            description=(
                "EarthRanger event type value for fire events (e.g. 'controlled_burn'). "
                "To find it: in EarthRanger go to Admin → Event Categories → click your "
                "fire category → select the event type and copy the 'Value' field "
                "(not the display name — the short lowercase slug). Must match exactly."
            ),
        ),
    ],
    serial_number: Annotated[
        int,
        Field(
            title="Serial Number",
            description=(
                "EarthRanger serial number of the fire event (e.g. 472259). "
                "To find it: go to Reports → Events in EarthRanger, locate your fire event, "
                "and note the number in the '#' or Serial Number column. "
                "Each event has a unique serial number — use this to select exactly one fire."
            ),
            ge=1,
        ),
    ],
) -> _GDF:
    """
    Fetch a single fire event polygon from EarthRanger by event type and serial number.

    Fetches all events of the given type, filters client-side by serial_number
    (ER API does not support serial_number as a query parameter), and returns the
    matching polygon with an 'event_time' column. Pass the result to
    extract_fire_date to obtain the fire date string for calculate_dnbr.
    """
    from ecoscope.platform.connections import EarthRangerConnection

    er = EarthRangerConnection.client_from_named_connection(client)

    # ER API requires the event type UUID, not the string value name.
    event_types_df = er.get_event_types()
    matching_types = event_types_df[event_types_df["value"] == event_type]
    if matching_types.empty:
        available = ", ".join(sorted(event_types_df["value"].dropna().unique()))
        raise ValueError(
            f"Event type '{event_type}' not found in EarthRanger. "
            f"Available types: {available}"
        )
    event_type_uuid = matching_types.iloc[0]["id"]

    events = er.get_events(
        event_type=[event_type_uuid],
        drop_null_geometry=True,
        include_details=True,
        include_updates=False,
        include_related_events=False,
        force_point_geometry=False,
    )

    if events.empty:
        raise ValueError(
            f"No '{event_type}' events with geometry found. "
            "Check the event_type value and verify that events exist in EarthRanger."
        )

    if "serial_number" not in events.columns:
        raise ValueError(
            "EarthRanger did not return a 'serial_number' column — "
            "ensure include_details=True and that the event type includes serial numbers."
        )

    # Filter client-side — ER API has no serial_number query param.
    match = events[events["serial_number"].astype(int) == serial_number]
    if match.empty:
        raise ValueError(
            f"No '{event_type}' event found with serial number {serial_number}. "
            "Check the serial number shown in the EarthRanger event list."
        )

    # Keep only polygon-geometry events — ER events can also be logged as points.
    poly_mask = match.geometry.geom_type.isin(["Polygon", "MultiPolygon"])
    poly_match = match[poly_mask].copy()
    if poly_match.empty:
        raise ValueError(
            f"Event {serial_number} exists but has no polygon geometry. "
            "Fire perimeter events must be drawn as polygons in EarthRanger."
        )

    keep_cols = ["time", "geometry"]
    for col in ("title", "serial_number", "Burn Type"):
        if col in poly_match.columns:
            keep_cols.append(col)

    return poly_match[keep_cols].reset_index(drop=True)


@register(tags=["fire", "earthranger"])
def extract_fire_date(event_gdf: _GDF) -> str:
    """
    Extract the fire date string (YYYY-MM-DD) from an ER fire event GeoDataFrame.

    Uses the event_time column returned by load_fire_event_from_er. The date is
    converted to UTC before formatting so it is consistent regardless of the
    EarthRanger site's timezone.
    """
    import pandas as pd

    event_time = event_gdf["time"].iloc[0]
    return pd.to_datetime(event_time, utc=True).strftime("%Y-%m-%d")


# ── Observability / trust KPI tasks ──────────────────────────────────────────

@register(tags=["fire", "stats"])
def count_mean_dnbr(geodataframe: _GDF) -> float:
    """Mean dNBR value across all sampled pixels in the fire perimeter."""
    return float(geodataframe["dNBR"].mean())


@register(tags=["fire", "stats"])
def format_mean_dnbr(
    dnbr_value: Annotated[
        float,
        Field(description="Mean dNBR value to format for dashboard display."),
    ],
) -> str:
    """Format a mean dNBR value as a rounded integer string."""
    return str(int(round(dnbr_value)))


@register(tags=["fire", "stats"])
def count_pre_images(geodataframe: _GDF) -> int:
    """
    Number of Landsat 8/9 scenes used in the pre-fire mean composite.

    Stored by calculate_dnbr as a constant column on the result GeoDataFrame.
    A higher count means the composite is based on more cloud-free observations
    and is therefore more reliable.
    """
    if geodataframe.empty or "pre_image_count" not in geodataframe.columns:
        return 0
    return int(geodataframe["pre_image_count"].iloc[0])


@register(tags=["fire", "stats"])
def count_post_images(geodataframe: _GDF) -> int:
    """
    Number of Landsat 8/9 scenes used in the post-fire mean composite.

    Stored by calculate_dnbr as a constant column on the result GeoDataFrame.
    Low counts (1–2 scenes) mean the post-fire signal may be noisy or smoke-affected.
    """
    if geodataframe.empty or "post_image_count" not in geodataframe.columns:
        return 0
    return int(geodataframe["post_image_count"].iloc[0])


@register(tags=["fire", "stats"])
def format_image_count(
    count: Annotated[
        int,
        Field(description="Number of Landsat scenes to format for display."),
    ],
) -> str:
    """Format a Landsat scene count as 'N scene(s)' for dashboard display."""
    return f"{count} scene{'s' if count != 1 else ''}"

import os
from typing import Annotated, Any, Literal, Optional

import geopandas as gpd
import h3
from pydantic import Field
from pydantic.json_schema import WithJsonSchema
from shapely.geometry import MultiPolygon, Polygon
from wt_registry import register

_GDF = Annotated[Any, WithJsonSchema({"type": "ecoscope.platform.annotations.DataFrame"})]
_OptGDF = Annotated[
    Optional[Any],
    WithJsonSchema({"anyOf": [{"type": "ecoscope.platform.annotations.DataFrame"}, {"type": "null"}]}),
]

_H3_AREA_LABELS = {
    4: "~1,770 km²",
    5: "~252 km²",
    6: "~36 km²",
    7: "~5 km²",
    8: "~0.7 km²",
    9: "~0.1 km²",
    10: "~0.015 km²",
    11: "~0.002 km²",
}


@register()
def hex_bin_observations(
    geodataframe: _GDF,
    h3_resolution: int = 7,
    count_column: str = "count",
    boundary: _OptGDF = None,
) -> _GDF:
    """Bin GPS observations into H3 hexagon cells and count fixes per cell.

    Reprojects points to EPSG:4326, assigns each fix to an H3 cell, counts
    fixes per cell, builds the hexagon polygon geometry, and returns a
    polygon GeoDataFrame with a column named by count_column.
    If boundary is provided, clips the resulting hexbins to that polygon.
    """
    gdf: gpd.GeoDataFrame = geodataframe
    if gdf.empty:
        return gdf

    gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

    if gdf.empty:
        return gdf

    gdf["_h3_cell"] = [
        h3.latlng_to_cell(pt.y, pt.x, h3_resolution)
        for pt in gdf.geometry
    ]

    counts = gdf.groupby("_h3_cell").size().reset_index(name=count_column)

    counts["geometry"] = counts["_h3_cell"].apply(
        lambda cell: Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(cell)])
    )

    result = gpd.GeoDataFrame(
        counts.drop(columns=["_h3_cell"]),
        geometry="geometry",
        crs="EPSG:4326",
    )

    if isinstance(boundary, gpd.GeoDataFrame) and not boundary.empty:
        bdf = boundary.to_crs("EPSG:4326")
        mask = bdf.union_all()
        # clip() requires a polygon mask; if ER stores the boundary as lines
        # (e.g. MultiLineString), fall back to the convex hull of those lines
        if not isinstance(mask, (Polygon, MultiPolygon)):
            mask = mask.convex_hull
        if mask and not mask.is_empty:
            result = gpd.clip(result, mask)

    return result


@register()
def set_subject_group_name(
    group_name: Annotated[
        str,
        Field(
            title="Subject Group Name",
            description=(
                "Name of the EarthRanger subject group to analyse (e.g. 'Rhinos - All'). "
                "Find it in ER under Admin → Subject Groups. "
                "The name must match exactly as it appears in EarthRanger."
            ),
        ),
    ],
) -> str:
    return group_name


@register()
def format_optional_name(name: str = "") -> str:
    return name if name else "Not set"


@register()
def set_boundary_group_name(
    group_name: Annotated[
        str,
        Field(
            title="Boundary Group Name",
            description=(
                "Name of the EarthRanger spatial features group to use as the clip boundary "
                "(e.g. 'Park Boundary'). Find it in ER under Admin → Map Layers → Feature Groups. "
                "Leave blank to show all hexbins without clipping."
            ),
            default="",
        ),
    ] = "",
) -> str:
    """Return the boundary group name as-is; exists only to expose a labelled form field."""
    return group_name


@register()
def set_overlay_group_name(
    group_name: Annotated[
        str,
        Field(
            title="Overlay Layer Group Name",
            description=(
                "Name of an EarthRanger spatial features group to display as an extra layer "
                "on top of the map (e.g. 'Roads', 'Fencelines', 'Water Sources'). "
                "Find it in ER under Admin → Map Layers → Feature Groups. "
                "Leave blank to add no overlay layer."
            ),
            default="",
        ),
    ] = "",
) -> str:
    """Return the overlay group name as-is; exists only to expose a labelled form field."""
    return group_name


@register()
def set_h3_resolution(
    h3_resolution: Annotated[
        int,
        Field(
            title="Hexagon Size (H3 Resolution)",
            description=(
                "Controls how large each hexagon is on the map. "
                "Smaller number = bigger hexagons (less detail). "
                "Larger number = smaller hexagons (more detail). "
                "6 = very large (~36 km² each, landscape scale). "
                "7 = large (~5 km², good for big reserves). "
                "8 = medium (~0.7 km², good for mid-size reserves). "
                "9 = small (~0.1 km², fine detail for small reserves). "
                "10 = very small (~0.015 km², sub-kilometre precision). "
                "11 = finest (~0.002 km², sub-hectare — only useful if you have very dense data). "
                "Start with 7 and increase if your hexagons look too coarse."
            ),
            default=7,
            ge=4,
            le=11,
        ),
    ] = 7,
) -> int:
    """Return h3_resolution as-is; exposes the hexagon-size field at the workflow level."""
    return h3_resolution


@register()
def format_h3_resolution(h3_resolution: int = 7) -> str:
    """Return a human-readable H3 resolution label (e.g. 'Resolution 8 (~0.7 km²)')."""
    area = _H3_AREA_LABELS.get(h3_resolution, "")
    if area:
        return f"Resolution {h3_resolution} ({area})"
    return f"Resolution {h3_resolution}"


@register()
def set_colormap(
    colormap: Annotated[
        Literal[
            "viridis",
            "plasma",
            "Blues",
            "Greens",
            "Oranges",
            "YlGn",
            "YlOrRd",
            "RdYlGn",
            "magma",
            "inferno",
        ],
        Field(
            title="Colour Scheme",
            description=(
                "Colour scheme for the hexbin map. "
                "viridis = blue → yellow (colourblind-safe, recommended). "
                "plasma = purple → yellow. "
                "Blues = light → dark blue. "
                "Greens = light → dark green. "
                "Oranges = light → dark orange. "
                "YlGn = yellow → green. "
                "YlOrRd = yellow → orange → red (intuitive: warmer = more activity). "
                "RdYlGn = red → yellow → green (traffic-light style). "
                "magma / inferno = dark artistic palettes."
            ),
            default="viridis",
        ),
    ] = "viridis",
) -> str:
    return colormap


@register()
def normalize_boundary_geometry(geodataframe: _GDF) -> _GDF:
    """Convert boundary geometry to polygon type for use with create_polygon_layer.

    Polygons and MultiPolygons pass through unchanged.
    LineStrings and MultiLineStrings (common ER spatial feature storage format)
    are converted to their convex hull polygon.
    """
    gdf: gpd.GeoDataFrame = geodataframe.copy()

    def to_polygon(geom):
        if isinstance(geom, (Polygon, MultiPolygon)):
            return geom
        return geom.convex_hull

    gdf["geometry"] = gdf.geometry.apply(to_polygon)
    return gdf


@register()
def create_hex_polygon_layer(
    geodataframe: _GDF,
    fill_color_column: str = "count_colors",
    label_column: str = "count_range",
    get_line_width: float = 1.0,
    opacity: float = 0.9,
    tooltip_columns: Optional[list] = None,
) -> Any:
    """Hex polygon layer with auto-contrasting outlines.

    Outline is white on dark-filled cells and black on light-filled cells,
    computed per row from fill luminance so it's always visible regardless of colormap.
    """
    from ecoscope.platform.tasks.results._ecomap import (
        LayerDefinition,
        LegendDefinition,
        PolygonLayerStyle,
    )

    class HexPolygonLayerStyle(PolygonLayerStyle):
        """PolygonLayerStyle extended with line_color_column support."""
        line_color_column: str | None = None

    gdf = geodataframe.copy()

    def _contrast(fill):
        lum = (0.299 * int(fill[0]) + 0.587 * int(fill[1]) + 0.114 * int(fill[2])) / 255.0
        return [255, 255, 255, 200] if lum < 0.5 else [0, 0, 0, 180]

    gdf["_outline"] = gdf[fill_color_column].apply(_contrast)

    style = HexPolygonLayerStyle(
        fill_color_column=fill_color_column,
        line_color_column="_outline",
        stroked=True,
        get_line_width=get_line_width,
        line_width_units="pixels",
        opacity=opacity,
    )

    legend = LegendDefinition(
        label_column=label_column,
        color_column=fill_color_column,
    )

    return LayerDefinition(
        geodataframe=gdf,
        layer_style=style,
        legend=legend,
        tooltip_columns=list(tooltip_columns) if tooltip_columns else ["count"],
    )


@register()
def create_overlay_layer(
    geodataframe: _GDF,
    get_color: str = "#FF8C00",
    get_width: float = 2.0,
) -> Any:
    """Overlay layer that auto-detects geometry type and renders correctly.

    Splits the GDF by geometry class so lonboard never receives mixed types:
    LineString/MultiLineString → PolylineLayerStyle (actual paths).
    Polygon/MultiPolygon       → PolygonLayerStyle (outline-only, no fill).
    Point/MultiPoint           → PointLayerStyle.
    Returns a list of LayerDefinitions (one per geometry class present).
    combine_map_layers handles the list via extend.
    """
    from ecoscope.platform.tasks.results._ecomap import (
        LayerDefinition,
        PointLayerStyle,
        PolygonLayerStyle,
        PolylineLayerStyle,
    )

    gdf: gpd.GeoDataFrame = geodataframe.copy()
    geom_type_col = gdf.geometry.geom_type

    layers = []

    line_gdf = gdf[geom_type_col.isin({"LineString", "MultiLineString"})]
    if not line_gdf.empty:
        layers.append(LayerDefinition(
            geodataframe=line_gdf,
            layer_style=PolylineLayerStyle(
                get_color=get_color,
                get_width=get_width,
                width_units="pixels",
                cap_rounded=True,
            ),
            legend=None,
            tooltip_columns=[],
        ))

    polygon_gdf = gdf[geom_type_col.isin({"Polygon", "MultiPolygon"})]
    if not polygon_gdf.empty:
        layers.append(LayerDefinition(
            geodataframe=polygon_gdf,
            layer_style=PolygonLayerStyle(
                filled=False,
                stroked=True,
                get_line_color=get_color,
                get_line_width=get_width,
                line_width_units="pixels",
            ),
            legend=None,
            tooltip_columns=[],
        ))

    point_gdf = gdf[geom_type_col.isin({"Point", "MultiPoint"})]
    if not point_gdf.empty:
        layers.append(LayerDefinition(
            geodataframe=point_gdf,
            layer_style=PointLayerStyle(
                get_fill_color=get_color,
                get_radius=5,
                radius_units="pixels",
            ),
            legend=None,
            tooltip_columns=[],
        ))

    return layers


@register()
def combine_map_layers(
    hex_layer: Any,
    boundary_layer: Any = None,
    overlay_layer: Any = None,
) -> Any:
    """Combine hex, optional boundary, and optional overlay layers for draw_ecomap.

    Returns [hex_layer] when nothing else is present, appends boundary and/or
    overlay layers when they are real (non-skipped, non-None) values.
    Propagates skip if hex_layer itself is skipped.
    """
    from wt_task.skip import SkipSentinel

    if isinstance(hex_layer, SkipSentinel):
        return hex_layer
    layers = [hex_layer]
    if not isinstance(boundary_layer, SkipSentinel) and boundary_layer is not None:
        layers.append(boundary_layer)
    if not isinstance(overlay_layer, SkipSentinel) and overlay_layer is not None:
        # create_overlay_layer returns a list (one entry per geometry class)
        if isinstance(overlay_layer, list):
            layers.extend(overlay_layer)
        else:
            layers.append(overlay_layer)
    return layers


@register()
def classify_hex_bins(
    geodataframe: _GDF,
    k: Annotated[
        int,
        Field(
            title="Number of Colour Bands",
            description=(
                "How many colour bands to show in the legend. "
                "The fix counts are automatically grouped into this many bands "
                "using Natural Breaks — a method that finds natural gaps in your data "
                "so each band represents a meaningful range. "
                "5 is a good default. Use fewer (3–4) for small datasets or "
                "more (6–7) if you have a wide spread of counts."
            ),
            default=5,
            ge=2,
            le=10,
        ),
    ] = 5,
) -> _GDF:
    import mapclassify

    gdf: gpd.GeoDataFrame = geodataframe.copy()
    counts = gdf["count"].values
    if len(counts) < k:
        gdf["count_class"] = 0.0
        lo, hi = int(counts.min()), int(counts.max())
        gdf["count_range"] = str(lo) if lo == hi else f"{lo}–{hi}"
        return gdf.sort_values("count_class").reset_index(drop=True)
    classifier = mapclassify.NaturalBreaks(counts, k=k)
    gdf["count_class"] = classifier.yb.astype(float)
    # Build a human-readable range label per class from actual data min/max
    class_ranges = {}
    for cls in sorted(gdf["count_class"].unique()):
        class_data = gdf.loc[gdf["count_class"] == cls, "count"]
        lo, hi = int(class_data.min()), int(class_data.max())
        class_ranges[cls] = str(lo) if lo == hi else f"{lo}–{hi}"
    gdf["count_range"] = gdf["count_class"].map(class_ranges)
    # Sort ascending so legend entries appear lowest -> highest
    return gdf.sort_values("count_class").reset_index(drop=True)


@register()
def count_observations(geodataframe: _GDF) -> int:
    return len(geodataframe)


@register()
def count_subjects(geodataframe: _GDF) -> int:
    gdf: gpd.GeoDataFrame = geodataframe
    if "groupby_col" in gdf.columns:
        return int(gdf["groupby_col"].nunique())
    return 1


@register()
def count_hexbins(geodataframe: _GDF) -> int:
    return len(geodataframe)


@register()
def max_hexbin_count(geodataframe: _GDF) -> int:
    gdf: gpd.GeoDataFrame = geodataframe
    if "count" in gdf.columns and not gdf.empty:
        return int(gdf["count"].max())
    return 0


@register()
def compute_patrol_summary(
    observations: _GDF,
    hexbins: _GDF,
    boundary_name: str = "",
    colormap: str = "viridis",
) -> str:
    import pandas as pd

    obs: gpd.GeoDataFrame = observations
    hx: gpd.GeoDataFrame = hexbins

    lines = []

    # Fix count
    lines.append(f"GPS Fixes Loaded:    {len(obs):,}")

    # Subjects — ecoscope stores subject name/id in groupby_col
    if "groupby_col" in obs.columns:
        n_subjects = obs["groupby_col"].nunique()
        lines.append(f"Subjects Tracked:    {n_subjects}")

    # Date range — ecoscope uses fixtime
    if "fixtime" in obs.columns:
        try:
            times = pd.to_datetime(obs["fixtime"]).dropna()
            if not times.empty:
                fmt = "%d %b %Y"
                lines.append(
                    f"Date Range:          {times.min().strftime(fmt)}"
                    f"  →  {times.max().strftime(fmt)}"
                )
        except Exception:
            pass

    lines.append("")  # blank separator

    # Hexbin stats
    if not hx.empty and "count" in hx.columns:
        lines.append(f"Active Hexbins:      {len(hx)}")
        lines.append(f"Max Fixes per Cell:  {int(hx['count'].max())}")
        lines.append(f"Fixes Mapped:        {int(hx['count'].sum()):,}")

    lines.append("")

    # Settings
    if boundary_name:
        lines.append(f"Boundary:            {boundary_name}")
    lines.append(f"Colour Scheme:       {colormap}")

    return "\n".join(lines)


@register()
def export_geodataframe(
    geodataframe: _GDF,
    root_path: Annotated[str, Field(title="Results directory")],
    filename_suffix: Annotated[str, Field(title="Filename suffix", default="hexbins")] = "hexbins",
    layer_name: str = "data",
) -> _GDF:
    """Save a GeoDataFrame to a GeoPackage file in root_path and return it unchanged."""
    from urllib.parse import urlparse

    gdf: gpd.GeoDataFrame = geodataframe
    if root_path.startswith("file://"):
        url_path = urlparse(root_path).path  # /C:/... on Windows, /home/... on Linux
        # Strip leading slash from Windows drive paths (e.g. /C:/ -> C:/)
        if url_path.startswith("/") and len(url_path) > 2 and url_path[2] == ":":
            url_path = url_path[1:]
        path = url_path
    else:
        path = root_path
    os.makedirs(path, exist_ok=True)
    gdf.to_file(os.path.join(path, f"{filename_suffix}.gpkg"), layer=layer_name, driver="GPKG")
    return gdf

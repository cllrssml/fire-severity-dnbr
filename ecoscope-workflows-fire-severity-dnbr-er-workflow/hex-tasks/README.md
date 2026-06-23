# hex-tasks

A custom task package for [EcoScope Platform SDK](https://ecoscope.io/en/stable/platform-sdk/) workflows. Provides H3 hexagonal binning, classification, layer styling, and supporting tasks used across EcoScope Desktop workflows.

## Tasks

| Task | Description |
|---|---|
| `hex_bin_observations` | Bins a GeoDataFrame of GPS fixes into H3 hexagons at a given resolution. Optionally clips to a boundary polygon. Returns a GDF with a `count` column. |
| `classify_hex_bins` | Classifies hexbin fix counts using Natural Breaks (Jenks). Adds `count_class` (float index) and `count_range` (label string) columns for use with `apply_color_map`. |
| `create_hex_polygon_layer` | Creates a polygon layer from classified hexbins with per-row contrasting outline colours (white on dark fills, black on light fills). |
| `create_overlay_layer` | Creates a map layer from an ER spatial features GeoDataFrame. Automatically splits mixed-geometry groups by type: lines → `PolylineLayerStyle`, polygons → `PolygonLayerStyle`, points → `PointLayerStyle`. Returns a list of `LayerDefinition` objects. |
| `combine_map_layers` | Merges a hex layer, optional boundary layer, and optional overlay layer into a single list for `draw_ecomap`. Handles `SkipSentinel` and list-type overlay layers. |
| `normalize_boundary_geometry` | Converts any geometry type to Polygon/MultiPolygon using a convex hull fallback. Use for boundary clip rendering when ER stores the boundary as LineString. |
| `set_subject_group_name` | Form field for the EarthRanger subject group name. |
| `set_boundary_group_name` | Form field for an optional ER spatial features group to use as the clip boundary. |
| `set_overlay_group_name` | Form field for an optional ER spatial features group to use as an overlay layer. |
| `set_h3_resolution` | Form field for the H3 resolution (step `id` must be `h3_resolution`). |
| `set_colormap` | Form field for the colour scheme picker (step `id` must be `colormap_picker`). |
| `format_h3_resolution` | Returns a human-readable resolution label: `"Resolution N (~X km²)"`. |
| `format_optional_name` | Returns the group name, or `"—"` if empty or skipped. For display widgets. |
| `count_observations` | Returns total number of rows (GPS fixes) in a GeoDataFrame. |
| `count_subjects` | Returns the number of unique subjects in a GeoDataFrame. |
| `count_hexbins` | Returns the number of hexbin rows in a classified GeoDataFrame. |
| `max_hexbin_count` | Returns the maximum fix count across all hexbins. |
| `export_geodataframe` | Saves a GeoDataFrame to a GeoPackage file in the results directory. |

## Usage in a workflow

Reference this package in your `spec.yaml` requirements:

```yaml
requirements:
  - name: "ecoscope-platform"
    version: ">=2.11.3,<3"
    channel: "https://repo.prefix.dev/ecoscope-workflows/"
  - name: "hex-tasks"
    path: "/path/to/hex-tasks"   # absolute path for compilation
    editable: true
```

After compiling, copy the package into the compiled workflow directory and update `pixi.toml` to use a relative path before running `pixi install`. See [CLAUDE.md](../CLAUDE.md) for the full build workflow.

## Dependencies

- `h3 >= 4.0`
- `geopandas`
- `wt-registry >= 0.2, < 1`

## Workflows using this package

- [`subject-hexgrid`](https://github.com/cllrssml/subject-hexgrid) — H3 hexagonal subject coverage map

# fire-severity-dnbr — workflow notes

Fire severity map using Landsat/GEE dNBR. Fire perimeter fetched automatically
from an ER fire event by serial number. The fire event polygon is always shown
as an orange outline on top of the dNBR severity pixels. An optional user-defined
overlay layer (fencelines, roads, water points, etc.) can be added from any ER
spatial feature group.

Custom package: `dnbr-tasks` only (`create_styled_overlay_layer`, `combine_dnbr_layers`,
`set_overlay_group_name`, `format_optional_name` are all in dnbr-tasks).

---

## Task chain (v6.1.0)

`set_workflow_details` → `set_er_connection` → `set_gee_connection` →
`load_fire_event_from_er` (custom; fetches polygon from ER by serial number) →
`extract_fire_date` (custom; extracts date from ER event_time) →
`set_overlay_group_name` (custom; optional ER feature group name, default "") →
`get_spatial_features_group` (built-in; `skipif: any_dependency_is_empty_string`) →
`set_base_maps` →
`calculate_dnbr` (custom; GEE Landsat; roi = fire_event polygon) →
`create_dnbr_layer` (custom) →
`create_styled_overlay_layer` id=`perimeter_layer` (wired to `fire_event.return`; always present, no skipif) →
`create_styled_overlay_layer` id=`overlay_layer` (wired to `overlay_features.return`; `skipif: any_dependency_skipped, any_is_empty_df`) →
`combine_dnbr_layers` (custom; merges dnbr_layer + perimeter_layer + optional overlay_layer; `skipif: any_is_empty_df` only — NO `any_dependency_skipped`; handles SkipSentinel itself) →
`draw_ecomap` (`skipif: any_is_empty_df, any_dependency_skipped`) →
`persist_text` → `create_map_widget_single_view` (`skipif: never`) →
stat chain: `count_burned_area_ha` → `format_area_ha` → widget_burned →
`count_high_severity_area_ha` → `format_area_ha` → widget_high_severity →
widget_fire_date (data: `fire_date.return`) →
`format_optional_name` → widget_overlay (shows overlay name or "Not set") →
`count_mean_dnbr` → `format_mean_dnbr` → widget_mean_dnbr →
`count_pre_images` → `format_image_count` → widget_pre_scenes →
`count_post_images` → `format_image_count` → widget_post_scenes →
`gather_dashboard` (`time_range: ~`).

**Key skipif rule:** `combine_dnbr_layers` must have `skipif: conditions: [any_is_empty_df]`
only — never `any_dependency_skipped`. The task inspects overlay_layer for SkipSentinel
itself and omits it gracefully. Adding `any_dependency_skipped` would cause the entire
map to skip whenever the overlay is left blank.

## Dashboard layout (v6.1.0)

8 widgets — `widget_id` order matches `gather_dashboard` widgets list:

| widget_id | Widget | x | w | y | h |
|---|---|---|---|---|---|
| 0 | Burned | 0 | 2 | 0 | 3 |
| 1 | High Sev | 2 | 2 | 0 | 3 |
| 2 | Date | 4 | 2 | 0 | 3 |
| 3 | Overlay | 6 | 4 | 0 | 3 |
| 4 | dNBR Avg | 0 | 4 | 3 | 3 |
| 5 | Pre Imgs | 4 | 3 | 3 | 3 |
| 6 | Post Imgs | 7 | 3 | 3 | 3 |
| 7 | Map | 0 | 10 | 6 | 16 |

Row 1 (y=0, h=3): `2+2+2+4 = 10`. Row 2 (y=3, h=3): `4+3+3 = 10`.
Map full-width (y=6, h=16). Overlay gets w=4 — feature group names can be long.

## Post-compile patch

After every recompile (one package, one path):
```bash
cp -r /home/sam/Ecoscope_Projects/dnbr-tasks ecoscope-workflows-*-workflow/dnbr-tasks
sed -i 's|path = "/home/sam/Ecoscope_Projects/dnbr-tasks"|path = "./dnbr-tasks"|' \
  ecoscope-workflows-*-workflow/pixi.toml
cd ecoscope-workflows-*-workflow && pixi install && cd ..
```

## GitHub

Repo: https://github.com/cllrssml/fire-severity-dnbr
Current published version: v6.1.0 (naming cleanup: dropped -er suffix from spec id and all folder names).

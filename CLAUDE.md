# fire_severity_dnbr_er — workflow notes

Fire severity map using Landsat/GEE dNBR. Fire perimeter fetched automatically
from an ER fire event by serial number. The fire event polygon is always shown
as an orange outline on top of the dNBR severity pixels (no extra user input).

Custom package: `dnbr-tasks` only (`create_styled_overlay_layer` and `combine_dnbr_layers` are both in dnbr-tasks).

---

## Task chain

`set_workflow_details` → `set_er_connection` → `set_gee_connection` →
`load_fire_event_from_er` (custom; fetches polygon from ER by serial number) →
`extract_fire_date` (custom; extracts date from ER event_time) →
`set_base_maps` →
`calculate_dnbr` (custom; GEE Landsat; roi = fire_event polygon) →
`create_dnbr_layer` (custom) →
`create_styled_overlay_layer` (dnbr-tasks; wired to `fire_event.return` — always present, no skipif) →
`combine_dnbr_layers` (dnbr-tasks; merges dnbr_layer + perimeter_layer) →
`draw_ecomap` (`skipif: any_is_empty_df, any_dependency_skipped`) →
`persist_text` → `create_map_widget_single_view` (`skipif: never`) →
stat chain: `count_burned_area_ha` → `format_area_ha` → widget_burned →
`count_high_severity_area_ha` → `format_area_ha` → widget_high_severity →
widget_fire_date (data: `fire_date.return`) →
`count_mean_dnbr` → `format_mean_dnbr` → widget_mean_dnbr →
`count_pre_images` → `format_image_count` → widget_pre_scenes →
`count_post_images` → `format_image_count` → widget_post_scenes →
`gather_dashboard` (`time_range: ~`).

## Dashboard layout

7 widgets — `widget_id` order matches `gather_dashboard` widgets list:

| widget_id | Widget | x | w | y | h |
|---|---|---|---|---|---|
| 0 | Burned | 0 | 3 | 0 | 3 |
| 1 | High Sev | 3 | 3 | 0 | 3 |
| 2 | Date | 6 | 4 | 0 | 3 |
| 3 | dNBR Avg | 0 | 4 | 3 | 3 |
| 4 | Pre Imgs | 4 | 3 | 3 | 3 |
| 5 | Post Imgs | 7 | 3 | 3 | 3 |
| 6 | Map | 0 | 10 | 6 | 16 |

Row 1 (y=0, h=3): `3+3+4 = 10`. Row 2 (y=3, h=3): `4+3+3 = 10`.
Map full-width (y=6, h=16).

## Post-compile patch

Two packages need patching after every compile:
```bash
cp -r /home/sam/Ecoscope_Projects/dnbr-tasks ecoscope-workflows-*-workflow/dnbr-tasks
sed -i 's|path = "/home/sam/Ecoscope_Projects/dnbr-tasks"|path = "./dnbr-tasks"|' \
  ecoscope-workflows-*-workflow/pixi.toml
cd ecoscope-workflows-*-workflow && pixi install && cd ..
```

## GitHub

Not published (as of June 2026). When ready, follow the GitHub publishing section
in the top-level CLAUDE.md.

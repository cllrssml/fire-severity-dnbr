# Fire Severity dNBR — EarthRanger Workflow

An [Ecoscope Desktop](https://ecoscope.io) workflow that measures **how severely a fire burned** across its perimeter, using satellite imagery from Landsat and Google Earth Engine. Fire perimeter and date are pulled directly from an EarthRanger event — no manual file uploads needed.

---

## What does it measure?

The workflow computes the **dNBR (Differenced Normalized Burn Ratio)**, a well-established remote sensing index that compares pre-fire and post-fire satellite reflectance to estimate burn severity. Higher dNBR = more of the vegetation was consumed and more soil was exposed.

dNBR is built from two Landsat bands:
- **NIR (near-infrared)** — healthy vegetation reflects strongly; charred ground reflects weakly
- **SWIR2 (shortwave infrared)** — sensitive to vegetation moisture; drops sharply after fire

The formula is:

```
NBR  = (NIR − SWIR2) / (NIR + SWIR2)
dNBR = (pre-fire NBR − post-fire NBR) × 1000
```

Rather than using a single satellite image, this workflow follows the **mean compositing method** (Parks et al. 2018, *Remote Sensing*) — it averages all available cloud-free Landsat images over the pre- and post-fire windows. This produces a more accurate, noise-resistant result than picking one image.

---

## What does each output mean?

### Severity map
Each pixel in the fire perimeter is coloured by severity class:

| Colour | Class | dNBR range | What it means |
|--------|-------|-----------|---------------|
| 🟢 Dark green | Enhanced Regrowth | < −100 | Post-fire greening faster than pre-fire baseline (very wet conditions or misclassification) |
| ⬜ Light grey | Unburned | −100 to 100 | Little to no fire impact detected |
| 🟡 Yellow | Low | 100 – 270 | Grass and herb layer burned; tree canopy mostly intact |
| 🟠 Orange | Moderate-Low | 270 – 440 | Moderate scorch; understory partially consumed |
| 🔴 Dark orange | Moderate-High | 440 – 660 | Severe scorch; significant tree kill |
| 🟥 Deep red | High | > 660 | Near-complete vegetation loss; mineral soil exposed |

Thresholds follow the USGS Key & Benson (2006) standard, the most widely adopted classification system for dNBR.

### Stat cards

| Card | What it shows |
|------|--------------|
| **Burned** | Total area classified as Low severity or higher (ha or km²) |
| **High Sev** | Area classified as Moderate-High or High severity — the most ecologically significant portion |
| **Date** | Fire date extracted from the EarthRanger event |
| **Overlay** | Name of the optional overlay layer (or blank if none selected) |
| **dNBR Avg** | Mean dNBR across all pixels — a single-number summary of overall burn intensity |
| **Pre Imgs** | Number of Landsat scenes used in the pre-fire composite — higher is more reliable |
| **Post Imgs** | Number of Landsat scenes used in the post-fire composite — higher is more reliable |

**Tip on Pre/Post Imgs:** If either count is very low (1–2 scenes), the composite is based on limited data and may be affected by cloud cover or smoke that wasn't fully masked. If your results look unexpected, check these counts first.

---

## Requirements

- **Ecoscope Desktop** (Windows) — [download here](https://ecoscope.io)
- An **EarthRanger** data source configured in Desktop (Data Sources → Add → EarthRanger)
- A **Google Earth Engine** data source configured in Desktop (Data Sources → Add → Google Earth Engine)
- A fire event **drawn as a polygon** in EarthRanger, with an event type and serial number

> **Note:** The fire perimeter must be a polygon feature in EarthRanger (not a point). If the event was logged as a point only, this workflow cannot be used.

---

## Installation

1. In Ecoscope Desktop, go to **Workflow Templates → + Add Template**
2. Paste the GitHub URL for this repository
3. Desktop will import and install the workflow automatically

---

## Configuration

### EarthRanger (required)
Select the EarthRanger data source that contains your fire events.

### Earth Engine (required)
Select your Google Earth Engine data source.

### Fire Event

**Event Type** *(required)*
The event type value in EarthRanger for your fire events (e.g. `controlled_burn`).

To find it:
1. In EarthRanger, go to **Admin → Event Categories**
2. Click your fire event category, then click on your specific event type
3. Copy the **Value** field (the short lowercase slug, not the display name)

> The value is case-sensitive and must match exactly. If you are unsure, the error message will list all available event types in your system.

**Serial Number** *(required)*
The EarthRanger serial number of the specific fire event you want to analyse.

To find it:
1. In EarthRanger, go to **Reports → Events**
2. Locate your fire event in the list
3. Note the **#** (serial number) shown next to it

> Serial numbers are always unique — using one guarantees this workflow analyses exactly the event you intend.

### Overlay Layer Group Name *(optional)*
Name of an EarthRanger spatial features group to display as an overlay on the map (e.g. `Roads`, `Fencelines`, `Water Sources`). Find groups in EarthRanger under **Admin → Map Layers → Feature Groups**. Leave blank to skip.

### Base Maps
Satellite imagery basemap is shown at 50% opacity by default, with a topo basemap underneath. You can customise or remove layers here.

### Compute dNBR

**Pre-Fire Window (days)** *(default: 365)*
How many days before the fire date to collect pre-fire Landsat imagery. A full year (365) captures enough cloud-free scenes across all seasons to build a reliable baseline. Increasing to 730 days can help in persistently cloudy regions.

**Post-Fire Window (days)** *(default: 60)*
How many days after the fire date to collect post-fire imagery.
- **Savanna / grassland (dry season fires):** 60 days is recommended — captures charred ground before the rainy season triggers regrowth that would dilute the signal.
- **Forest / temperate vegetation:** 90–180 days. Forest recovery is slower, so a longer window captures the full extent of tree kill.
- **Avoid > 365 days** unless the fire was severe — by then, regrowth in many ecosystems has significantly reduced the dNBR signal.

**Analysis Scale (metres)** *(default: 100)*
Pixel resolution for the analysis. Landsat's native resolution is 30 m.
- **100 m** is a good default — fast and still shows spatial patterns within large fires.
- **30 m** gives the sharpest detail but requires the fire to be small enough (< ~750 ha at 30 m before hitting GEE limits). The workflow will tell you if the area is too large.
- **200–500 m** for very large fires (> 10,000 ha) to keep computation practical.

### dNBR Severity Layer

**Layer Opacity** *(default: 0.85)*
Transparency of the severity pixel layer. Reduce to see the basemap more clearly.

---

## Interpreting results — important caveats

### dNBR is calibrated for forest ecosystems
The Key & Benson (2006) severity thresholds were developed primarily in North American conifer forests. In **savanna and grassland** ecosystems:
- Pre-fire vegetation is sparser, so even a 100% grass burn may only produce a dNBR of 100–200 (classified "Low" or "Unburned")
- The *relative* severity within a single fire is still meaningful — areas with higher dNBR burned more intensely than areas with lower dNBR
- Do not compare absolute dNBR values between forest fires and savanna fires as if they are equivalent

### Pre/Post Imgs trust indicators
A composite built from many scenes is far more reliable than one built from 1–2 scenes. If Pre Imgs or Post Imgs is very low:
- Results may be biased by a single cloudy or smoky image that wasn't fully masked
- Consider widening the pre-fire or post-fire window to gather more scenes

### "Enhanced Regrowth" does not always mean regrowth
Negative dNBR can appear when the post-fire image captures a wetter period than the pre-fire baseline (e.g. an unusually wet dry season). Treat Enhanced Regrowth pixels with caution in savanna ecosystems.

### Smoke masking
Standard Landsat cloud masking does not remove all smoke. Very recent post-fire images (< 30 days) in high-smoke conditions may have underestimated dNBR values. The Pre/Post Imgs count helps identify this risk.

---

## Troubleshooting

**"Event type not found"**
The event type value you entered does not exist in EarthRanger. Check the error message — it will list all available event types. Double-check the Admin → Event Categories value field.

**"No event found with serial number X"**
The serial number does not match any event of that type. Verify the serial number in EarthRanger's Reports → Events view.

**"Event exists but has no polygon geometry"**
The event was logged as a point, not a polygon. Fire perimeter events must be drawn as polygons in EarthRanger.

**"No Landsat imagery found for the pre-fire window"**
No cloud-free Landsat scenes exist over this location for the specified window. Try increasing Pre-Fire Window (days) or check that the fire perimeter polygon is correctly positioned.

**"~X pixels exceeds limit"**
The fire area is too large for the chosen Analysis Scale. Increase the scale (e.g. from 30 m to 100 m or 200 m) as suggested in the error message.

**Map shows only grey (Unburned) pixels**
- Check Post-Fire Window: if using a long post-fire window in a fast-recovering ecosystem, regrowth may already have reduced the dNBR signal
- Check Post Imgs: if it is very low (1–2), a smoke-contaminated image may be suppressing the signal
- Verify the fire event polygon covers the actual burned area in EarthRanger

---

## Science references

Parks, S. A., Holsinger, L. M., Voss, M. A., Loehman, R. A., & Robinson, N. P. (2018). Mean composite fire severity metrics computed with Google Earth Engine offer improved accuracy and expanded mapping potential. *Remote Sensing*, 10(6), 879. https://doi.org/10.3390/rs10060879

Key, C. H., & Benson, N. C. (2006). Landscape Assessment: Ground measure of severity, the Composite Burn Index; and remote sensing of severity, the Normalized Burn Ratio. In *USGS Rapid Assessment of Vegetation Fire Dynamics* (pp. LA-1–LA-55). US Geological Survey.

---

## License

BSD 3-Clause — see [LICENSE](LICENSE). Copyright Sam Cilliers.

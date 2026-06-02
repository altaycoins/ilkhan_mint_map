# 🗺️ Ilkhanate Mint Map Studio

An interactive, high-fidelity Geographic Information System (GIS) built with **Streamlit** and **Folium** to visualize, analyze, and catalog historical mints and regional boundaries of the Ilkhanate Empire.

This application blends static historical spatial vectors with a live cloud-backed database layout, letting users track geographic metrics, apply stylized artistic presets, and make live, permanent database contributions right from their web browser.

Live Web App Link: ilkhanid-mint-map.streamlit.app

---

## 🚀 Features

- **Consolidated GIS Framework:** Dynamically parses native KML element structures to separate complex geographical multi-point region boundaries (Polygons) and mint sites (Points) out of a single file (`regions.kml`).
- **Live Cloud Database Write-Back:** Integrates directly with a secure Google Sheets backend. Any custom mints injected via the browser form pass an API pipe to save permanently to the cloud and instantly render across all live active user maps.
- **Transliteration Sorting Engine:** Implements diacritic-insensitive Unicode decomposing (`unicodedata`). Dropdown filter modules completely strip accent marks (`ā`, `ī`, `ṣ`, `ḥ`) under the hood, organizing entries in true, clean alphabetical A–Z order.
- **Typography & Display Safeguards:** Overhauls crowded vector text clutter using optimized single-pass alpha-blended halos (`text-shadow`), entirely bypassing browser font rendering smears over dense marker clusters.
- **Artistic Graphic Map Presets:**
  - Standard (OpenStreetMap)
  - Physical Terrain (Esri)
  - Topographic Contour Lines (OpenTopoMap)
  - Dark Graphic Poster (Navy & Gold Custom CSS Overlay)
  - Light Graphic Poster (Cream & Gold Custom CSS Overlay)
- **Data Export Utilities:**
  - **HTML Vector Render:** Downloads standalone full-screen web code templates for crisp, high-resolution publication screenshots.
  - **Excel-Safe Metadata Catalog:** Exports the entire map dataset to an Excel-friendly CSV spreadsheet encoded with a physical Byte Order Mark (`utf-8-sig`) layer to prevent character corruption across Arabic scripts and transliterations.

---

## 🛠️ Project File Structure

```text
├── app.py                  # Core Python Application Script
├── regions.kml             # Baseline GIS File (Contains Region Borders & Base Mints)
└── requirements.txt        # Python Application Dependency Requirements

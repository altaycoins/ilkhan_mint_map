import streamlit as st
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
import xml.etree.ElementTree as ET
import os
import folium
from folium.features import DivIcon
from streamlit_folium import st_folium
import warnings
import re
import unicodedata
from streamlit_gsheets import GSheetsConnection

# Suppress pandas/pyproj warnings for a cleaner console
warnings.filterwarnings('ignore')

st.set_page_config(layout="wide", page_title="Ilkhanate Mint Studio")
st.title("🗺️ Ilkhanate Mint Map Studio")

# Initialize the Google Sheets Cloud Connection Engine
conn = st.connection("gsheets", type=GSheetsConnection)

def strip_diacritics(text):
    """
    Decomposes special transliteration marks (ā, ī, ū, ṣ, ḥ, etc.) 
    into standard characters for smooth A-Z dropdown sorting.
    """
    if not text: return ""
    normalized = unicodedata.normalize('NFKD', str(text))
    stripped = "".join([c for c in normalized if not unicodedata.combining(c)])
    clean = re.sub(r"[‘’`´'\"]", "", stripped)
    return clean.strip().lower()

def parse_kml_coordinates(coord_text):
    """Splits KML coordinate strings safely, handling spaces and newlines."""
    if not coord_text: return []
    tokens = coord_text.strip().split()
    coords = []
    for t in tokens:
        parts = t.split(',')
        if len(parts) >= 2:
            try:
                coords.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return coords

@st.cache_data
def load_single_kml(file_path):
    """Parses a single KML containing both regions and mints, preserving ExtendedData."""
    if not os.path.exists(file_path):
        st.error(f"File not found: {file_path}. Please ensure 'regions.kml' is in the same folder.")
        return None
        
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        st.error(f"XML Parsing Error in {file_path}: {e}")
        return None
        
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    records = []
    
    for placemark in root.findall('.//kml:Placemark', ns):
        name_node = placemark.find('kml:name', ns)
        name = name_node.text.strip() if name_node is not None and name_node.text else ""
        
        desc_node = placemark.find('kml:description', ns)
        desc = desc_node.text.strip() if desc_node is not None and desc_node.text else ""
        
        row_data = {'Name': name, 'Description': desc}
        
        # Pull custom metadata columns (Arabic, Modern Country, etc.)
        ext_data = placemark.find('kml:ExtendedData', ns)
        if ext_data is not None:
            for data_node in ext_data.findall('kml:Data', ns):
                col_name = data_node.get('name')
                val_node = data_node.find('kml:value', ns)
                if col_name and val_node is not None and val_node.text:
                    formatted_col = col_name.strip().replace(' ', '_').title()
                    row_data[formatted_col] = val_node.text.strip()
                    
        # Extract Geometry
        geometry = None
        point_node = placemark.find('.//kml:Point/kml:coordinates', ns)
        if point_node is not None and point_node.text:
            pt_coords = parse_kml_coordinates(point_node.text)
            if pt_coords: geometry = Point(pt_coords[0])
                
        poly_node = placemark.find('.//kml:Polygon//kml:coordinates', ns)
        if poly_node is not None and poly_node.text:
            poly_coords = parse_kml_coordinates(poly_node.text)
            if len(poly_coords) >= 3: geometry = Polygon(poly_coords)
                
        if geometry:
            row_data['geometry'] = geometry
            records.append(row_data)
            
    if not records: return None
    gdf = gpd.GeoDataFrame(records, geometry='geometry')
    gdf.set_crs(epsg=4326, inplace=True)
    return gdf

# --- Persistent Data Storage State Initialization ---
if 'base_regions' not in st.session_state or 'base_mints' not in st.session_state:
    all_data_gdf = load_single_kml("regions.kml")
    if all_data_gdf is not None:
        st.session_state.base_regions = all_data_gdf[all_data_gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])].copy()
        raw_mints = all_data_gdf[all_data_gdf.geometry.type == 'Point'].copy()
        
        # Hardcode ordering baseline once alphabetically by normalized clean text names
        if not raw_mints.empty:
            raw_mints['norm_sort'] = raw_mints['Name'].apply(strip_diacritics)
            raw_mints = raw_mints.sort_values('norm_sort').drop(columns=['norm_sort'])
            raw_mints['Mint_Number'] = range(1, len(raw_mints) + 1)
        st.session_state.base_mints = raw_mints
    else:
        st.session_state.base_regions = None
        st.session_state.base_mints = None

# Fetch active baseline copies
regions_gdf = st.session_state.base_regions.copy() if st.session_state.base_regions is not None else None
mints_gdf = st.session_state.base_mints.copy() if st.session_state.base_mints is not None else None

# --- Live Cloud Read Connection Layer ---
try:
    live_custom_df = conn.read(ttl="1m")
    if not live_custom_df.empty:
        live_custom_df['geometry'] = live_custom_df.apply(lambda r: Point(float(r['Longitude']), float(r['Latitude'])), axis=1)
        custom_gdf = gpd.GeoDataFrame(live_custom_df, geometry='geometry')
        custom_gdf.set_crs(epsg=4326, inplace=True)
        mints_gdf = pd.concat([mints_gdf, custom_gdf], ignore_index=True)
except Exception:
    pass

# Determine global sequence indexing limits
highest_base_num = int(st.session_state.base_mints['Mint_Number'].max()) if st.session_state.base_mints is not None and not st.session_state.base_mints.empty else 0
highest_live_num = int(live_custom_df['Mint_Number'].max()) if 'live_custom_df' in locals() and not live_custom_df.empty else 0
next_suggested_num = max(highest_base_num, highest_live_num) + 1

# Dropdown clean alphabetical indexing helpers
def get_sorted_dropdown_options(df):
    if df is None or df.empty: return []
    unique_names = [str(n) for n in df['Name'].unique() if n]
    return sorted(unique_names, key=strip_diacritics)

# Theme Style Presets
style_options = {
    "Standard (OpenStreetMap)": {
        "tiles": "OpenStreetMap", "attr": None, "css": "",
        "r_border": "#8C7B6B", "r_fill": "#F4F1EA", "m_bg": "#EA4335", "m_text": "#FFFFFF",
        "lbl_color": "#1A1A1A", "lbl_halo": "#FFFFFF"
    },
    "Dark Graphic Poster (Navy & Gold)": {
        "tiles": "CartoDB dark_matter", "attr": None,
        "css": ".leaflet-tile-container img { filter: hue-rotate(205deg) saturate(1.6) brightness(0.65) contrast(1.15) !important; }",
        "r_border": "#FFFFFF", "r_fill": "#C89D4D", "m_bg": "#C89D4D", "m_text": "#101D33",
        "lbl_color": "#C89D4D", "lbl_halo": "#101D33"
    },
    "Light Graphic Poster (Cream & Gold)": {
        "tiles": "CartoDB positron", "attr": None,
        "css": ".leaflet-tile-container img { filter: sepia(0.45) hue-rotate(340deg) saturate(0.95) brightness(1.02) !important; }",
        "r_border": "#101D33", "r_fill": "#DFCA9D", "m_bg": "#101D33", "m_text": "#FFFFFF",
        "lbl_color": "#101D33", "lbl_halo": "#F4F1EA"
    },
    "Physical Terrain (Esri)": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}", "attr": "Tiles © Esri", "css": "",
        "r_border": "#8C7B6B", "r_fill": "#F4F1EA", "m_bg": "#EA4335", "m_text": "#FFFFFF",
        "lbl_color": "#1A1A1A", "lbl_halo": "#FFFFFF"
    },
    "Topographic (OpenTopoMap)": {
        "tiles": "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", "attr": "Map style: © OpenTopoMap", "css": "",
        "r_border": "#8C7B6B", "r_fill": "#F4F1EA", "m_bg": "#EA4335", "m_text": "#FFFFFF",
        "lbl_color": "#1A1A1A", "lbl_halo": "#FFFFFF"
    }
}

# --- UI Sidebar ---
with st.sidebar:
    st.header("🔍 Search & Filter")
    
    search_mint = None
    if mints_gdf is not None and not mints_gdf.empty:
        sorted_mint_names = get_sorted_dropdown_options(mints_gdf)
        search_mint = st.selectbox("Search for a Mint:", options=[""] + sorted_mint_names)

    selected_regions = []
    if regions_gdf is not None and not regions_gdf.empty:
        sorted_region_names = get_sorted_dropdown_options(regions_gdf)
        selected_regions = st.multiselect("Filter by Region(s):", options=sorted_region_names)
        
    st.header("👁️ Layer Toggles")
    show_regions = st.checkbox("Show Region Borders", value=False)
    show_region_labels = st.checkbox("Show Region Names", value=False)
    show_mints = st.checkbox("Show Mints", value=True)
    # NEW COMPONENT TOGGLE BUTTON
    show_mint_names = st.checkbox("Show Mint Names next to Numbers", value=True)
    
    st.header("🎨 Map Styling")
    selected_style_name = st.selectbox("Base Map Style Preset", list(style_options.keys()))
    style_preset = style_options[selected_style_name]
    
    region_color = st.color_picker("Region Border Color", style_preset["r_border"])
    region_fill = st.color_picker("Region Fill Color", style_preset["r_fill"])

    # --- Add New Mint UI Form ---
    st.markdown("---")
    st.header("➕ Add New Custom Mint")
    with st.form("mint_entry_form", clear_on_submit=True):
        new_name = st.text_input("Mint Name (Main Header):")
        new_arabic = st.text_input("Arabic script value:")
        
        region_choices = [""] + get_sorted_dropdown_options(st.session_state.base_regions)
        new_region = st.selectbox("Assign Region Boundary:", options=region_choices)
        
        new_country = st.text_input("Modern Country:")
        new_turkish = st.text_input("Turkish variant:")
        new_lat = st.number_input("Latitude Coordinate (Y):", format="%.6f", value=34.353182)
        new_lon = st.number_input("Longitude Coordinate (X):", format="%.6f", value=58.678751)
        new_num = st.number_input("Assigned Static Number (Locked):", value=next_suggested_num, step=1)
        
        submit_mint = st.form_submit_button("Save and Inject Mint Permanent")
        if submit_mint and new_name:
            try:
                current_sheet_df = conn.read()
            except Exception:
                current_sheet_df = pd.DataFrame()
                
            new_row = pd.DataFrame([{
                'Name': new_name, 'Arabic': new_arabic, 'Region': new_region,
                'Modern_Country': new_country, 'Turkish': new_turkish, 
                'Latitude': float(new_lat), 'Longitude': float(new_lon), 'Mint_Number': int(new_num)
            }])
            
            updated_sheet_df = pd.concat([current_sheet_df, new_row], ignore_index=True)
            conn.update(data=updated_sheet_df)
            st.success(f"Successfully committed '{new_name}' to cloud sheet database as Mint #{new_num}!")
            st.rerun()

# --- Main App Logic & Map Rendering ---
if regions_gdf is not None and mints_gdf is not None:
    if style_preset["css"]:
        st.markdown(f"<style>{style_preset['css']}</style>", unsafe_allow_html=True)
        
    if selected_regions:
        regions_gdf = regions_gdf[regions_gdf['Name'].isin(selected_regions)]
        if not mints_gdf.empty and not regions_gdf.empty:
            mints_gdf = gpd.sjoin(mints_gdf, regions_gdf, how="inner", predicate="intersects")
    
    if search_mint:
        target_col = 'Name_left' if 'Name_left' in mints_gdf.columns else 'Name'
        search_result = mints_gdf[mints_gdf[target_col] == search_mint]
        if not search_result.empty:
            target_mint = search_result.iloc[0]
            center_y, center_x, zoom_level = target_mint.geometry.y, target_mint.geometry.x, 10 
        else:
            st.warning(f"Mint '{search_mint}' is currently hidden by active data filters.")
            bounds = regions_gdf.total_bounds if not regions_gdf.empty else mints_gdf.total_bounds
            center_y, center_x, zoom_level = (bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2, 5
    else:
        bounds = regions_gdf.total_bounds if not regions_gdf.empty else mints_gdf.total_bounds
        center_y, center_x, zoom_level = (bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2, 5

    m = folium.Map(location=[center_y, center_x], zoom_start=zoom_level, tiles=style_preset["tiles"], attr=style_preset["attr"])
    
    if show_regions and not regions_gdf.empty:
        style_function = lambda x: {'color': region_color, 'weight': 1.5, 'fillColor': region_fill, 'fillOpacity': 0.55}
        folium.GeoJson(regions_gdf, style_function=style_function).add_to(m)
        
    if show_region_labels and not regions_gdf.empty:
        for _, row in regions_gdf.iterrows():
            r_name_val = row.get('Name_left', row.get('Name', ''))
            if r_name_val: 
                centroid = row.geometry.centroid
                folium.map.Marker(
                    [centroid.y, centroid.x],
                    icon=DivIcon(class_name="empty", icon_size=(150,36), icon_anchor=(75,18), html=f'<div style="font-size: 14pt; font-weight: bold; color: {style_preset["lbl_color"]}; text-align: center; text-shadow: 0px 0px 4px {style_preset["lbl_halo"]};">{r_name_val}</div>')
                ).add_to(m)

    if show_mints and not mints_gdf.empty:
        skip_cols = ['name', 'name_left', 'name_right', 'geometry', 'index_right', 'description', 'description_left', 'description_right', 'mint_number', 'mint_number_left', 'mint_number_right']
        
        theme_m_bg = "#101D33" if "Light" in selected_style_name else ("#C89D4D" if "Dark" in selected_style_name else "#EA4335")
        theme_m_txt = "#FFFFFF" if "Light" in selected_style_name else ("#101D33" if "Dark" in selected_style_name else "#FFFFFF")
        
        for _, row in mints_gdf.iterrows():
            m_name = str(row.get('Name_left', row.get('Name', '')))
            mint_num = str(row.get('Mint_Number_left', row.get('Mint_Number', '•')))
            
            is_searched = (m_name == search_mint)
            bg_color = "#2072B2" if is_searched else theme_m_bg
            text_color = "#FFFFFF" if is_searched else theme_m_txt
            
            # Popup Grid Table Builder
            popup_html = f"<div style='min-width: 240px;'><h3 style='margin-bottom:8px; border-bottom: 2px solid #333; padding-bottom: 4px;'>{m_name}</h3>"
            popup_html += "<table style='width: 100%; border-collapse: collapse; font-size: 10pt;'>"
            popup_html += f"<tr><td style='font-weight:700; padding:4px 0; border-bottom:1px solid #eee;'>Longitude</td><td style='text-align:right; padding:4px 0; border-bottom:1px solid #eee;'>{row.geometry.x:.6f}</td></tr>"
            popup_html += f"<tr><td style='font-weight:700; padding:4px 0; border-bottom:1px solid #eee;'>Latitude</td><td style='text-align:right; padding:4px 0; border-bottom:1px solid #eee;'>{row.geometry.y:.6f}</td></tr>"
            
            for col_name, val in row.items():
                if col_name.lower() not in skip_cols and pd.notna(val) and str(val).strip() != "":
                    clean_label = col_name.replace('_', ' ').title()
                    popup_html += f"<tr><td style='font-weight:700; padding: 4px 10px 4px 0; border-bottom: 1px solid #eee;'>{clean_label}</td>"
                    popup_html += f"<td style='padding: 4px 0; border-bottom: 1px solid #eee; text-align: right;'>{val}</td></tr>"
            popup_html += "</table></div>"
            popup = folium.Popup(popup_html, max_width=350)
            
            # CONDITIONAL RENDERING BLUEPRINT: Strips text element out if user toggles checkbox off
            text_element_html = f"""
                <div style="font-size: 11pt; color: {style_preset['lbl_color']}; font-weight: 700; text-shadow: 0px 0px 4px {style_preset['lbl_halo']}; white-space: nowrap;">
                    {m_name}
                </div>
            """ if show_mint_names else ""
            
            html_content = f"""
                <div style="display: flex; align-items: center; gap: 4px;">
                    <div style="background-color: {bg_color}; color: {text_color}; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-size: 8pt; font-weight: bold; box-shadow: 1px 1px 3px rgba(0,0,0,0.4); flex-shrink: 0; z-index: 999;">
                        {mint_num}
                    </div>
                    {text_element_html}
                </div>
            """
            
            folium.map.Marker(
                [row.geometry.y, row.geometry.x],
                icon=DivIcon(class_name="empty", icon_size=(150, 24), icon_anchor=(11, 11), html=html_content),
                popup=popup
            ).add_to(m)
            
    st_folium(m, width=1200, height=750, returned_objects=[])
    
    # --- Data Export Engines ---
    st.markdown("---")
    btn_col1, btn_col2 = st.columns(2)
    
    with btn_col1:
        map_html = m.get_root().render()
        st.download_button(
            label="📥 Download Standalone Map (HTML) for High-Res Screenshots", 
            data=map_html, 
            file_name="styled_ilkhans_map.html", 
            mime="text/html",
            use_container_width=True
        )
        
    with btn_col2:
        if not mints_gdf.empty:
            export_df = pd.DataFrame()
            
            num_src = 'Mint_Number_left' if 'Mint_Number_left' in mints_gdf.columns else 'Mint_Number'
            name_src = 'Name_left' if 'Name_left' in mints_gdf.columns else 'Name'
            
            export_df['Mint Number'] = mints_gdf[num_src]
            export_df['Mint Name'] = mints_gdf[name_src]
            export_df['Longitude'] = mints_gdf.geometry.x
            export_df['Latitude'] = mints_gdf.geometry.y
            
            export_skip_keys = [
                'name', 'name_left', 'name_right', 'geometry', 'index_right', 
                'description', 'description_left', 'description_right', 
                'mint_number', 'mint_number_left', 'mint_number_right', 'norm_sort',
                'latitude', 'longitude', 'longtitude'
            ]
            for col in mints_gdf.columns:
                if col.lower() not in export_skip_keys:
                    clean_col_title = col.replace('_', ' ').title()
                    export_df[clean_col_title] = mints_gdf[col]
            
            export_df = export_df.sort_values('Mint Number')
            csv_payload_bytes = export_df.to_csv(index=False).encode('utf-8-sig')
            
            st.download_button(
                label="📊 Download Mint Catalog Data Spreadsheet (CSV)",
                data=csv_payload_bytes,
                file_name="ilkhanate_mints_catalog.csv",
                mime="text/csv",
                use_container_width=True
            )
